// A QWidget shown inside a QML scene.
//
// QML scenes can't contain widgets. The widget is therefore made a native
// window and parented to the item's QQuickWindow (a child window; a subsurface
// on Wayland), and kept over the item's area. Consequence: it is always drawn
// above the QML scene, so the item shows a snapshot of the widget instead
// while QML popups overlap it ("frozen"), and leaves room at the bottom for
// notifications ("bottomInset").
//
// Used for Kate's editor (KateEditor) and for Kate's tool views (KateToolArea).

#pragma once

#include <QImage>
#include <QList>
#include <QPointer>
#include <QQuickPaintedItem>
#include <QRect>
#include <QWindow>

class QWidget;

class NativeWidgetItem : public QQuickPaintedItem
{
    Q_OBJECT
    QML_ANONYMOUS

    // while QML popups are open over the widget: show a snapshot instead of the
    // (always on top) native widget, so the popups aren't covered
    Q_PROPERTY(bool frozen READ frozen WRITE setFrozen NOTIFY frozenChanged)
    // leave this much of the item's bottom free of the native widget (for
    // notifications drawn by the host over that area)
    Q_PROPERTY(qreal bottomInset READ bottomInset WRITE setBottomInset NOTIFY bottomInsetChanged)

public:
    explicit NativeWidgetItem(QQuickItem *parent = nullptr);
    ~NativeWidgetItem() override;

    bool frozen() const;
    void setFrozen(bool frozen);
    qreal bottomInset() const;
    void setBottomInset(qreal inset);
    void paint(QPainter *painter) override;

    // for tests: the widget's contents as an image file
    Q_INVOKABLE bool grabToFile(const QString &path);
    // where the native widget is, in window coordinates (for tests)
    Q_INVOKABLE QRect nativeGeometry() const;
    Q_INVOKABLE bool nativeVisible() const;

    // Widgets whose popups (menus, completion, tooltips…) belong to Kate:
    // they get Kreator's window as transient parent (on Wayland a popup needs
    // a toplevel), and they don't freeze the embedded widgets.
    static void registerKateWidget(QWidget *root);
    static bool isKateWidget(const QObject *o);
    // the QQuickWindow embedded widgets were last shown in
    static QWindow *hostWindow();

Q_SIGNALS:
    void frozenChanged();
    void bottomInsetChanged();

protected:
    // the widget to show; the item doesn't own it
    void setWidget(QWidget *widget);
    QWidget *widget() const;
    QQuickWindow *quickWindow() const;
    bool isUnderWidget(const QObject *o) const;
    void detachWidget();

    bool eventFilter(QObject *watched, QEvent *event) override;
    void itemChange(ItemChange change, const ItemChangeData &value) override;
    void geometryChange(const QRectF &newGeometry, const QRectF &oldGeometry) override;
    void syncGeometry();

private:
    void attach(QQuickWindow *window);
    void updateFrozen();

    QPointer<QWidget> m_widget;
    QPointer<QQuickWindow> m_window;
    QRect m_lastRect;
    bool m_frozen = false;
    bool m_effectiveFrozen = false;
    QImage m_snapshot;
    qreal m_bottomInset = 0;
    // popup windows (not Kate's own) currently shown: they freeze the widget too
    QList<QPointer<QWindow>> m_popupWindows;
};
