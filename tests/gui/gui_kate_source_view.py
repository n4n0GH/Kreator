"""Kate's editor as the source view."""

KATE = True

import sys as _s, traceback as _t
_s.excepthook = lambda *a: (_t.print_exception(*a), app.exit(3))
import warnings; warnings.simplefilter("ignore")
from PySide6.QtCore import QObject, Qt, QEvent, QPointF, QMetaObject
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtQuick import QQuickItem
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
check(backend.property("kateEditorAvailable"), f"Kate's editor available ({backend.property('kateEditorProblem')})")
backend.openFolder(P)
backend.openFile(f"{P}/Main.qml")
u = next(r["uid"] for r in backend.outline.rows() if r["typeName"] == "MyButton")
backend.select(u)
page.setProperty("sourceMode", True)
def s1():
    eds = find_all(lambda it: it.objectName() == "kateEditor")
    check(len(eds) == 1, "the source view is Kate's editor")
    ed = eds[0]; globals()["ed"] = ed
    check(ed.property("text") == backend.property("sourceText"), "it shows the document")
    line = backend.lineOfSelected("")
    check(ed.property("cursorLine") == line - 1, f"cursor at the selected object (line {ed.property('cursorLine') + 1} vs {line})")
    check(ed.property("mode") == "QML", "QML highlighting")
    # type into Kate
    v = [w for w in QApplication.allWidgets() if w.metaObject().className() == "KTextEditor::ViewPrivate"][0]
    inner = [c for c in v.findChildren(QWidget) if c.metaObject().className() == "KateViewInternal"][0]
    globals()["inner"] = inner
    QMetaObject.invokeMethod(ed, "focusEditor")
    ed.setCursorPosition(0, 0)
    afi = win.activeFocusItem()
    print("activeFocusItem:", afi.metaObject().className() if afi else None, afi.objectName() if afi else "", "| ed.activeFocus:", ed.hasActiveFocus(), "| win.focus:", __import__("PySide6.QtGui", fromlist=["QGuiApplication"]).QGuiApplication.focusWindow(), flush=True)
    for ch in "// kate\n":
        k = Qt.Key_Return if ch == "\n" else Qt.Key_unknown
        for tp in (QEvent.KeyPress, QEvent.KeyRelease):
            QApplication.sendEvent(win, QKeyEvent(tp, k, Qt.NoModifier, ch))
    sp = page.property("sourcePane")
    check(ed.property("text").startswith("// kate\n") and sp.property("dirty"), "typing (through Kreator's window) edits and marks it edited")
    check(page.commitSource() and backend.property("sourceText").startswith("// kate") and backend.property("modified"), "apply puts the edit into the document")
    QTimer.singleShot(200, s2)
def s2():
    ed = globals()["ed"]
    # design change -> source view follows
    u2 = next(r["uid"] for r in backend.outline.rows() if r["typeName"] == "MyButton")
    backend.select(u2); backend.setProperty("caption", "string", "Changed")
    QTimer.singleShot(300, lambda: s3(ed))
def s3(ed):
    check('"Changed"' in ed.property("text") and not page.property("sourcePane").property("dirty"), "a design change shows up in the editor")
    # toolbar undo in Kate's view = Kate's text undo
    t = ed.property("text")
    ed.setCursorPosition(0, 0)
    for tp in (QEvent.KeyPress, QEvent.KeyRelease):
        QApplication.sendEvent(win, QKeyEvent(tp, Qt.Key_X, Qt.NoModifier, "x"))
    check(ed.property("text") == "x" + t, "typed")
    page.property("sourcePane").editorUndo()
    check(ed.property("text") == t, "Undo (toolbar) undoes in Kate")
    # switch document while in the source view
    backend.openFile(f"{P}/MyButton.qml")
    QTimer.singleShot(300, lambda: s4(ed))
def s4(ed):
    check(ed.property("text") == backend.property("sourceText") and "MyButton" not in backend.property("fileName")[:0] and backend.property("fileName") == "MyButton.qml", "switching documents shows the other file")
    win.grabWindow().save(f"{OUT}/kate_src.png")
    backend.discardAll()
    app.quit()
QTimer.singleShot(1500, s1)
