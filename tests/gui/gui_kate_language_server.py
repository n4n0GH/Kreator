"""Kate's editor with Kate's LSP client through Kreator's qmlls."""

KATE = True
NEEDS = ['qmlls']

import sys as _s, traceback as _t, os, glob, time
_s.excepthook = lambda *a: (_t.print_exception(*a), app.exit(3))
import warnings; warnings.simplefilter("ignore")
from PySide6.QtCore import QObject, Qt, QEvent, QMetaObject
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget, QTreeView, QMenu, QTabWidget
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
page = win.findChild(QObject, "editorPage")
P = f"{OUT}/proj"
def find_all(pred):
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems())
    return out
def wait(pred, timeout, then, what):
    t0 = time.time()
    def tick():
        try:
            ok = pred()
        except Exception:
            ok = False
        if ok:
            then()
        elif time.time() - t0 > timeout:
            check(False, f"{what} (timed out after {timeout}s)")
            then()
        else:
            QTimer.singleShot(200, tick)
    tick()
def key(k, mods=Qt.NoModifier, text=""):
    for tp in (QEvent.KeyPress, QEvent.KeyRelease):
        QApplication.sendEvent(win, QKeyEvent(tp, k, mods, text))
def model_texts(model, parent=None, out=None):
    from PySide6.QtCore import QModelIndex
    out = [] if out is None else out
    parent = parent or QModelIndex()
    for r in range(model.rowCount(parent)):
        for c in range(model.columnCount(parent)):
            v = model.index(r, c, parent).data()
            if v: out.append(str(v))
        model_texts(model, model.index(r, 0, parent), out)
    return out

backend.openFolder(P)
backend.openFile(f"{P}/Main.qml")
page.setProperty("sourceMode", True)

def s1():
    eds = find_all(lambda it: it.objectName() == "kateEditor")
    check(len(eds) == 1, "the source view is Kate's editor")
    ed = eds[0]; globals()["ed"] = ed
    check(ed.property("languageFeatures"), f"Kate's LSP client is loaded ({ed.property('languageProblem')})")
    names = ed.actionNames()
    check("lspclient_find_references" in names and "lspclient_rename" in names, "its actions are there (find references, rename)")
    check(any("lspbridge" in a for a in ed.property("languageServer")), f"through Kreator's bridge ({ed.property('languageServer')[-1:]})")
    menus = [w for w in QApplication.allWidgets() if isinstance(w, QMenu) and w.objectName() == "ktexteditor_popup"]
    texts = [a.text().replace("&", "") for m in menus for a in m.actions()]
    check(any("Find References" in t for t in texts) and any("Rename" in t for t in texts), f"the context menu has the LSP entries ({len(texts)} entries)")
    # wait for qmlls to be running for this document (hover/definition answer)
    QMetaObject.invokeMethod(ed, "focusEditor")
    QTimer.singleShot(3000, s2)

def s2():
    ed = globals()["ed"]
    # completion: in ApplicationWindow's body, a type qmlls knows (not in the file)
    ed.setCursorPosition(4, 17)
    QMetaObject.invokeMethod(ed, "focusEditor")
    key(Qt.Key_Return)
    for ch in "TreeVi":
        key(Qt.Key_unknown, Qt.NoModifier, ch)
    key(Qt.Key_Space, Qt.ControlModifier)
    QTimer.singleShot(500, s4)

def completion_items():
    ws = [w for w in QApplication.allWidgets() if w.metaObject().className() == "KateCompletionWidget"]
    if not ws or not ws[0].isVisible():
        return []
    trees = [t for t in ws[0].findChildren(QTreeView)]
    out = []
    for t in trees:
        if t.model():
            out += model_texts(t.model())
    return out

def s4():
    def has():
        items = completion_items()
        if not items:
            key(Qt.Key_Space, Qt.ControlModifier)   # (the first Ctrl+Space can come too early)
        return any("TreeView" in i for i in items)
    wait(has, 20, s5, "qmlls' completion shows TreeView")

def s5():
    items = completion_items()
    check(any("TreeView" in i for i in items), f"LSP completion in Kate's popup ({[i for i in items if 'TreeView' in i][:2]})")
    key(Qt.Key_Escape)
    ed = globals()["ed"]
    # diagnostics: an unknown property
    t = ed.property("text")
    lines = t.split("\n")
    ln = next(i for i, l in enumerate(lines) if "TreeVi" in l)
    ed.setCursorPosition(ln, 0)
    # replace the typed word by an error
    lines[ln] = "    notAProperty: 1"
    globals()["errline"] = ln
    ed.setProperty("text", "\n".join(lines))   # (setText: as from the design view)
    for ch in " ":
        key(Qt.Key_unknown, Qt.NoModifier, ch)
    wait(lambda: any("notAProperty" in x for x in area().itemTexts("Diagnostics")), 25, s6, "Kate's diagnostics panel lists the error")

def area():
    return find_all(lambda it: it.objectName() == "kateToolArea")[0]

def diag_rows():
    return len(area().itemTexts("Diagnostics"))

def s6():
    texts = area().itemTexts("Diagnostics")
    check(any("notAProperty" in x for x in texts), f"the diagnostic is about notAProperty ({[x for x in texts if 'notA' in x][:1]})")
    # find references of MyButton (line 7 after the inserted line)
    ed = globals()["ed"]
    lines = ed.property("text").split("\n")
    ln = next(i for i, l in enumerate(lines) if "MyButton {" in l)
    ed.setCursorPosition(ln, lines[ln].index("MyButton") + 2)
    sp = page.property("sourcePane")
    sp.setProperty("panelsShown", False)
    check(ed.triggerAction("lspclient_find_references"), "find references runs")
    wait(lambda: sp.property("panelsShown") and ref_rows() > 0, 20, s7, "the references panel shows up with results")

def ref_rows():
    a = area()
    return len(a.itemTexts(a.property("currentTitle")))

def s7():
    areas = find_all(lambda it: it.objectName() == "kateToolArea")
    check(len(areas) == 1 and areas[0].nativeVisible(), "Kate's panel is shown below the editor")
    # (it comes for what Kate lists there; the toolbar has no button for it)
    check(not find_all(lambda it: it.property("text") == "Panels"), "the toolbar has no Panels button")
    if areas:
        g = areas[0].nativeGeometry(); e = globals()["ed"].nativeGeometry()
        check(g.top() >= e.bottom(), f"below the editor (panel {g.y()}..{g.bottom()}, editor ..{e.bottom()})")
    win.grabWindow().save(f"{OUT}/lsp_kate.png")
    areas[0].grabToFile(f"{OUT}/lsp_kate_panel.png")
    globals()["ed"].grabToFile(f"{OUT}/lsp_kate_editor.png")
    # go to definition: MyButton -> MyButton.qml (Kreator opens it)
    ed = globals()["ed"]
    page.commitSource() if False else None
    backend.discardAll() if False else None
    lines = ed.property("text").split("\n")
    ln = next(i for i, l in enumerate(lines) if "MyButton {" in l)
    # (the edit with the error must be applied or reverted first: revert)
    page.property("sourcePane").load(False, False)
    ed.setCursorPosition(5, 6)
    QTimer.singleShot(1500, s8)

def s8():
    ed = globals()["ed"]
    check(ed.triggerAction("lspclient_find_definition"), "go to definition runs")
    wait(lambda: backend.property("fileName") == "MyButton.qml", 15, s9, "go to definition opens MyButton.qml in Kreator")

def s9():
    ed = globals()["ed"]
    check(backend.property("fileName") == "MyButton.qml" and ed.property("text") == backend.property("sourceText"),
          "...and the editor shows it")
    check(page.property("sourceMode"), "still in the source view")
    swaps = glob.glob(f"{P}/.*swp*") + glob.glob(f"{P}/*.kate-swp")
    check(not swaps, f"no swap files in the project ({swaps})")
    cfg = os.path.join(os.environ.get("XDG_CONFIG_HOME", ""), "kreatorrc")
    txt = open(cfg).read() if os.path.exists(cfg) else ""
    check("[lspclient]" in txt and "Swap File Mode=0" in txt, "kreatorrc has Kate's LSP settings, and no swap files")
    import subprocess
    kids = subprocess.run(["ps", "-o", "pid=,args=", "--ppid", str(os.getpid())], capture_output=True, text=True).stdout
    qmlls = [l for l in kids.splitlines() if "qmlls" in l]
    bridge = [l for l in kids.splitlines() if "lspbridge" in l]
    check(len(qmlls) == 1 and len(bridge) == 1, f"one qmlls for Kreator and Kate ({len(qmlls)} qmlls, {len(bridge)} bridge)")
    kate = open(os.path.join(os.environ.get("XDG_CONFIG_HOME", ""), "katerc")).read()
    check("qmlls6" not in kate, "Kate's allow list is untouched")
    backend.discardAll()
    QTimer.singleShot(300, app.quit)

QTimer.singleShot(1500, s1)
