#include "katetoolarea.h"

#include "katehost.h"

#include <QApplication>
#include <QKeyEvent>
#include <QAbstractItemView>
#include <QTabWidget>

#include <memory>

KateToolArea::KateToolArea(QQuickItem *parent)
    : NativeWidgetItem(parent)
{
    if (!qobject_cast<QApplication *>(QCoreApplication::instance()))
        return;
    setActiveFocusOnTab(true);
    KateHost *host = KateHost::instance();
    setWidget(host->toolArea());
    connect(host, &KateHost::toolViewsChanged, this, &KateToolArea::countChanged);
    connect(host->toolArea(), &QTabWidget::currentChanged, this, &KateToolArea::countChanged);
    connect(host, &KateHost::toolAreaRequested, this, &KateToolArea::showRequested);
}

int KateToolArea::count() const
{
    return widget() ? static_cast<QTabWidget *>(widget())->count() : 0;
}

QString KateToolArea::currentTitle() const
{
    auto *tabs = static_cast<QTabWidget *>(widget());
    return tabs && tabs->currentIndex() >= 0 ? tabs->tabText(tabs->currentIndex()).remove(QLatin1Char('&')) : QString();
}

bool KateToolArea::eventFilter(QObject *watched, QEvent *event)
{
    // a click into a tool view: it gets the keyboard (via Kreator's window)
    if (event->type() == QEvent::MouseButtonPress && widget() && isUnderWidget(watched))
        activate();
    return NativeWidgetItem::eventFilter(watched, event);
}

void KateToolArea::activate()
{
    if (!hasActiveFocus() && !m_activating) {
        m_activating = true;
        forceActiveFocus(Qt::MouseFocusReason);
        m_activating = false;
    }
    QT_WARNING_PUSH
    QT_WARNING_DISABLE_DEPRECATED
    if (widget() && QApplication::activeWindow() != widget())
        QApplication::setActiveWindow(widget());
    QT_WARNING_POP
}

void KateToolArea::itemChange(ItemChange change, const ItemChangeData &value)
{
    if (change == ItemActiveFocusHasChanged && !m_activating && value.boolValue)
        activate();
    NativeWidgetItem::itemChange(change, value);
}

void KateToolArea::forward(QKeyEvent *event)
{
    QWidget *target = QApplication::focusWidget();
    if (!target || !isUnderWidget(target)) {
        auto *tabs = static_cast<QTabWidget *>(widget());
        target = tabs && tabs->currentWidget() ? tabs->currentWidget() : widget();
        if (target && target->focusWidget())
            target = target->focusWidget();
    }
    if (!target) {
        event->ignore();
        return;
    }
    std::unique_ptr<QEvent> copy(event->clone());
    QCoreApplication::sendEvent(target, copy.get());
    event->setAccepted(copy->isAccepted());
}

void KateToolArea::keyPressEvent(QKeyEvent *event)
{
    forward(event);
}

void KateToolArea::keyReleaseEvent(QKeyEvent *event)
{
    forward(event);
}

QStringList KateToolArea::titles() const
{
    QStringList out;
    auto *tabs = static_cast<QTabWidget *>(widget());
    for (int i = 0; tabs && i < tabs->count(); ++i)
        out.append(tabs->tabText(i).remove(QLatin1Char('&')));
    return out;
}

static void collect(const QAbstractItemModel *m, const QModelIndex &parent, QStringList &out, int depth = 0)
{
    // (some models (a flat list) answer every index with their rows: stop)
    if (depth > 3)
        return;
    for (int r = 0; r < m->rowCount(parent); ++r) {
        for (int c = 0; c < m->columnCount(parent); ++c) {
            const QString t = m->index(r, c, parent).data().toString();
            if (!t.isEmpty())
                out.append(t);
        }
        collect(m, m->index(r, 0, parent), out, depth + 1);
    }
}

QStringList KateToolArea::itemTexts(const QString &title) const
{
    QStringList out;
    auto *tabs = static_cast<QTabWidget *>(widget());
    for (int i = 0; tabs && i < tabs->count(); ++i) {
        if (tabs->tabText(i).remove(QLatin1Char('&')) != title)
            continue;
        const auto views = tabs->widget(i)->findChildren<QAbstractItemView *>();
        for (auto *v : views) {
            if (v->model())
                collect(v->model(), QModelIndex(), out);
        }
    }
    return out;
}
