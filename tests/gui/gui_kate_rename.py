"""Rename in Kate's editor, also in other files, as unsaved changes."""

KATE = True
NEEDS = ['qmlls']

import sys as _s, traceback as _t, time
_s.excepthook = lambda *a: (_t.print_exception(*a), app.exit(3))
import warnings; warnings.simplefilter("ignore")
from PySide6.QtCore import QObject, Qt, QEvent, QMetaObject
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QInputDialog, QDialog, QLineEdit
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
def key(k, mods=Qt.NoModifier, text=""):
    for tp in (QEvent.KeyPress, QEvent.KeyRelease):
        QApplication.sendEvent(win, QKeyEvent(tp, k, mods, text))
def wait(pred, timeout, then, what):
    t0 = time.time()
    def tick():
        try: ok = pred()
        except Exception: ok = False
        if ok: then()
        elif time.time() - t0 > timeout:
            check(False, f"{what} (timed out)"); then()
        else: QTimer.singleShot(200, tick)
    tick()
backend.openFolder(P)
backend.openFile(f"{P}/Main.qml")
backend.openFile(f"{P}/MyButton.qml")
page.setProperty("sourceMode", True)
def s1():
    ed = find_all(lambda it: it.objectName() == "kateEditor")[0]; globals()["ed"] = ed
    QMetaObject.invokeMethod(ed, "focusEditor")
    lines = ed.property("text").split("\n")
    ln = next(i for i, l in enumerate(lines) if "property string caption" in l)
    ed.setCursorPosition(ln, lines[ln].index("caption") + 1)
    QTimer.singleShot(3000, s2)
def answer():
    dlgs = [w for w in QApplication.topLevelWidgets() if isinstance(w, QInputDialog) and w.isVisible()]
    check(bool(dlgs), "F2 asks for the new name (Kate's dialog)")
    if dlgs:
        dlgs[0].setTextValue("label")
        dlgs[0].accept()
def s2():
    QTimer.singleShot(1500, answer)
    key(Qt.Key_F2)          # modal dialog: returns after answer()
    wait(lambda: "property string label" in globals()["ed"].property("text"), 15, s3, "renamed in the current file")
def s3():
    ed = globals()["ed"]
    t = ed.property("text")
    check("property string label" in t and "text: label" in t, "renamed in the current file (declaration and use)")
    check(page.property("sourcePane").property("dirty"), "as an edit to apply (like typing)")
    docs = {d["name"] if "name" in d else d.get("key"): d for d in backend.openDocuments}
    main = [d for d in backend.openDocuments if str(d.get("key", "")).endswith("Main.qml")]
    check(main and main[0].get("modified"), f"Main.qml changed too, unsaved ({main[0] if main else None})")
    check(backend.property("fileName") == "MyButton.qml", "still showing MyButton.qml")
    # Main.qml's text in Kreator
    page.commitSource()
    backend.switchTo(f"{P}/Main.qml")
    QTimer.singleShot(500, s4)
def s4():
    t = backend.property("sourceText")
    check(t.count("label:") == 2 and "caption" not in t.replace("console.log(label)", ""), f"Main.qml's bindings renamed ({t.count('label:')})")
    check(open(f"{P}/Main.qml").read() == open(f"{P}/Main.orig").read(), "nothing written to disk")
    # undo of the rename in Main.qml (Kreator's undo)
    backend.undo()
    check(backend.property("sourceText").count("caption:") == 2, "Kreator's Undo takes it back")
    backend.discardAll()
    QTimer.singleShot(300, app.quit)
QTimer.singleShot(1500, s1)
