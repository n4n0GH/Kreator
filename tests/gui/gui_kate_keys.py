"""Keys in Kate's editor, and the keys Kreator keeps."""

KATE = True

import sys as _s, traceback as _t
_s.excepthook = lambda *a: (_t.print_exception(*a), app.exit(3))
import warnings; warnings.simplefilter("ignore")
from PySide6.QtCore import QObject, Qt, QMetaObject
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
def key(k, mods=Qt.NoModifier, text=None):
    QTest.keyClick(win, k, mods)
    app.processEvents()
backend.openFolder(P)
backend.openFile(f"{P}/Main.qml")
backend.openFile(f"{P}/MyButton.qml")
page.setProperty("sourceMode", True)
def s1():
    ed = find_all(lambda it: it.objectName() == "kateEditor")[0]; globals()["ed"] = ed
    QMetaObject.invokeMethod(ed, "focusEditor")
    ed.setCursorPosition(0, 0)
    for k in (Qt.Key_Slash, Qt.Key_Slash, Qt.Key_Space, Qt.Key_Q):
        key(k)
    t = ed.property("text")
    check(t.startswith("// q"), f"typing with real key events ({t[:6]!r})")
    key(Qt.Key_Backspace)
    check(ed.property("text").startswith("// \n") or ed.property("text").startswith("// i"), "Backspace (Kate)")
    c = ed.property("cursorColumn"); key(Qt.Key_Left)
    check(ed.property("cursorColumn") == c - 1, "Left (Kate)")
    key(Qt.Key_Z, Qt.ControlModifier)
    check(ed.property("text").startswith("// q"), "Ctrl+Z is Kate's undo")
    check(page.property("sourcePane").property("dirty"), "edited")
    key(Qt.Key_Return, Qt.ControlModifier)
    check(not page.property("sourcePane").property("dirty") and backend.property("sourceText").startswith("// q"), "Ctrl+Return applies (Kreator)")
    disk = open(f"{P}/MyButton.qml").read()
    key(Qt.Key_S, Qt.ControlModifier)
    QTimer.singleShot(300, lambda: s2(disk))
def s2(disk):
    check(open(f"{P}/MyButton.qml").read().startswith("// q") and not backend.property("modified"), "Ctrl+S saves through Kreator")
    key(Qt.Key_Tab, Qt.ControlModifier)
    QTimer.singleShot(300, s3)
def s3():
    check(backend.property("fileName") == "Main.qml", f"Ctrl+Tab switches tabs while typing in Kate ({backend.property('fileName')})")
    key(Qt.Key_E, Qt.ControlModifier | Qt.ShiftModifier)
    QTimer.singleShot(300, s4)
def s4():
    check(not page.property("sourceMode"), "Ctrl+Shift+E switches to the design view")
    key(Qt.Key_E, Qt.ControlModifier | Qt.ShiftModifier)
    QTimer.singleShot(400, s5)
def s5():
    ed = find_all(lambda it: it.objectName() == "kateEditor")[0]
    check(page.property("sourceMode") and ed.hasActiveFocus(), "and back to the source view, keyboard in Kate")
    # Quick Open (Ctrl+Alt+O) over the editor: the editor freezes
    key(Qt.Key_O, Qt.ControlModifier | Qt.AltModifier)
    QTimer.singleShot(400, lambda: s6(ed))
def s6(ed):
    check(ed.property("frozen") is True or ed.nativeVisible() is False, "Quick Open over the editor: editor shows a snapshot")
    win.grabWindow().save(f"{OUT}/kate_quickopen.png")
    key(Qt.Key_Escape)
    QTimer.singleShot(400, lambda: s7(ed))
def s7(ed):
    check(ed.nativeVisible(), "closed: live editor back")
    app.quit()
QTimer.singleShot(1500, s1)
