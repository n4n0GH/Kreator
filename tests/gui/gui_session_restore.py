"""Restoring the session: tabs, order, unsaved changes, untitled documents."""


# --- run 0 ---
from PySide6.QtCore import QObject, QMetaObject, Q_ARG
P = f"{OUT}/proj"
backend.openFolder(P)
for f in ("Main.qml", "MyButton.qml", "forms/dialog.ui"):
    backend.openFile(f"{P}/{f}")
backend.moveTab(2, 0)            # dialog.ui first
backend.switchTo(f"{P}/MyButton.qml")
ok = backend.applySource(backend.property("sourceText").replace("import QtQuick", "import QtQuick // edited", 1))
print("edited:", ok, backend.modified)
backend.newDocument("kirigami-page")
backend.applySource(backend.property("sourceText") + "\n// my untitled note\n")
backend.newDocument("widgets-form")
backend.switchTo(f"{P}/MyButton.qml")
print("tabs before quit:", [(d["name"], d["modified"]) for d in backend.openDocuments], backend.currentKey)
def quit_():
    win.close()   # with keepUnsaved: no question, just quits
    QTimer.singleShot(300, lambda: (print("still visible:", win.isVisible()), app.quit()))
QTimer.singleShot(500, quit_)

# --- run 1 ---
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
P = f"{OUT}/proj"
docs = backend.openDocuments
print("restored:", [(d["name"], d["modified"], d["key"]) for d in docs], backend.currentKey)
check(backend.projectPath == P, "folder reopened")
check([d["name"] for d in docs] == ["dialog.ui", "Main.qml", "MyButton.qml", "Page.qml", backend.openDocuments[4]["name"]] and len(docs) == 5, "tabs in order, untitled kept")
check(backend.currentKey == f"{P}/MyButton.qml" and backend.modified and "// edited" in backend.property("sourceText"), "current doc with its unsaved edit")
check(open(f"{P}/MyButton.qml").read() == open(f"{P}/MyButton.orig").read(), "file on disk untouched")
check([d["modified"] for d in docs] == [False, False, True, True, True], "modified flags")
check(backend.property("unsavedCount") == 3, "unsaved count")
backend.switchTo(docs[3]["key"])
check(backend.filePath == "" and "my untitled note" in backend.property("sourceText"), "untitled document text kept")
backend.switchTo(docs[4]["key"])
check(backend.docKind == "ui", f"untitled .ui form kept ({backend.fileName})")
backend.newDocument("qtquick")
check(len(set(d["key"] for d in backend.openDocuments)) == 6, "new untitled key does not collide")
app.quit()
