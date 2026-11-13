"""Without keeping unsaved changes, documents come back as saved."""

SETTINGS = [{}, {'keepUnsaved': False}]

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
# restore off for unsaved: the edited file comes back as saved, untitled dropped
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
docs = backend.openDocuments
check([d["name"] for d in docs] == ["dialog.ui", "Main.qml", "MyButton.qml"] and not any(d["modified"] for d in docs), f"keepUnsaved off: saved state only {[d['name'] for d in docs]}")
app.quit()
