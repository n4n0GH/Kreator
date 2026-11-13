"""Reordering tabs by dragging."""


from PySide6.QtCore import QObject, Qt, QEvent, QPointF, QPoint, QMetaObject, Q_ARG
from PySide6.QtGui import QMouseEvent, QGuiApplication
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
def v(x): return x.toVariant() if hasattr(x, "toVariant") else x
P = f"{OUT}/proj"
def names(): return [d["name"] for d in v(backend.property("openDocuments"))]
def current(): return next(d["name"] for d in v(backend.property("openDocuments")) if d["current"])
def find_all(pred):
    out = []; stack = [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems())
    return out
def tab_items():
    ts = find_all(lambda it: it.metaObject().className().startswith("TabButton") and it.metaObject().indexOfProperty("dragOffset") >= 0)
    return sorted(ts, key=lambda t: t.mapToScene(QPointF(0, 0)).x())
def send(t, p, b):
    QGuiApplication.sendEvent(win, QMouseEvent(t, QPointF(p), QPointF(p), QPointF(win.mapToGlobal(p)), Qt.LeftButton if t != QEvent.MouseMove else Qt.NoButton, b, Qt.NoModifier))
def center(t):
    return t.mapToScene(QPointF(t.width() / 2, t.height() / 2)).toPoint()
backend.openFolder(P)
for f in ("Main.qml", "MyButton.qml", "forms/dialog.ui"):
    QMetaObject.invokeMethod(win, "switchFile", Q_ARG("QVariant", f"{P}/{f}"))
def drag(src, dst_x, steps=12, release=True):
    a = center(src); b = QPoint(dst_x, a.y())
    send(QEvent.MouseButtonPress, a, Qt.LeftButton)
    for k in range(1, steps + 1):
        send(QEvent.MouseMove, QPoint(a.x() + (b.x() - a.x()) * k // steps, a.y()), Qt.LeftButton)
    if release:
        send(QEvent.MouseButtonRelease, b, Qt.NoButton)
def s1():
    print("start:", names())
    ts = tab_items()
    last = ts[-1]
    drag(ts[0], int(last.mapToScene(QPointF(last.width() - 5, 0)).x()) + 10)   # Main -> end
    QTimer.singleShot(400, s2)
def s2():
    print("after drag to end:", names())
    check(names() == ["MyButton.qml", "dialog.ui", "Main.qml"], "dragging the first tab to the end")
    check(current() == "dialog.ui", "dragging does not switch documents")
    ts = tab_items()
    drag(ts[2], int(ts[0].mapToScene(QPointF(3, 0)).x()), release=False)   # Main -> front, hold
    QTimer.singleShot(200, s3)
def s3():
    marker = find_all(lambda it: it.metaObject().className() == "QQuickRectangle" and it.width() == 3 and it.isVisible())
    check(len(marker) == 1, "drop marker shown while dragging")
    win.grabWindow().save(f"{OUT}/tabdrag.png")
    ts = tab_items()
    p = QPoint(int(ts[0].mapToScene(QPointF(3, 0)).x()), center(ts[0]).y())
    send(QEvent.MouseButtonRelease, p, Qt.NoButton)
    QTimer.singleShot(400, s4)
def s4():
    print("after drag to front:", names())
    check(names() == ["Main.qml", "MyButton.qml", "dialog.ui"], "dragging the last tab to the front")
    # small move (below the drag threshold) is a click: switches
    ts = tab_items()
    a = center(ts[1])
    send(QEvent.MouseButtonPress, a, Qt.LeftButton)
    send(QEvent.MouseMove, QPoint(a.x() + 2, a.y()), Qt.LeftButton)
    send(QEvent.MouseButtonRelease, QPoint(a.x() + 2, a.y()), Qt.NoButton)
    QTimer.singleShot(500, s5)
def s5():
    check(current() == "MyButton.qml" and names() == ["Main.qml", "MyButton.qml", "dialog.ui"], "a click still switches tabs without reordering")
    app.quit()
QTimer.singleShot(1500, s1)
