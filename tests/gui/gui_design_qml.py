"""Editing a Kirigami page in the design view: properties, i18n, structure."""


import re
def snap(name):
    win.grabWindow().save(f"{OUT}/{name}.png"); print("saved", name)
def rows(model): return model.rows()
def uid_of(type_, ident=None):
    for r in backend.outline.rows():
        if r["typeName"] == type_ and (ident is None or r["objectId"] == ident): return r["uid"]
    raise KeyError(type_)
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)

backend.openFile(REPO + "/examples/SettingsPage.qml")
steps = []
def s1():
    u = uid_of("TextField", "nameField"); backend.select(u)
    names = [r["name"] for r in backend.properties.rows()]
    print("props:", names)
    backend.setProperty("placeholderText", "string", "Full name")
    check('placeholderText: "Full name"' in backend.sourceText, "edit string keeps plain quoting")
    backend.setProperty("Kirigami.FormData.label", "string", "Your Name:")
    check('Kirigami.FormData.label: i18n("Your Name:")' in backend.sourceText, "edit translated keeps i18n")
    backend.setShowAllProperties(True)
    allp = [r for r in backend.properties.rows() if r["section"] == "All properties"]
    print("live props:", len(allp), [ (r["name"], r["kind"], r["value"]) for r in allp[:8]])
    en = [r for r in allp if r["kind"] == "enum"][:3]
    print("enums:", [(r["name"], r["value"], r["enumKeys"][:4]) for r in en])
    backend.setProperty("horizontalAlignment", "enum", "AlignHCenter")
    check("horizontalAlignment: QQC2.TextField.AlignHCenter" in backend.sourceText, "enum written")
    backend.setProperty("readOnly", "bool", "true")
    check("readOnly: true" in backend.sourceText, "bool written")
    try:
        backend.setProperty("width", "number", "abc")
    except Exception as e: print("exc", e)
    backend.setShowAllProperties(False)
def s2():
    print("previewError after edits:", repr(backend.previewError), "note:", backend.previewNote)
    # insert a button into the column layout
    backend.select(uid_of("ColumnLayout"))
    idx = [i for i, e in enumerate(backend.adapter.palette()) if e["name"] == "Button"][0]
    backend.insertComponent(idx)
    check("QQC2.Button {\n            id: button" in backend.sourceText, "button inserted with id")
    print("selected:", backend.selectedType, backend.selectedId)
    # insert a Kirigami action while page selected -> goes to actions list
    backend.select(backend.adapter.doc.root.uid)
    idx = [i for i, e in enumerate(backend.adapter.palette()) if e["name"] == "Action"][0]
    backend.insertComponent(idx)
    check(backend.sourceText.count("Kirigami.Action {") == 2, "action appended to actions list")
    # insert into FormLayout -> gets FormData.label
    backend.select(uid_of("FormLayout"))
    idx = [i for i, e in enumerate(backend.adapter.palette()) if e["name"] == "SpinBox"][0]
    backend.insertComponent(idx)
    check('Kirigami.FormData.label: i18n("SpinBox:")' in backend.sourceText, "form child gets label")
    backend.moveSelected(-1)
    backend.duplicateSelected()
    check("spinBox2" in backend.sourceText, "duplicate with unique id")
    backend.deleteSelected()
    check("spinBox2" not in backend.sourceText, "delete")
    n = len(backend.undo_stack)
    backend.undo(); backend.undo()
    check("spinBox2" not in backend.sourceText and len(backend.undo_stack) == n - 2, "undo x2")
    backend.redo()
    check("spinBox2" in backend.sourceText, "redo")
def s3():
    print("previewError:", repr(backend.previewError))
    snap("qml2")
    # rename id updates references
    backend.select(uid_of("TextField", "nameField"))
    backend.setSelectedId("userName")
    check("userName.text = \"\"" in backend.sourceText, "id rename updates references")
    # fix all
    before = backend.issueCount
    backend.applyAllFixes()
    print("issues before/after fix:", before, backend.issueCount, [i["title"] for i in backend.issues])
    check('placeholderText: "Full name"' in backend.sourceText or "i18n(\"Full name\")" in backend.sourceText, "text survives")
    print(backend.sourceText[:1800])
def s4():
    print("previewError:", repr(backend.previewError))
    snap("qml3")
    # pick: click in preview at name field center
    app.quit()
seq = [s1, s2, s3, s4]
def run(i=0):
    try:
        seq[i]()
    except Exception:
        import traceback; traceback.print_exc(); app.quit(); return
    if i + 1 < len(seq): QTimer.singleShot(900, lambda: run(i + 1))
QTimer.singleShot(1000, run)
