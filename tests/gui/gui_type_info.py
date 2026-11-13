"""Go to definition on a C++ type shows its description."""

KATE = True
NEEDS = ['qmlls']

import sys as _s, traceback as _t, time, shutil
_s.excepthook = lambda *a: (_t.print_exception(*a), app.exit(3))
import warnings; warnings.simplefilter("ignore")
from PySide6.QtCore import QObject, Qt, QEvent, QPointF, QPoint, QMetaObject
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
page = win.findChild(QObject, "editorPage")
P = f"{OUT}/proj"
shutil.copy(f"{P}/Types.orig", f"{P}/Types.qml")
def find_all(pred):
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems() if hasattr(it, 'childItems') else [])
    return out
def popup():
    return win.findChild(QObject, "typeInfoPopup")
backend.openFolder(P); backend.openFile(f"{P}/Types.qml"); page.setProperty("sourceMode", True)
def ctrl_click(ed, line, col):
    v = [w for w in QApplication.allWidgets() if w.metaObject().className() == "KTextEditor::ViewPrivate"][0]
    inner = [c for c in v.findChildren(QWidget) if c.metaObject().className() == "KateViewInternal"][0]
    p = ed.positionBelow(line, col)
    vp = QPoint(int(p.x()) + 3, int(p.y()) - 8)
    ip = inner.mapFrom(v, vp)
    for tp in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        QApplication.sendEvent(inner, QMouseEvent(tp, QPointF(ip), QPointF(inner.mapToGlobal(ip)), Qt.LeftButton,
                               Qt.LeftButton if tp == QEvent.MouseButtonPress else Qt.NoButton, Qt.ControlModifier))
def s1():
    ed = find_all(lambda it: it.objectName() == "kateEditor")[0]; globals()["ed"] = ed
    QMetaObject.invokeMethod(ed, "focusEditor")
    QTimer.singleShot(3000, s2)
def s2():
    ctrl_click(ed, 4, 6)    # Rectangle
    QTimer.singleShot(800, s3)
def s3():
    pp = popup()
    check(pp is not None and pp.property("visible"), "Ctrl+click on Rectangle shows its description")
    if pp:
        info = pp.property("info")
        check(info.get("name") == "Rectangle" and info.get("module") == "QtQuick", f"Rectangle from QtQuick ({info.get('name')}, {info.get('module')})")
        check("color" in [p["name"] for p in info["properties"]], "own properties (color…)")
        check([b["name"] for b in info["bases"]][:1] == ["Item"], f"inherits Item ({[b['name'] for b in info['bases']]})")
        btn = find_all(lambda it: it.objectName() == "inheritedFromItem")
        check(btn and btn[0].property("visible"), "Item's members are a collapsed section")
        check(ed.property("frozen") or not ed.nativeVisible(), "the editor shows a snapshot under the popup")
        win.grabWindow().save(f"{OUT}/typepop.png")
        if btn:
            btn[0].clicked.emit()
        QTimer.singleShot(300, lambda: s3b(pp))
def s3b(pp):
    win.grabWindow().save(f"{OUT}/typepop2.png")
    pp.close()
    QTimer.singleShot(300, s4)
def s4():
    check(ed.nativeVisible(), "closed: live editor back")
    ed.setCursorPosition(7, 15)   # Kirigami.Icon via Kate's action
    check(ed.triggerAction("lspclient_find_definition"), "go to definition (Kate's action)")
    QTimer.singleShot(800, s5)
def s5():
    pp = popup(); info = pp.property("info")
    check(pp.property("visible") and info.get("name") == "Icon" and "org.kde.kirigami" in info.get("module", ""), f"Kirigami.Icon described ({info.get('module')})")
    pp.close()
    ed.setCursorPosition(10, 6)   # MyButton: written in QML -> opens its file
    ed.triggerAction("lspclient_find_definition")
    QTimer.singleShot(3000, s6)
def s6():
    check(not popup().property("visible"), "no popup for a type written in QML")
    check(backend.property("fileName") == "MyButton.qml", "its file opens instead")
    backend.discardAll()
    QTimer.singleShot(300, app.quit)
QTimer.singleShot(1500, s1)
