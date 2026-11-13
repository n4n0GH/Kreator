"""Moved signal flow nodes keep their places across a restart; Reset Layout."""


import json
from PySide6.QtCore import QObject, QPointF, QPoint, Qt
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
def nodes(): return {i.objectName()[9:]: i for i in items(lambda it: it.objectName().startswith("flowNode_")) if i.isVisible()}
def scene(it, fx=0.3): return it.mapToScene(QPointF(it.width() * fx, 8)).toPoint()  # title bar
def drag(a, b, steps=12):
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, steps + 1):
        QTest.mouseMove(win, a + (b - a) * i / steps); QTest.qWait(15)
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, b)

# --- run 0 ---
import os
import shutil; shutil.copy(f"{P}/dialog.orig", f"{P}/dialog.ui")
backend.openFolder(P); backend.openFile(f"{P}/dialog.ui"); backend.openFile(f"{P}/Flow.qml")
page.setProperty("flowMode", True)
def s1():
    pane = items(lambda i: i.objectName() == "flowPane")[0]; pane.setProperty("zoom", 1.0)
    QTimer.singleShot(200, s1b)
def s1b():
    ns = nodes()
    a, b = ns["advanced"], ns["“Save”"]
    globals()["want"] = {"status": (a.x() + 120, a.y() + 150), "save": (b.x() + 100, b.y() + 130)}
    drag(scene(a), scene(a) + QPoint(120, 150)); QTest.qWait(100)
    drag(scene(b), scene(b) + QPoint(100, 130))
    QTimer.singleShot(200, s2)
def s2():
    ns = nodes()
    check(abs(ns["advanced"].x() - want["status"][0]) < 3 and abs(ns["advanced"].y() - want["status"][1]) < 3, "status moved")
    check(abs(ns["“Save”"].y() - want["save"][1]) < 3, "the Save button (no id) moved")
    json.dump(want, open(f"{OUT}/flowpos.want", "w"))
    backend.switchTo(f"{P}/dialog.ui")
    QTimer.singleShot(400, s3)
def s3():
    cb = nodes()["checkBox"]; globals()["cbwant"] = (cb.x(), cb.y() + 200)
    drag(scene(cb), scene(cb) + QPoint(0, 200))
    QTimer.singleShot(200, s4)
def s4():
    json.dump(cbwant, open(f"{OUT}/flowpos.cb", "w"))
    QTimer.singleShot(300, lambda: (win.close(), QTimer.singleShot(500, app.quit)))
QTimer.singleShot(1500, s1)

# --- run 1 ---
import os
want = json.load(open(f"{OUT}/flowpos.want")); cbwant = json.load(open(f"{OUT}/flowpos.cb"))
data = json.load(open(os.environ["XDG_DATA_HOME"] + "/kreator/session.json"))
check(any("flowPositions" in d for d in data["docs"]), "positions stored in session.json")
check(backend.currentKey.endswith("dialog.ui"), f"session restored ({backend.currentKey})")
page.setProperty("flowMode", True)
def s1():
    items(lambda i: i.objectName() == "flowPane")[0].setProperty("zoom", 1.0)
    QTimer.singleShot(200, s2)
def s2():
    cb = nodes()["checkBox"]
    check(abs(cb.x() - cbwant[0]) < 3 and abs(cb.y() - cbwant[1]) < 3, f"form: moved widget back in its place ({cb.y()} vs {cbwant[1]})")
    backend.switchTo(f"{P}/Flow.qml")
    QTimer.singleShot(400, s3)
def s3():
    ns = nodes()
    check(abs(ns["advanced"].x() - want["status"][0]) < 3 and abs(ns["advanced"].y() - want["status"][1]) < 3, "QML: object with an id in its place")
    check(abs(ns["“Save”"].y() - want["save"][1]) < 3 and abs(ns["“Save”"].x() - want["save"][0]) < 3, "QML: object without an id in its place")
    reset = [i for i in items(lambda it: it.objectName() == "flowResetLayout")][0]
    reset.clicked.emit()
    QTimer.singleShot(200, s4)
def s4():
    check(abs(nodes()["advanced"].y() - want["status"][1]) > 50, "Reset Layout still works")
    check(not backend.flowPositions(), "and forgets them")
    backend.discardAll(); QTimer.singleShot(300, app.quit)
QTimer.singleShot(1500, s1)
