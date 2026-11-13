"""Undo history of a file changed while Kreator was closed is dropped."""


def between_runs(run, work):
    path = os.path.join(work, "proj", "MyButton.qml")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("// changed elsewhere\n")

# --- run 0 ---
P = f"{OUT}/proj"
backend.openFolder(P)
backend.openFile(f"{P}/Main.qml")
for i in range(3):
    backend.applySource(backend.property("sourceText").replace("import QtQuick", f"import QtQuick // e{i}", 1))
backend.undo()                    # leaves one redo step
backend.openFile(f"{P}/MyButton.qml")
backend.applySource(backend.property("sourceText") + "\n// saved edit\n")
backend.save()                    # clean, but with history
print("before quit Main undo/redo:", len(backend.docs[f"{P}/Main.qml"].undo), len(backend.docs[f"{P}/Main.qml"].redo), "MyButton:", len(backend.undo_stack), backend.modified)
QTimer.singleShot(300, lambda: (win.close(), QTimer.singleShot(300, app.quit)))

# --- run 1 ---
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
check(backend.fileName == "MyButton.qml" and not backend.canUndo and "changed elsewhere" in backend.property("sourceText"), "file changed while closed: history dropped, not misapplied")
app.quit()
