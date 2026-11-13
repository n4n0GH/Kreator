"""Kate's editor: notifications, popups and other details."""

KATE = True

import sys as _s, traceback as _t, os
_s.excepthook = lambda *a: (_t.print_exception(*a), app.exit(3))
import warnings; warnings.simplefilter("ignore")
from PySide6.QtCore import QObject, Qt, QMetaObject, QPoint, QEvent
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QApplication, QWidget, QMenu
from PySide6.QtTest import QTest
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
page = win.findChild(QObject, "editorPage")
P = f"{OUT}/proj"
def find_all(pred):
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems())
    return out
cfg = os.environ["XDG_CONFIG_HOME"]
kreatorrc = open(f"{cfg}/kreatorrc").read() if os.path.exists(f"{cfg}/kreatorrc") else ""
check("Line Height Multiplier=1.7" in kreatorrc, "Kate's editor settings were taken from katerc at start")
backend.openFolder(P)
backend.openFile(f"{P}/Main.qml")
page.setProperty("sourceMode", True)
def s1():
    ed = find_all(lambda it: it.objectName() == "kateEditor")[0]; globals()["ed"] = ed
    h0 = ed.nativeGeometry().height()
    win.showPassiveNotification("A notification over the editor", "short", "", None)
    QTimer.singleShot(400, lambda: s2(ed, h0))
def s2(ed, h0):
    h1 = ed.nativeGeometry().height()
    check(ed.nativeVisible() and h1 < h0, f"a notification shortens the live editor ({h0} -> {h1})")
    win.grabWindow().save(f"{OUT}/kate_notif.png")
    QTimer.singleShot(7000, lambda: s3(ed, h0))
def s3(ed, h0):
    check(ed.nativeGeometry().height() == h0, "full height again when it's gone")
    v = [w for w in QApplication.allWidgets() if w.metaObject().className() == "KTextEditor::ViewPrivate"][0]
    inner = [c for c in v.findChildren(QWidget) if c.metaObject().className() == "KateViewInternal"][0]
    QApplication.sendEvent(inner, QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(40, 40), inner.mapToGlobal(QPoint(40, 40))))
    QTimer.singleShot(400, lambda: s4(ed))
def s4(ed):
    menus = [m for m in QApplication.topLevelWidgets() if isinstance(m, QMenu) and m.isVisible()]
    for m in menus: m.close()
    v = [w for w in QApplication.allWidgets() if w.metaObject().className() == "KTextEditor::ViewPrivate"][0]
    cm = [m for m in QApplication.allWidgets() if isinstance(m, QMenu) and len(m.actions()) > 5 and any(a.objectName() == "edit_undo" for a in m.actions())]
    names = [a.text().replace("&", "") for a in cm[0].actions() if a.isVisible()] if cm else []
    check(bool(cm) and not any(n.startswith("Save") or n.startswith("Reload") for n in names), f"Kate's menu has no Save/Reload (Kreator's job): {[n for n in names if n][:10]}")
    check(not ed.property("frozen"), "the editor isn't frozen")
    # settings changed here go back to Kate (as after Kate's settings dialog)
    QMetaObject.invokeMethod(ed, "setProperty", Qt.DirectConnection)  # no-op, keep ed alive
    app.quit()
QTimer.singleShot(1500, s1)
