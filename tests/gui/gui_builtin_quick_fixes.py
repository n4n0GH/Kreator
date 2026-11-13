"""Built-in editor: qmllint quick fixes."""

PLAIN_EDITOR = True
NEEDS = ['qmlls']

from PySide6.QtCore import QObject, Qt, QEvent, QMetaObject, Q_ARG
from PySide6.QtGui import QKeyEvent, QGuiApplication
from PySide6.QtTest import QTest
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
def v(x): return x.toVariant() if hasattr(x, "toVariant") else x
backend.openFile(f"{OUT}/qf/Fixes.qml")
page = win.findChild(QObject, "editorPage")
def find(pred):
    stack = [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): return it
        stack.extend(it.childItems())
def lsp():
    import gc
    from kreator.lsp import LanguageSupport
    return next(o for o in gc.get_objects() if isinstance(o, LanguageSupport))
def s1():
    page.setProperty("sourceMode", True); QTimer.singleShot(6000, s2)
def s2():
    global ed, pane, menu, L
    L = lsp()
    ed = find(lambda it: it.metaObject().indexOfProperty("persistentSelection") >= 0 and it.property("persistentSelection"))
    pane = find(lambda it: it.metaObject().indexOfProperty("foldRegions") >= 0)
    menu = [o for o in ed.children() if o.metaObject().indexOfProperty("fixes") >= 0][0]
    diags = v(L.property("diagnostics"))
    print("diagnostics with fixes:", [(d["line"] + 1, [f["title"] for f in d["fixes"]], [f["auto"] for f in d["fixes"]]) for d in diags if d["fixes"]])
    lines = v(pane.property("diagnosticLines"))
    check(lines.get("19", {}).get("hasFix") and lines.get("10", {}).get("hasFix") and not lines.get("14", {}).get("hasFix"), "lightbulbs on fixable lines only")
    check(len(v(pane.property("safeFixes"))) == 1, "one safe fix (root.)")
    win.grabWindow().save(f"{OUT}/qf1.png")
    # Alt+Return on the 'heigth' line
    ed.forceActiveFocus()
    t = ed.property("text"); ed.setProperty("cursorPosition", t.index("heigth") + 2)
    QTest.keyClick(win, Qt.Key_Return, Qt.AltModifier)
    QTimer.singleShot(300, s3)
def s3():
    fixes = v(menu.property("fixes"))
    check(menu.property("opened") and fixes[0]["title"] == 'Did you mean "height"?', f"Alt+Return opens fixes: {[f['title'] for f in fixes]}")
    win.grabWindow().save(f"{OUT}/qf2.png")
    menu.close()
    QMetaObject.invokeMethod(pane, "applyFix", Q_ARG("QVariant", fixes[0]))
    t = ed.property("text")
    check("height: 20" in t and "heigth" not in t, "typo fixed")
    QTimer.singleShot(2500, s4)   # new diagnostics + fixes
def s4():
    diags = v(L.property("diagnostics"))
    check(not any("heigth" in d["message"] for d in diags), "diagnostic gone after the fix")
    # placeholder fix in the delegate
    d = next(d for d in diags if d["line"] == 10)
    fix = d["fixes"][0]
    check(fix["title"].startswith("Qualify with the parent"), "placeholder fix title: " + fix["title"])
    QMetaObject.invokeMethod(pane, "applyFix", Q_ARG("QVariant", fix))
    check(ed.property("selectedText") == "<id>", "<id> selected for typing")
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)
    QTimer.singleShot(2500, s5)
def s5():
    # apply all safe fixes
    t0 = ed.property("text")
    print("before apply-all: safe", len(v(pane.property("safeFixes"))), "current", L.isFixTextCurrent(t0), "diags", [(d["line"]+1, len(d["fixes"])) for d in v(L.property("diagnostics"))], "fixtext==text", L._fix_text == t0, "L._text==t0", L._text == t0)
    QMetaObject.invokeMethod(pane, "applyAllSafeFixes")
    t = ed.property("text")
    check("{ root.counter = 1 }" in t, "Apply All Safe Fixes qualified with root.")
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)
    check(ed.property("text") == t0, "one Ctrl+Z undoes it")
    # stale protection: type and immediately apply
    ed.setProperty("cursorPosition", 0)
    QGuiApplication.sendEvent(win, QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " "))
    QMetaObject.invokeMethod(pane, "applyAllSafeFixes")
    check(ed.property("text").startswith(" import") and "{ root.counter" not in ed.property("text"), "no stale fixes applied right after typing")
    app.quit()
QTimer.singleShot(1000, s1)
