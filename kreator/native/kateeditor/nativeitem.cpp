#include "nativeitem.h"

#include <QApplication>
#include <QCoreApplication>
#include <QEvent>
#include <QPainter>
#include <QQuickWindow>
#include <QWidget>

static QList<QPointer<QWidget>> s_kateRoots;
static QPointer<QWindow> s_hostWindow;

void NativeWidgetItem::registerKateWidget(QWidget *root)
{
    s_kateRoots.removeAll(nullptr);
    if (root && !s_kateRoots.contains(root))
        s_kateRoots.append(root);
}

bool NativeWidgetItem::isKateWidget(const QObject *o)
{
    for (; o; o = o->parent()) {
        for (const auto &r : std::as_const(s_kateRoots)) {
            if (r == o)
                return true;
        }
    }
    return false;
}

QWindow *NativeWidgetItem::hostWindow()
{
    return s_hostWindow;
}

NativeWidgetItem::NativeWidgetItem(QQuickItem *parent)
    : QQuickPaintedItem(parent)
{
    // popups shown anywhere, and quitting
    QCoreApplication::instance()->installEventFilter(this);
}

NativeWidgetItem::~NativeWidgetItem()
{
    detachWidget();
}

void NativeWidgetItem::detachWidget()
{
    if (!m_widget)
        return;
    m_widget->removeEventFilter(this);
    m_widget->hide();
    // detach from the QQuickWindow before either goes away
    if (QWindow *w = m_widget->windowHandle())
        w->setParent(nullptr);
    m_widget = nullptr;
}

void NativeWidgetItem::setWidget(QWidget *widget)
{
    if (widget == m_widget)
        return;
    detachWidget();
    m_widget = widget;
    if (!widget)
        return;
    registerKateWidget(widget);
    // a native window of its own, to be parented to the QQuickWindow
    widget->setParent(nullptr);
    widget->setAttribute(Qt::WA_NativeWindow);
    widget->setAttribute(Qt::WA_DontCreateNativeAncestors);
    widget->setWindowFlags(Qt::Widget);
    widget->hide();
    // Kreator decides when to quit: the widget has no widget parent, so Qt would
    // count it as a top-level window
    widget->setAttribute(Qt::WA_QuitOnClose, false);
    widget->installEventFilter(this);
    m_lastRect = QRect();
    QQuickWindow *w = m_window;
    m_window = nullptr;
    attach(w);
}

QWidget *NativeWidgetItem::widget() const
{
    return m_widget;
}

QQuickWindow *NativeWidgetItem::quickWindow() const
{
    return m_window;
}

bool NativeWidgetItem::isUnderWidget(const QObject *o) const
{
    for (; o; o = o->parent()) {
        if (o == m_widget)
            return true;
    }
    return false;
}

bool NativeWidgetItem::eventFilter(QObject *watched, QEvent *event)
{
    // Kate's own popups (context menu, completion, tooltips…) are widget
    // windows whose transient parent would be an embedded widget, which on
    // Wayland is only a subsurface, or a hidden helper window; popups need a
    // real toplevel: hand them Kreator's window. (QShowEvent reaches a widget
    // before its native window is shown.)
    if (event->type() == QEvent::Show && watched->isWidgetType()) {
        auto *w = static_cast<QWidget *>(watched);
        if (w->isWindow() && !s_kateRoots.contains(w) && !w->property("kreatorKatePopup").toBool()) {
            // under one of Kate's widgets, or a parentless popup / dialog
            // opened while Kate has the keyboard (the code action menu…)
            const bool kate = w->parentWidget() ? isKateWidget(w->parentWidget())
                                                : (w->windowType() == Qt::Popup || w->windowType() == Qt::Dialog)
                                                  && isKateWidget(QApplication::activeWindow());
            if (kate)
                w->setProperty("kreatorKatePopup", true);
        }
        if (w->isWindow() && w->property("kreatorKatePopup").toBool()) {
            QWindow *host = s_hostWindow;
            if (QWindow *h = (w->winId(), w->windowHandle()); h && host && h->transientParent() != host)
                h->setTransientParent(host);
        }
        return false;
    }
    if ((event->type() == QEvent::Show || event->type() == QEvent::Hide) && watched->isWindowType()) {
        auto *w = static_cast<QWindow *>(watched);
        // (not tooltips: hovering a button while typing must not freeze the widget)
        const bool popup = (w->flags() & Qt::WindowType_Mask) == Qt::Popup;
        if (popup && w != m_window && !(m_widget && w == m_widget->windowHandle())) {
            bool kate = false;
            const auto widgets = QApplication::topLevelWidgets();
            for (QWidget *tw : widgets) {
                if (tw->windowHandle() == w) {
                    kate = tw->property("kreatorKatePopup").toBool() || isKateWidget(tw->parentWidget());
                    break;
                }
            }
            if (!kate) {
                if (event->type() == QEvent::Show && !m_popupWindows.contains(w))
                    m_popupWindows.append(w);
                else if (event->type() == QEvent::Hide)
                    m_popupWindows.removeAll(w);
                updateFrozen();
            }
        }
        return false;
    }
    if (event->type() == QEvent::Quit && watched == QCoreApplication::instance()) {
        // Qt doesn't finish quitting while a parentless widget is shown
        if (m_widget)
            m_widget->hide();
        return false;
    }
    if (watched == m_widget && event->type() == QEvent::Close) {
        event->accept();
        return true;
    }
    return QQuickPaintedItem::eventFilter(watched, event);
}

bool NativeWidgetItem::frozen() const
{
    return m_frozen;
}

void NativeWidgetItem::setFrozen(bool frozen)
{
    if (frozen == m_frozen)
        return;
    m_frozen = frozen;
    updateFrozen();
    Q_EMIT frozenChanged();
}

void NativeWidgetItem::updateFrozen()
{
    m_popupWindows.removeAll(nullptr);
    const bool frozen = m_frozen || !m_popupWindows.isEmpty();
    if (frozen == m_effectiveFrozen)
        return;
    m_effectiveFrozen = frozen;
    if (frozen && m_widget && m_widget->isVisible()) {
        m_snapshot = m_widget->grab().toImage();  // at the device pixel ratio
        m_widget->hide();
    } else if (!frozen) {
        m_snapshot = QImage();
        syncGeometry();
    }
    update();
}

void NativeWidgetItem::paint(QPainter *painter)
{
    if (m_effectiveFrozen && !m_snapshot.isNull())
        painter->drawImage(QRectF(0, 0, width(), qMax<qreal>(1, height() - m_bottomInset)), m_snapshot);
}

qreal NativeWidgetItem::bottomInset() const
{
    return m_bottomInset;
}

void NativeWidgetItem::setBottomInset(qreal inset)
{
    inset = qBound<qreal>(0, inset, height());
    if (qFuzzyCompare(inset + 1, m_bottomInset + 1))
        return;
    m_bottomInset = inset;
    syncGeometry();
    update();
    Q_EMIT bottomInsetChanged();
}

bool NativeWidgetItem::grabToFile(const QString &path)
{
    return m_widget && m_widget->grab().save(path);
}

QRect NativeWidgetItem::nativeGeometry() const
{
    return m_widget ? m_widget->geometry() : QRect();
}

bool NativeWidgetItem::nativeVisible() const
{
    return m_widget && m_widget->isVisible();
}

void NativeWidgetItem::itemChange(ItemChange change, const ItemChangeData &value)
{
    if (change == ItemSceneChange)
        attach(value.window);
    else if (change == ItemVisibleHasChanged)
        syncGeometry();
    QQuickPaintedItem::itemChange(change, value);
}

void NativeWidgetItem::geometryChange(const QRectF &newGeometry, const QRectF &oldGeometry)
{
    QQuickPaintedItem::geometryChange(newGeometry, oldGeometry);
    syncGeometry();
}

void NativeWidgetItem::attach(QQuickWindow *window)
{
    if (window == m_window)
        return;
    if (m_window)
        disconnect(m_window, nullptr, this, nullptr);
    m_window = window;
    if (window)
        s_hostWindow = window;
    if (m_widget) {
        QWindow *handle = (m_widget->winId(), m_widget->windowHandle());
        if (handle) {
            handle->setParent(window);
            // keys always go to the host window, where its shortcuts work, and
            // are passed on to the widget from there (see KateEditor)
            handle->setFlag(Qt::WindowDoesNotAcceptFocus, true);
        }
    }
    if (window) {
        // ancestors moving (split views, layouts) don't tell the item: check
        // where it is whenever the scene is drawn
        connect(window, &QQuickWindow::afterAnimating, this, &NativeWidgetItem::syncGeometry);
        connect(window, &QQuickWindow::frameSwapped, this, &NativeWidgetItem::syncGeometry);
    }
    syncGeometry();
}

void NativeWidgetItem::syncGeometry()
{
    if (!m_widget)
        return;
    const bool show = m_window && isVisible() && width() > 0 && height() > 0 && !m_effectiveFrozen;
    if (!show) {
        if (m_widget->isVisible())
            m_widget->hide();
        return;
    }
    const QRect r = mapRectToScene(QRectF(0, 0, width(), qMax<qreal>(1, height() - m_bottomInset))).toAlignedRect();
    if (r != m_lastRect || !m_widget->isVisible()) {
        m_lastRect = r;
        m_widget->setGeometry(r);
    }
    if (!m_widget->isVisible())
        m_widget->show();
}
