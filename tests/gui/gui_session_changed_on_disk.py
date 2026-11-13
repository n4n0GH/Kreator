"""A restored unsaved file that changed on disk while Kreator was closed."""


def between_runs(run, work):
    # MyButton.qml (restored with unsaved changes) changes on disk while Kreator is closed
    path = os.path.join(work, "proj", "MyButton.qml")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n// changed elsewhere\n")

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
# file changed on disk while QViewer was closed
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
def later():
    print("externalChange:", backend.externalChange, "modified:", backend.modified)
    check(backend.externalChange and backend.modified, "external change noticed for a restored unsaved file")
    app.quit()
QTimer.singleShot(1500, later)
