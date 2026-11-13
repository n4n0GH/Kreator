"""A folder as a project: the file tree, Quick Open, switching files."""

NEEDS = ['qmlls']

from PySide6.QtCore import QObject, Qt, QEvent, QMetaObject, Q_ARG
from PySide6.QtGui import QKeyEvent, QGuiApplication
from PySide6.QtTest import QTest
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
def v(x): return x.toVariant() if hasattr(x, "toVariant") else x
P = f"{OUT}/proj"
page = win.findChild(QObject, "editorPage")
def find(pred):
    stack = [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): return it
        stack.extend(it.childItems())
def rows(): return [(r["relPath"], r["isDir"], r["modified"], r["current"]) for r in backend.projectFiles.rows()]
backend.openFolder(P)
def s1():
    r = rows()
    print("project rows:", r)
    check(("forms", True, False, False) in r and ("forms/dialog.ui", False, False, False) in r and not any("build" in x[0] for x in r), "folder tree with .qml/.ui, build output skipped")
    check(backend.property("projectName") == "proj" and "proj" in win.title(), "project name in the window title: " + win.title())
    QMetaObject.invokeMethod(win, "switchFile", Q_ARG("QVariant", f"{P}/Main.qml"))
    QTimer.singleShot(800, s2)
def s2():
    check(backend.property("fileName") == "Main.qml", "file opened from the project")
    # edit Main in the design view
    u = next(r["uid"] for r in backend.outline.rows() if r["typeName"] == "MyButton")
    backend.select(u); backend.setProperty("caption", "string", "Edited")
    check(backend.property("modified"), "Main modified")
    page.setProperty("sourceMode", True)
    QMetaObject.invokeMethod(win, "switchFile", Q_ARG("QVariant", f"{P}/MyButton.qml"))
    QTimer.singleShot(1500, s3)
def s3():
    check(backend.property("fileName") == "MyButton.qml" and page.property("sourceMode"), "switched without a prompt, source view kept")
    r = rows()
    check(("Main.qml", False, True, False) in r and ("MyButton.qml", False, False, True) in r, "tree marks Main as modified, MyButton as current")
    check(backend.property("unsavedCount") == 1, "one unsaved document in the background")
    # symbols
    import gc
    from kreator.lsp import LanguageSupport
    global L
    L = next(o for o in gc.get_objects() if isinstance(o, LanguageSupport))
    QTimer.singleShot(3500, s4)
def s4():
    syms = v(L.property("symbols"))
    print("symbols:", [(s["name"], s["detail"], s["line"] + 1) for s in syms][:6])
    check(any(s["name"] == "Button" and s["isObject"] for s in syms) and any(s["name"] == "caption" for s in syms), "document symbols from qmlls")
    find(lambda it: it.metaObject().className().startswith("SidePanel")).showTab(1)
    app.processEvents()
    sym_view = find(lambda it: it.metaObject().indexOfProperty("showBindings") >= 0)
    check(sym_view is not None and sym_view.isVisible(), "sidebar shows Symbols in the source view")
    # go to symbol picker
    ed = find(lambda it: it.objectName() == "kateEditor") or find(lambda it: it.metaObject().indexOfProperty("persistentSelection") >= 0 and it.property("persistentSelection"))
    if ed.objectName() == "kateEditor":
        QMetaObject.invokeMethod(ed, "focusEditor")
    else:
        ed.forceActiveFocus()
    QTest.keyClick(win, Qt.Key_P, Qt.ControlModifier | Qt.AltModifier)
    QTimer.singleShot(400, lambda: s5(ed))
def s5(ed):
    pick = [o for o in page.findChildren(QObject) if o.metaObject().indexOfProperty("shown") >= 0 and o.metaObject().indexOfProperty("placeholder") >= 0 and "symbol" in o.property("placeholder")]
    sp = pick[0]
    shown = v(sp.property("shown"))
    check(sp.property("opened") and any(i["title"] == "caption" for i in shown), f"Ctrl+Alt+P lists symbols ({len(shown)})")
    win.grabWindow().save(f"{OUT}/proj_symbols.png")
    item = next(i for i in shown if i["title"] == "caption")
    sp.close(); QMetaObject.invokeMethod(sp, "picked", Q_ARG("QVariant", item))
    QTimer.singleShot(300, lambda: s6(ed))
def s6(ed):
    if ed.objectName() == "kateEditor":
        ln = ed.property("cursorLine") + 1
    else:
        t = ed.property("text"); p = ed.property("cursorPosition"); ln = t[:p].count("\n") + 1
    check(ln == 6, f"jumped to the symbol's line ({ln})")
    # change MyButton on disk? no: change Main on disk while it is in the background -> conflict kept
    # quick open
    QTest.keyClick(win, Qt.Key_O, Qt.ControlModifier | Qt.AltModifier)
    QTimer.singleShot(400, s7)
def s7():
    fp = [o for o in page.findChildren(QObject) + win.findChildren(QObject) if o.metaObject().indexOfProperty("shown") >= 0 and o.metaObject().indexOfProperty("placeholder") >= 0 and "file" in o.property("placeholder")]
    fpk = fp[0]
    shown = v(fpk.property("shown"))
    print("quick open:", [(i["title"], i.get("subtitle")) for i in shown][:5])
    check(fpk.property("opened") and shown[0]["title"] == "• Main.qml" and shown[1]["title"] == "MyButton.qml" and any(i["title"] == "dialog.ui" for i in shown), "Ctrl+Alt+O: previously used document first (modified marked), current next, then project files")
    win.grabWindow().save(f"{OUT}/proj_quickopen.png")
    item = next(i for i in shown if i["title"] == "• Main.qml")
    fpk.close(); QMetaObject.invokeMethod(fpk, "picked", Q_ARG("QVariant", item))
    QTimer.singleShot(1200, s8)
def s8():
    t = backend.property("sourceText")
    check(backend.property("fileName") == "Main.qml" and 'caption: "Edited"' in t and backend.property("canUndo"), "back on Main: unsaved edit and undo history kept")
    backend.undo()
    check('caption: "Edited"' not in backend.property("sourceText"), "undo still works after switching")
    backend.redo()
    # .ui in the subfolder
    QMetaObject.invokeMethod(win, "switchFile", Q_ARG("QVariant", f"{P}/forms/dialog.ui"))
    QTimer.singleShot(1200, s9)
def s9():
    check(backend.property("docKind") == "ui", ".ui from the project")
    win.grabWindow().save(f"{OUT}/proj_tree.png")
    # Save All
    n = backend.saveAll()
    main = open(f"{P}/Main.qml").read()
    check(n == 0 and 'caption: "Edited"' in main and backend.property("unsavedCount") == 0, "Save All writes the background document")
    check(not any(x[2] for x in rows()), "no modified marks after Save All")
    open(f"{P}/Main.qml", "w").write(open(f"{P}/Main.orig").read())   # restore
    # close folder
    QMetaObject.invokeMethod(win, "closeFolder")
    QTimer.singleShot(300, s10)
def s10():
    check(backend.property("projectPath") == "", "folder closed")
    app.quit()
QTimer.singleShot(1000, s1)
