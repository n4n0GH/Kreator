"""Editing a Qt Designer form in the design view."""


def snap(name):
    win.grabWindow().save(f"{OUT}/{name}.png"); print("saved", name)
def check(c, m): print(("PASS " if c else "FAIL ") + m)
def uid_of(t, i=None):
    for r in backend.outline.rows():
        if r["typeName"] == t and (i is None or r["objectId"] == i): return r["uid"]
    raise KeyError(t)
backend.openFile(REPO + "/examples/dialog.ui")
def s1():
    print("err:", repr(backend.previewError), "size", backend.uiWidth, backend.uiHeight, backend.uiImage)
    print("outline:", [(r["depth"], r["typeName"], r["objectId"], r["label"]) for r in backend.outline.rows()])
    print("issues:", [i["title"] for i in backend.issues])
    backend.select(uid_of("QPushButton"))
    print("rect:", backend.uiRect(backend.selectedUid))
    print("props:", [(r["name"], r["kind"], r["value"], r["section"]) for r in backend.properties.rows()][:6])
    backend.setShowAllProperties(True)
    en = [r for r in backend.properties.rows() if r["kind"] == "enum"][:2]
    print("enum rows:", [(r["name"], r["value"], r["enumKeys"][:3]) for r in en])
    backend.setShowAllProperties(False)
    backend.setProperty("text", "string", "Test Connection…")
    check("<string>Test Connection…</string>" in backend.sourceText, "ui string edit")
    # pick the spinbox: compute its rect
    backend.select(uid_of("QSpinBox"))
    r = backend.uiRect(backend.selectedUid)
    backend.select(uid_of("QDialog"))
    backend.pickUi(r[0] + 5, r[1] + 5)
    check(backend.selectedType == "QSpinBox", "pick ui widget")
    # insert a widget into the form layout
    backend.select(uid_of("QFormLayout"))
    idx = [i for i, e in enumerate(backend.adapter.palette()) if e["name"] == "QLabel"][0]
    backend.insertComponent(idx)
    idx = [i for i, e in enumerate(backend.adapter.palette()) if e["name"] == "QLineEdit"][0]
    backend.insertComponent(idx)
    src = backend.sourceText
    check('<item row="2" column="0">' in src and '<item row="2" column="1">' in src, "form layout row placement")
    backend.select(uid_of("QCheckBox"))
    idx = [i for i, e in enumerate(backend.adapter.palette()) if e["name"] == "QGroupBox"][0]
    backend.insertComponent(idx)
    idx = [i for i, e in enumerate(backend.adapter.palette()) if e["name"] == "QRadioButton"][0]
    backend.insertComponent(idx)
    check("QGroupBox" in backend.sourceText and 'class="QVBoxLayout" name="verticalLayout_2"' in backend.sourceText, "container gets layout")
    backend.moveSelected(-1)
    backend.applyAllFixes()
    print("issues after fix:", [i["title"] for i in backend.issues])
    backend.setSelectedId("myRadio")
    check('name="myRadio"' in backend.sourceText, "rename")
def s2():
    print("err:", repr(backend.previewError))
    snap("ui1")
    open(f"{OUT}/ui_out.ui", "w").write(backend.sourceText)
    app.quit()
seq = [s1, s2]
def run(i=0):
    try: seq[i]()
    except Exception:
        import traceback; traceback.print_exc(); app.quit(); return
    if i + 1 < len(seq): QTimer.singleShot(900, lambda: run(i + 1))
QTimer.singleShot(1000, run)
