"""Undo history kept across a restart."""


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
P = f"{OUT}/proj"
check(backend.fileName == "MyButton.qml" and not backend.modified and backend.canUndo, "saved file restored clean with its undo history")
backend.undo()
check("// saved edit" not in backend.property("sourceText") and backend.modified, "undo across the restart")
backend.redo()
check("// saved edit" in backend.property("sourceText") and not backend.modified, "redo")
backend.switchTo(f"{P}/Main.qml")
t = backend.property("sourceText")
check("// e1" in t and "// e2" not in t and backend.canUndo and backend.canRedo, "background doc: text, undo and redo restored")
backend.redo()
check("// e2" in backend.property("sourceText"), "redo the undone edit")
backend.undo(); backend.undo(); backend.undo()
check("// e0" not in backend.property("sourceText") and not backend.canUndo, "undo back to the file as opened")
app.quit()
