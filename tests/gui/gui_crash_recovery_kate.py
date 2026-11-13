"""After a crash: unapplied text in Kate's editor comes back."""

KATE = True
SETTINGS = {'sessionInterval': 2}
EXIT = {0: 9}

# --- run 0 ---
import os, warnings; warnings.simplefilter("ignore")
from PySide6.QtCore import QObject, Qt, QMetaObject
from PySide6.QtTest import QTest
page = win.findChild(QObject, "editorPage")
P = f"{OUT}/proj"
backend.openFolder(P); backend.openFile(f"{P}/MyButton.qml")
page.setProperty("sourceMode", True)
def find_all(pred):
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems())
    return out
def s1():
    ed = find_all(lambda it: it.objectName() == "kateEditor")[0]
    QMetaObject.invokeMethod(ed, "focusEditor"); ed.setCursorPosition(0, 0)
    for k in (Qt.Key_B, Qt.Key_R, Qt.Key_O, Qt.Key_K, Qt.Key_E, Qt.Key_N, Qt.Key_BraceLeft):
        QTest.keyClick(win, k, Qt.NoModifier)
    print("typed:", repr(ed.property("text")[:10]), flush=True)
    QTimer.singleShot(3500, lambda: os._exit(9))   # crash after a periodic save
QTimer.singleShot(1500, s1)

# --- run 1 ---
import warnings; warnings.simplefilter("ignore")
from PySide6.QtCore import QObject
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
page = win.findChild(QObject, "editorPage")
def find_all(pred):
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems())
    return out
def s1():
    ed = find_all(lambda it: it.objectName() == "kateEditor")[0]
    check(page.property("sourceMode") and backend.property("fileName") == "MyButton.qml", "restored into the source view of the file")
    check(ed.property("text").startswith("broken{"), f"Kate's editor has the unapplied, unparsable text ({ed.property('text')[:10]!r})")
    check(page.property("sourcePane").property("dirty"), "marked as edited")
    app.quit()
QTimer.singleShot(1500, s1)
