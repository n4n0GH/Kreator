"""Removing an unused member from a red port's menu, the menu's place, undo."""


import sys as _s, traceback as _t
_s.excepthook = lambda *a: (_t.print_exception(*a), app.exit(3))
import warnings; warnings.simplefilter("ignore")
from PySide6.QtCore import QObject, QPointF, Qt
from PySide6.QtTest import QTest
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
page = win.findChild(QObject, "editorPage")
P = f"{OUT}/flowproj"
def items(pred):
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems())
    return out
def named(prefix):
    return [i for i in items(lambda it: it.objectName().startswith(prefix)) if i.isVisible()]
def fp(): return items(lambda it: it.objectName() == "flowPane")[0]
def port(node, name): return [i for i in named("flowPort_") if i.objectName() == f"flowPort_{node}_{name}"]
def click(q):
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, q.mapToScene(QPointF(q.width()/2, q.height()/2)).toPoint())
backend.openFolder(P); backend.openFile(f"{P}/Flow.qml")
page.setProperty("flowMode", True)
def text(): return backend.adapter.text()
def s1():
    fp().setProperty("zoom", 1.0)
    from PySide6.QtCore import QTimer as T
    T.singleShot(400, s2)
def s2():
    q = port("root", "lonely()")
    check(bool(q), "red lonely() port shown")
    click(q[0])
    QTimer.singleShot(500, s3)
def s3():
    rm = named("flowRemoveMember")
    check(bool(rm), "clicking it opens the remove menu")
    if rm:
        check("lonely()" in rm[0].property("text"), f"menu item: {rm[0].property('text')}")
        q = port("root", "lonely()")[0]
        pr = q.mapToScene(QPointF(q.width(), q.height() / 2))
        mi = rm[0].mapToScene(QPointF(0, rm[0].height() / 2))
        check(0 < mi.x() - pr.x() < 40 and abs(mi.y() - pr.y()) < 30, f"the menu opens beside the port (menu {mi.x():.0f},{mi.y():.0f} port end {pr.x():.0f},{pr.y():.0f})")
        win.grabWindow().save(f"{OUT}/flowremove1.png")
        click(rm[0])
    QTimer.singleShot(800, s4)
def s4():
    check("function lonely" not in text(), "the function is removed from the source")
    check(not port("root", "lonely()"), "its port is gone")
    check(bool(port("root", "save()")), "other ports remain")
    q = port("root", "leftover")
    click(q[0])
    QTimer.singleShot(500, s5)
def s5():
    rm = named("flowRemoveMember")
    check(bool(rm) and "Property" in rm[0].property("text"), "property remove menu")
    click(rm[0])
    QTimer.singleShot(800, s6)
def s6():
    check("leftover" not in text() and not port("root", "leftover"), "the property is removed")
    backend.undo(); backend.undo()
    QTimer.singleShot(800, s7)
def s7():
    check("function lonely" in text() and "property int leftover" in text(), "undo brings both back")
    check(bool(port("root", "lonely()")) and bool(port("root", "leftover")), "and their ports")
    # a handler port (red, not removable): clicking still jumps to its code
    backend.discardAll()
    QTimer.singleShot(300, app.quit)
QTimer.singleShot(1500, s1)
