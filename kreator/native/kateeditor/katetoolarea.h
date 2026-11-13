// Kate's tool views (the LSP client's references, Kate's diagnostics list…)
// as a QML item: the plugins' tool views are tabs of one widget, shown here.

#pragma once

#include "nativeitem.h"

class KateToolArea : public NativeWidgetItem
{
    Q_OBJECT
    QML_ELEMENT

    // number of tool views (tabs)
    Q_PROPERTY(int count READ count NOTIFY countChanged)
    // the title of the tab shown
    Q_PROPERTY(QString currentTitle READ currentTitle NOTIFY countChanged)

public:
    explicit KateToolArea(QQuickItem *parent = nullptr);

    int count() const;
    QString currentTitle() const;
    // the titles of the tool views
    Q_INVOKABLE QStringList titles() const;
    // the texts listed in a tool view (its item views), for tests
    Q_INVOKABLE QStringList itemTexts(const QString &title) const;

Q_SIGNALS:
    void countChanged();
    // a plugin showed (true) or hid (false) one of its tool views
    void showRequested(bool show);

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;
    void itemChange(ItemChange change, const ItemChangeData &value) override;
    void keyPressEvent(QKeyEvent *event) override;
    void keyReleaseEvent(QKeyEvent *event) override;

private:
    void forward(QKeyEvent *event);
    void activate();
    bool m_activating = false;
};
