"""Built-in editor: dynamic word wrap and mouse selection."""

PLAIN_EDITOR = True

from PySide6.QtCore import QObject, Qt, QPointF, QPoint, QEvent
from PySide6.QtGui import QWheelEvent, QMouseEvent, QGuiApplication, QPointingDevice
from PySide6.QtTest import QTest
def send(t, p, b):
    QGuiApplication.sendEvent(win, QMouseEvent(t, QPointF(p), QPointF(p), QPointF(win.mapToGlobal(p)), Qt.LeftButton if t != QEvent.MouseMove else Qt.NoButton, b, Qt.NoModifier))
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
backend.openFile(f"{OUT}/work/Long.qml")
page = win.findChild(QObject, "editorPage")
def find(pred):
    stack = [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): return it
        stack.extend(it.childItems())
def s1():
    page.setProperty("sourceMode", True)
    QTimer.singleShot(800, s2)
def s2():
    global ed, pane, flick
    ed = find(lambda it: it.metaObject().indexOfProperty("persistentSelection") >= 0 and it.property("persistentSelection"))
    pane = find(lambda it: it.metaObject().indexOfProperty("lineTops") >= 0)
    flick = ed.parentItem().parentItem().parentItem()
    print("wrap:", pane.property("wrap"), "interactive:", flick.property("interactive"))
    tops = pane.property("lineTops").toVariant(); starts = pane.property("lineStarts").toVariant()
    t = ed.property("text"); long_i = t[:t.index("deliberately")].count("\n")
    h = tops[1] - tops[0]
    check(pane.property("wrap") and tops[long_i + 1] - tops[long_i] > 2.5 * h, f"long line {long_i+1} wraps; gutter gap {tops[long_i+1]-tops[long_i]:.0f}px vs {h:.0f}px")
    # where does line 30 start on screen vs its number label
    win.grabWindow().save(f"{OUT}/wrap.png")
    # vertical mouse drag selection (same x)
    r1 = ed.positionToRectangle(starts[9]); r2 = ed.positionToRectangle(starts[15])
    x = 60
    p1 = ed.mapToScene(QPointF(x, r1.y() + r1.height() / 2)).toPoint()
    p2 = ed.mapToScene(QPointF(x, r2.y() + r2.height() / 2)).toPoint()
    send(QEvent.MouseButtonPress, p1, Qt.LeftButton)
    for k in range(1, 11):
        send(QEvent.MouseMove, QPoint(p1.x(), p1.y() + (p2.y() - p1.y()) * k // 10), Qt.LeftButton)
    send(QEvent.MouseButtonRelease, p2, Qt.NoButton)
    sel = ed.property("selectedText")
    print("sel1", ed.property("selectionStart"), ed.property("selectionEnd"), "focus", ed.hasActiveFocus(), p1, p2)
    check(sel.count("\n") >= 5 or sel.count(" ") >= 5, f"vertical drag selects {max(sel.count(chr(10)), sel.count(chr(0x2029)))} line breaks")
    # wheel still scrolls
    y0 = flick.property("contentY")
    pos = ed.mapToScene(QPointF(100, 100))
    ev = QWheelEvent(pos, pos, QPoint(0, 0), QPoint(0, -360), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QGuiApplication.sendEvent(win, ev)
    QTimer.singleShot(400, lambda: s3(y0))
def s3(y0):
    check(flick.property("contentY") > y0, f"wheel scrolls ({y0:.0f} -> {flick.property('contentY'):.0f})")
    flick.setProperty("contentY", 600)
    # drag past the top edge (into the toolbar): auto-scroll up + selection grows
    global p1
    p1 = flick.mapToScene(QPointF(60, 100)).toPoint()
    send(QEvent.MouseButtonPress, p1, Qt.LeftButton)
    bottom = flick.mapToScene(QPointF(60, -25)).toPoint()
    for k in range(1, 6):
        send(QEvent.MouseMove, QPoint(p1.x(), p1.y() + (bottom.y() - p1.y()) * k // 5), Qt.LeftButton)
    sp = ed.findChild(QObject, "selectPoint")
    print("pointhandler active during drag:", sp.property("active") if sp else "not found")
    QTimer.singleShot(1200, lambda: s4(bottom))
def s4(bottom):
    send(QEvent.MouseButtonRelease, bottom, Qt.NoButton)
    sel = ed.property("selectedText")
    check(flick.property("contentY") < 400, f"auto-scroll while dragging above (contentY {flick.property('contentY'):.0f})")
    lines = max(sel.count("\n"), sel.count(" "))
    check(lines > 20, f"selection extended to {lines} lines")
    # F10 toggles wrap
    ed.forceActiveFocus()
    QTest.keyClick(win, Qt.Key_F10)
    QTimer.singleShot(300, s5)
def s5():
    print("wrap after F10:", pane.property("wrap"), "focus", ed.hasActiveFocus())
    tops = pane.property("lineTops").toVariant()
    check(not pane.property("wrap") and abs((tops[30] - tops[29]) - (tops[1] - tops[0])) < 0.5, "F10 turns wrap off, gutter evenly spaced")
    app.quit()
QTimer.singleShot(1000, s1)
