"""Closing tabs."""


# (the same setup as gui_tab_drag.py)
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
    ts = tab_items()
    # close button of the (unmodified, background) first tab
    btn = [it for it in find_all(lambda it: it.metaObject().className().startswith("ToolButton") and it.property("text") == "Close Tab" and it.isVisible())]
    btn.sort(key=lambda b: b.mapToScene(QPointF(0, 0)).x())
    p = btn[0].mapToScene(QPointF(btn[0].width() / 2, btn[0].height() / 2)).toPoint()
    send(QEvent.MouseButtonPress, p, Qt.LeftButton); send(QEvent.MouseButtonRelease, p, Qt.NoButton)
    QTimer.singleShot(400, s2)
def s2():
    check(names() == ["MyButton.qml", "dialog.ui"], f"close button closes the tab: {names()}")
    ts = tab_items()
    p = center(ts[0])
    QGuiApplication.sendEvent(win, QMouseEvent(QEvent.MouseButtonPress, QPointF(p), QPointF(p), QPointF(win.mapToGlobal(p)), Qt.MiddleButton, Qt.MiddleButton, Qt.NoModifier))
    QGuiApplication.sendEvent(win, QMouseEvent(QEvent.MouseButtonRelease, QPointF(p), QPointF(p), QPointF(win.mapToGlobal(p)), Qt.MiddleButton, Qt.NoButton, Qt.NoModifier))
    QTimer.singleShot(400, s3)
def s3():
    check(names() == ["dialog.ui"], f"middle click closes the tab: {names()}")
    app.quit()
QTimer.singleShot(1500, s1)
