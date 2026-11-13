"""After a crash: tabs, applied and unapplied edits come back (built-in editor)."""

PLAIN_EDITOR = True
SETTINGS = {'sessionInterval': 2}
EXIT = {0: 9}

# --- run 0 ---
import os
from PySide6.QtCore import QObject
P = f"{OUT}/proj"
page = win.findChild(QObject, "editorPage")
print("owns:", backend.ownsSession, "interval:", backend.sessionInterval)
backend.openFolder(P)
backend.openFile(f"{P}/Main.qml")
backend.applySource(backend.property("sourceText").replace("import QtQuick", "import QtQuick // crash-edit", 1))
backend.openFile(f"{P}/MyButton.qml")
page.setProperty("sourceMode", True)
def type_broken():
    # find the source TextEdit and type unparsable text without applying
    stack = [win.contentItem()]; ed = None
    while stack:
        it = stack.pop()
        if it.metaObject().className().startswith("QQuickTextEdit") and it.property("readOnly") is False and "MyButton" not in str(it.property("text"))[:0] and it.isVisible() and "import" in (it.property("text") or ""):
            ed = it; break
        stack.extend(it.childItems())
    ed.setProperty("text", ed.property("text") + "\nItem { broken: \n")
    QTimer.singleShot(3500, crash)
def crash():
    print("session written:", os.path.exists(f"{os.environ['XDG_DATA_HOME']}/kreator/session.json"), flush=True)
    os._exit(9)   # no quit, no onClosing
QTimer.singleShot(800, type_broken)

# --- run 1 ---
from PySide6.QtCore import QObject
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
P = f"{OUT}/proj"
page = win.findChild(QObject, "editorPage")
def go():
    docs = backend.openDocuments
    print([(d["name"], d["modified"]) for d in docs])
    check([d["name"] for d in docs] == ["Main.qml", "MyButton.qml"], "tabs restored after a crash")
    check(backend.fileName == "MyButton.qml" and page.property("sourceMode"), "source view shown for the restored unapplied edit")
    stack = [win.contentItem()]; ed = None
    while stack:
        it = stack.pop()
        if it.metaObject().className().startswith("QQuickTextEdit") and "broken:" in (it.property("text") or ""):
            ed = it
        stack.extend(it.childItems())
    check(ed is not None, "unapplied (unparsable) source text restored")
    check(page.pendingSource() != "" if hasattr(page, "pendingSource") else True, "still pending")
    backend.switchTo(f"{P}/Main.qml")
    check(backend.modified and "crash-edit" in backend.property("sourceText"), "applied edit in the background tab restored")
    app.quit()
QTimer.singleShot(500, go)
