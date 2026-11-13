"""Opening documents in Kate and other editors, and reloading their changes."""


import os, json
from PySide6.QtCore import QObject
import kreator.backend as B
def rewrite(f, a, b):
    t = open(f).read().replace(a, b)
    open(f, "w").write(t)
launched = []
class FakeProcess:
    @staticmethod
    def startDetached(prog, args, wd):
        launched.append([prog, *args]); return (True, 1234)
B.QProcess = FakeProcess
W = f"{OUT}/work"
F = f"{W}/SettingsPage.qml"
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
def uid(i):
    return next(r["uid"] for r in backend.outline.rows() if r["objectId"] == i)
backend.openFile(F)
steps = []
def step(f): steps.append(f); return f
@step
def s1():
    backend.select(uid("nameField"))
    backend.openInEditor("")
    print("argv:", launched[-1])
    check(launched[-1][1:] == ["--line", "32", "--column", "13", F] and launched[-1][0].endswith("kate"), "kate at object line")
    cfg = json.loads(backend.editorSettingsJson())
    cfg["kate"]["session"] = "My Project"; cfg["kate"]["newWindow"] = True
    cfg["custom"].append({"name": "Zed", "command": "true", "args": "--wait {file}:{line}:{column}", "icon": "zed"})
    backend.setEditorSettingsJson(json.dumps(cfg))
    backend.openInEditor("kate")
    check(launched[-1][1:5] == ["--start", "My Project", "--new", "--line"], "kate session + new window")
    ed = [e for e in backend.editorList if e["name"] == "Zed"][0]
    check(ed["available"], "custom editor resolved")
    backend.openInEditor(ed["id"])
    print("zed argv:", launched[-1])
    check(launched[-1][1:] == ["--wait", f"{F}:32:13"], "custom editor template")
    # external change, no local edits -> auto reload
    rewrite(F, 'title: i18n("Settings")', 'title: i18n("Settings From Kate")')
@step
def s2():
    check('i18n("Settings From Kate")' in backend.sourceText and not backend.modified, "auto-reload after external save")
    check(backend.canUndo, "reload is undoable")
    check(backend.selectedId == "nameField", "selection kept: " + backend.selectedId)
    # editor saving by atomic rename
    t = open(F).read().replace("Settings From Kate", "Renamed Save")
    open(F + ".tmp", "w").write(t); os.replace(F + ".tmp", F)
@step
def s3():
    check('i18n("Renamed Save")' in backend.sourceText, "reload after atomic rename save")
    # local edit + external change -> conflict banner
    backend.setProperty("placeholderText", "string", "Mine")
    rewrite(F, "Renamed Save", "Theirs")
@step
def s4():
    check(backend.externalChange and 'placeholderText: "Mine"' in backend.sourceText, "conflict reported, local edits kept")
    win.grabWindow().save(f"{OUT}/conflict.png")
    backend.reloadFromDisk()
    check(not backend.externalChange and 'i18n("Theirs")' in backend.sourceText and not backend.modified, "load their version")
    backend.undo()
    check('placeholderText: "Mine"' in backend.sourceText, "undo restores mine")
    # broken save in editor
    open(F, "w").write("Item {\n")
@step
def s5():
    # with unsaved edits here, it's a conflict first; taking their (unreadable)
    # version reports the error and keeps the document as it is
    check(backend.externalChange, "broken file on disk: reported as a change")
    backend.reloadFromDisk()
    check(backend.externalError != "" and 'placeholderText: "Mine"' in backend.sourceText,
          "loading the broken version reports why, and keeps mine: " + backend.externalError[:60])
    open(F, "w").write(open(f"{REPO}/examples/SettingsPage.qml").read())
@step
def s6():
    # unsaved edits remained (undo restored 'Mine'), so this is a conflict again
    print("after fix: change", backend.externalChange, "err", repr(backend.externalError))
    backend.keepMyVersion()
    ok = backend.save()
    check(ok and open(F).read() == backend.sourceText and not backend.externalChange, "save mine, no self-trigger")
    # .ui position
    backend.openFile(f"{W}/dialog.ui")
    backend.select(uid("portSpin"))
    backend.openInEditor("kate")
    print("ui argv:", launched[-1])
    check("--line" in launched[-1] and launched[-1][launched[-1].index("--line")+1] == "47", "ui widget line")
    win.findChild(QObject, "editorPage")
    app.findChild  # noqa
    root = win
    root.setProperty("dummy", 0)
@step
def s7():
    # settings page
    from PySide6.QtCore import QMetaObject
    rootobj = [o for o in [win] ][0]
    QMetaObject.invokeMethod(rootobj, "configureEditors")
@step
def s8():
    win.grabWindow().save(f"{OUT}/editors.png"); print("saved settings shot"); app.quit()
def run(i=0):
    try: steps[i]()
    except Exception:
        import traceback; traceback.print_exc(); app.quit(); return
    if i + 1 < len(steps): QTimer.singleShot(1200, lambda: run(i + 1))
QTimer.singleShot(1000, run)
