"""Editing a form's connections in the signal flow view: drag to connect, the dialog, edit, delete, undo."""


import sys as _s, traceback as _t
_s.excepthook = lambda *a: (_t.print_exception(*a), app.exit(3))
import warnings; warnings.simplefilter("ignore")
import shutil
from PySide6.QtCore import QObject, QPointF, QPoint, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
page = win.findChild(QObject, "editorPage")
P = f"{OUT}/flowproj"
shutil.copy(f"{P}/dialog.orig", f"{P}/dialog.ui")
def items(pred):
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems())
    return out
def named(n): return [i for i in items(lambda it: it.objectName() == n) if i.isVisible()]
def nodes(): return {i.objectName()[9:]: i for i in items(lambda it: it.objectName().startswith("flowNode_")) if i.isVisible()}
def scene(it, x=None, y=None):
    return it.mapToScene(QPointF(it.width()/2 if x is None else x, it.height()/2 if y is None else y)).toPoint()
def fp(): return named("flowPane")[0]
def drag(a, b, steps=12):
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, steps + 1):
        QTest.mouseMove(win, a + (b - a) * i / steps); QTest.qWait(15)
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, b)
win.resize(1300, 800)   # the same room to scroll everywhere
backend.openFolder(P); backend.openFile(f"{P}/dialog.ui")
page.setProperty("flowMode", True)
def dot(sender, sig, receiver, slot):
    n = f"flowEdge_u{sender}.{sig}_u{receiver}.{slot}"
    return [i for i in items(lambda it: it.objectName() == n and it.isVisible())]
def s1():
    pane = fp(); pane.setProperty("zoom", 1.0)
    ns = nodes()
    check(sorted(ns) == ["Dialog", "buttonBox", "checkBox", "lineEdit"], f"widgets {sorted(ns)}")
    flick = named("flowFlick")[0]
    z0 = min(1.6, 1.3 * flick.width() / pane.property("canvasSize").width())
    globals()["Z0"] = z0
    pane.setProperty("zoom", z0)
    QTimer.singleShot(200, s1z)
def s1z():
    flick = named("flowFlick")[0]
    canvas = nodes()["Dialog"].parentItem()
    at = flick.mapToScene(QPointF(flick.width() * 0.6, flick.height() * 0.5))
    under = canvas.mapFromScene(at)
    QApplication.sendEvent(win, QWheelEvent(at, QPointF(win.mapToGlobal(at)), QPoint(), QPoint(0, 120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
    QTimer.singleShot(200, lambda: s1b(canvas, at, under))
def s1b(canvas, at, under):
    pane = fp(); z = pane.property("zoom")
    check(z > Z0 * 1.1, f"the wheel zooms, no modifier needed ({Z0:.2f} -> {z:.2f})")
    now = canvas.mapFromScene(at)
    check(abs(now.x() - under.x()) < 4 and abs(now.y() - under.y()) < 4, f"around the pointer ({under} -> {now})")
    # a touchpad: two fingers scroll, a pinch zooms
    from PySide6.QtGui import QPointingDevice, QInputDevice, QNativeGestureEvent
    tp = QPointingDevice("touchpad", 4242, QInputDevice.DeviceType.TouchPad, QPointingDevice.PointerType.Finger,
                         QInputDevice.Capability.Position | QInputDevice.Capability.Scroll, 5, 2)
    globals()["TP"] = tp
    pane.setProperty("zoom", 2.0)
    fl = named("flowFlick")[0]; fl.setProperty("contentX", 0); QTest.qWait(100)
    room = fl.property("contentWidth") - fl.width()
    zz = pane.property("zoom")
    QApplication.sendEvent(win, QWheelEvent(at, QPointF(win.mapToGlobal(at)), QPoint(-60, 0), QPoint(-480, 0), Qt.NoButton,
                                            Qt.NoModifier, Qt.NoScrollPhase, False, Qt.MouseEventNotSynthesized, tp))
    check(room > 20 and abs(fl.property("contentX") - min(60, room)) < 1 and pane.property("zoom") == zz,
          f"two-finger scrolling on a touchpad scrolls sideways ({fl.property('contentX')}), no zoom ({pane.property('zoom'):.2f})")
    QApplication.sendEvent(win, QWheelEvent(at, QPointF(win.mapToGlobal(at)), QPoint(-30, -20), QPoint(-240, -160), Qt.NoButton,
                                            Qt.NoModifier, Qt.NoScrollPhase, False, Qt.MouseEventNotSynthesized, tp))
    check(abs(fl.property("contentX") - min(90, room)) < 1 if room > 90 else fl.property("contentX") == room,
          f"and diagonally, once ({fl.property('contentX')} of {room})")
    pane.setProperty("zoom", 1.0); zz = 1.0
    QApplication.sendEvent(win, QWheelEvent(at, QPointF(win.mapToGlobal(at)), QPoint(0, 15), QPoint(0, 120), Qt.NoButton,
                                            Qt.ControlModifier, Qt.NoScrollPhase, False, Qt.MouseEventNotSynthesized, tp))
    check(pane.property("zoom") > zz * 1.05, f"with Ctrl it zooms ({pane.property('zoom'):.2f})")
    pane.setProperty("zoom", 1.0)
    for t, v in [(Qt.BeginNativeGesture, 0)] + [(Qt.ZoomNativeGesture, 0.06)] * 5 + [(Qt.EndNativeGesture, 0)]:
        QApplication.sendEvent(win, QNativeGestureEvent(t, tp, 2, at, at, QPointF(win.mapToGlobal(at)), v, QPointF(), 7))
    check(pane.property("zoom") > 1.2, f"touchpad pinch zooms ({pane.property('zoom'):.2f})")
    pane.setProperty("zoom", 1.0)
    QTimer.singleShot(200, s2)
def s2():
    cb = nodes()["checkBox"]; x0, y0 = cb.x(), cb.y()
    a = cb.mapToScene(QPointF(cb.width() * 0.3, 8)).toPoint()   # the title bar
    drag(a, a + QPoint(0, 160))
    QTimer.singleShot(200, lambda: s3(x0, y0))
def s3(x0, y0):
    cb = nodes()["checkBox"]
    check(abs(cb.y() - y0 - 160) < 8 and abs(cb.x() - x0) < 8, f"drag moves the object ({y0} -> {cb.y()})")
    check(named("flowResetLayout")[0].property("enabled"), "Reset Layout enabled")
    win.grabWindow().save(f"{OUT}/fedit1.png")
    # connect: drag from checkBox's handle to Dialog
    QTest.mouseMove(win, scene(cb)); QTest.qWait(100)
    h = named("flowHandle_checkBox")
    check(bool(h), "handle shown on hover")
    d = nodes()["Dialog"]
    drag(scene(h[0]), scene(d))
    QTimer.singleShot(500, s4)
def s4():
    dlg = win.findChild(QObject, "connectionDialog") or [o for o in items(lambda it: it.objectName() == "connectionDialog")]
    dlg = dlg if isinstance(dlg, QObject) else dlg[0]
    check(dlg.property("visible"), "dropping on a widget opens the connection dialog")
    check(dlg.property("senderName") == "checkBox" and dlg.property("receiverName") == "Dialog",
          f"sender/receiver filled in ({dlg.property('senderName')}, {dlg.property('receiverName')})")
    sigs = backend.uiSignals("checkBox"); slots = backend.uiSlots("Dialog", "clicked()")
    check("toggled(bool)" in sigs and "reject()" in slots and "setEnabled(bool)" not in slots, "signals; only compatible slots")
    sb = named("connSignal")[0]; sb.setProperty("editText", "clicked()")
    QMetaObject = __import__("PySide6.QtCore", fromlist=["QMetaObject"]).QMetaObject
    QMetaObject.invokeMethod(dlg, "refreshSlots", Qt.DirectConnection, "reject()") if False else dlg.refreshSlots("reject()") if hasattr(dlg, "refreshSlots") else None
    named("connSlot")[0].setProperty("editText", "reject()")
    check(dlg.property("valid"), "valid")
    win.grabWindow().save(f"{OUT}/fedit2.png")
    dlg.accept()
    QTimer.singleShot(400, s5)
def s5():
    t = backend.property("sourceText")
    check("<sender>checkBox</sender>" in t and "<slot>reject()</slot>" in t, "connection added to the form")
    check(backend.property("canUndo") and backend.property("modified"), "unsaved, undoable")
    check(bool(dot("checkBox", "clicked()", "Dialog", "reject()")), "new arrow shown: clicked() -> reject()")
    ports = [i.objectName() for i in items(lambda it: it.objectName().startswith("flowPort_") and it.isVisible())]
    check("flowPort_checkBox_clicked()" in ports and "flowPort_Dialog_reject()" in ports, "with its ports")
    # an arrow's dot -> menu -> delete
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, scene(dot("buttonBox", "accepted()", "Dialog", "accept()")[0]))
    QTimer.singleShot(400, s6)
def s6():
    menu = [o for o in win.findChildren(QObject) if o.objectName() == "flowEdgeMenu"] or items(lambda it: it.objectName() == "flowEdgeMenu")
    m = menu[0]
    check(m.property("visible"), "clicking an arrow's dot opens its menu")
    it = [i for i in items(lambda it: it.property("text") == "Delete Connection" and it.isVisible())][0]
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, scene(it))
    QTimer.singleShot(400, s7)
def s7():
    t = backend.property("sourceText")
    check("accept()" not in t.replace("reject", ""), "connection deleted")
    backend.undo()
    QTimer.singleShot(300, s8)
def s8():
    check("<slot>accept()</slot>" in backend.property("sourceText"), "undo brings it back")
    check(bool(dot("buttonBox", "accepted()", "Dialog", "accept()")), "and its arrow")
    check(nodes()["checkBox"].y() > 150, "moved object stays where it was put after edits")
    named("flowResetLayout")[0].clicked.emit()
    QTimer.singleShot(200, s9)
def s9():
    check(not named("flowResetLayout")[0].property("enabled"), "Reset Layout puts it back")
    # the body of an object doesn't move it
    ln = nodes()["lineEdit"]; y0 = ln.y()
    b = ln.mapToScene(QPointF(ln.width() * 0.3, ln.height() - 6)).toPoint(); drag(b, b + QPoint(0, 80))
    check(abs(nodes()["lineEdit"].y() - y0) < 1, "dragging the body doesn't move the object")
    # the wheel zooms over an object and over an arrow's dot too
    for what, it in (("an object", nodes()["Dialog"]), ("a dot", dot("buttonBox", "accepted()", "Dialog", "accept()")[0])):
        z = fp().property("zoom"); at = it.mapToScene(QPointF(it.width() / 2, it.height() / 2))
        QApplication.sendEvent(win, QWheelEvent(at, QPointF(win.mapToGlobal(at)), QPoint(), QPoint(0, -120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
        check(fp().property("zoom") < z, f"the wheel over {what} zooms ({z:.2f} -> {fp().property('zoom'):.2f})")
    # dragging the background scrolls (zoomed in)
    fp().setProperty("zoom", 2.0)
    QTimer.singleShot(200, s9b)
def s9b():
    fl = named("flowFlick")[0]
    a = fl.mapToScene(QPointF(fl.width() - 30, fl.height() - 30)).toPoint()
    x0 = fl.property("contentX"); drag(a, a + QPoint(-150, -100))
    check(fl.property("contentX") > x0 + 100, f"dragging the background scrolls ({x0} -> {fl.property('contentX')})")
    fp().setProperty("zoom", 1.0)
    win.grabWindow().save(f"{OUT}/fedit3.png")
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, scene(dot("checkBox", "clicked()", "Dialog", "reject()")[0]))
    QTimer.singleShot(400, s10)
def s10():
    it = [i for i in items(lambda it: it.property("text") == "Edit Connection…" and it.isVisible())][0]
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, scene(it))
    QTimer.singleShot(400, s11)
def s11():
    dlg = [o for o in items(lambda it: it.objectName() == "connectionDialog")]
    dlg = dlg[0] if dlg else win.findChild(QObject, "connectionDialog")
    check(dlg.property("visible") and dlg.property("index") >= 0, "Edit Connection… opens the dialog")
    check(named("connSignal")[0].property("editText") == "clicked()" and dlg.property("receiverName") == "Dialog", "with the connection filled in")
    named("connSlot")[0].setProperty("editText", "accept()")
    dlg.accept()
    QTimer.singleShot(400, s12)
def s12():
    t = backend.property("sourceText")
    check("<signal>clicked()</signal>\n   <receiver>Dialog</receiver>\n   <slot>accept()</slot>" in t, "edited in the form")
    QTimer.singleShot(300, s13)
def s13():
    # drag from a signal's connector onto a slot: both filled in
    out = [i for i in items(lambda it: it.objectName() == "flowOut_checkBox_toggled(bool)" and it.isVisible())][0]
    slot = [i for i in items(lambda it: it.objectName() == "flowPort_lineEdit_setEnabled(bool)" and it.isVisible())][0]
    QTest.mouseMove(win, scene(out)); QTest.qWait(100)
    drag(scene(out), scene(slot))
    QTimer.singleShot(500, s14)
def s14():
    dlg = [o for o in items(lambda it: it.objectName() == "connectionDialog")]
    dlg = dlg[0] if dlg else win.findChild(QObject, "connectionDialog")
    check(dlg.property("visible") and dlg.property("index") < 0, "dragging a signal's connector opens the dialog")
    check(dlg.property("senderName") == "checkBox" and dlg.property("signalText") == "toggled(bool)"
          and dlg.property("receiverName") == "lineEdit" and dlg.property("slotText") == "setEnabled(bool)",
          f"with the signal and the slot dropped on ({dlg.property('signalText')} -> {dlg.property('receiverName')}.{dlg.property('slotText')})")
    dlg.reject()
    backend.discardAll(); QTimer.singleShot(300, app.quit)
QTimer.singleShot(1500, s1)
