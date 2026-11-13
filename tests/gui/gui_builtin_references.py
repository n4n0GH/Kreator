"""Built-in editor: find references."""

PLAIN_EDITOR = True
NEEDS = ['qmlls']

from PySide6.QtCore import QObject, Qt, QEvent, QMetaObject, Q_ARG
from PySide6.QtGui import QKeyEvent, QGuiApplication
from PySide6.QtTest import QTest
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
def v(x): return x.toVariant() if hasattr(x, "toVariant") else x
P = f"{OUT}/proj"
MAIN0 = open(f"{P}/Main.qml").read()
backend.openFile(f"{OUT}/work/SettingsPage.qml")
page = win.findChild(QObject, "editorPage")
def find(pred):
    stack = [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): return it
        stack.extend(it.childItems())
def setup():
    global ed, pane, refs, rbar
    ed = find(lambda it: it.metaObject().indexOfProperty("persistentSelection") >= 0 and it.property("persistentSelection"))
    pane = find(lambda it: it.metaObject().indexOfProperty("foldRegions") >= 0)
    refs = find(lambda it: it.metaObject().indexOfProperty("fileCount") >= 0)
    rbar = find(lambda it: it.metaObject().indexOfProperty("oldName") >= 0)
def field_of(item):
    stack = [item]
    while stack:
        it = stack.pop()
        if it.metaObject().className().startswith("TextField") or it.metaObject().indexOfProperty("placeholderText") >= 0: return it
        stack.extend(it.childItems())
def s1():
    page.setProperty("sourceMode", True); QTimer.singleShot(5000, s2)
def s2():
    setup(); ed.forceActiveFocus()
    t = ed.property("text")
    ed.setProperty("cursorPosition", t.index("nameField.text") + 2)
    QTest.keyClick(win, Qt.Key_F12, Qt.ShiftModifier)
    QTimer.singleShot(1500, s3)
def s3():
    res = v(refs.property("results"))
    check(refs.isVisible() and len(res) == 2 and all(r["current"] for r in res), f"Shift+F12: {len(res)} references in this file")
    marks = v(pane.property("referenceMarks"))
    check(len(marks) >= 1, f"references highlighted in the editor ({len(marks)} on screen)")
    win.grabWindow().save(f"{OUT}/refs1.png")
    # click second row -> jump
    QMetaObject.invokeMethod(pane, "gotoReference", Q_ARG("QVariant", res[1]))
    t = ed.property("text"); p = ed.property("cursorPosition")
    check(t[:p].count("\n") == res[1]["line"] and ed.property("selectedText") == "nameField", "clicking a reference jumps and selects it")
    # rename (single file)
    QTest.keyClick(win, Qt.Key_F2)
    check(rbar.isVisible() and rbar.property("oldName") == "nameField", "F2 opens the rename bar")
    f = field_of(rbar); f.setProperty("text", "userField")
    QTest.keyClick(win, Qt.Key_Return)
    QTimer.singleShot(1500, s4)
def s4():
    t = ed.property("text")
    check(t.count("userField") == 2 and "nameField" not in t, "renamed both occurrences")
    res = v(refs.property("results"))
    check(len(res) == 2 and res[0]["match"] == "userField", "references refreshed after rename")
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)
    t = ed.property("text")
    check(t.count("nameField") == 2 and "userField" not in t, "one Ctrl+Z undoes the rename")
    QTest.keyClick(win, Qt.Key_Escape)
    check(not refs.isVisible(), "Esc closes the references")
    # ---- multi-file: open MyButton.qml
    backend.openFile(f"{P}/MyButton.qml")
    page.setProperty("sourceMode", True)
    QTimer.singleShot(4000, s5)
def s5():
    setup(); ed.forceActiveFocus()
    t = ed.property("text")
    ed.setProperty("cursorPosition", t.index("caption:") + 2)
    QTest.keyClick(win, Qt.Key_F12, Qt.ShiftModifier)
    QTimer.singleShot(1500, s6)
def s6():
    res = v(refs.property("results"))
    files = sorted({r["fileName"] for r in res})
    check(files == ["Main.qml", "MyButton.qml"] and len(res) >= 5, f"references across files: {len(res)} in {files}")
    win.grabWindow().save(f"{OUT}/refs2.png")
    QTest.keyClick(win, Qt.Key_F2)
    field_of(rbar).setProperty("text", "title2")
    QTest.keyClick(win, Qt.Key_Return)
    QTimer.singleShot(1500, s7)
def s7():
    dlg = [o for o in pane.children() if o.metaObject().indexOfProperty("others") >= 0][0]
    others = v(dlg.property("others"))
    check(dlg.property("opened") and others and others[0]["fileName"] == "Main.qml", f"confirmation lists other files: {[(o['fileName'], o['count']) for o in others]}")
    win.grabWindow().save(f"{OUT}/refs3.png")
    act = dlg.findChild(QObject, "confirmRenameAction") or pane.findChild(QObject, "confirmRenameAction")
    QMetaObject.invokeMethod(act, "trigger")
    QTimer.singleShot(800, s8)
def s8():
    t = ed.property("text"); main = open(f"{P}/Main.qml").read()
    check("property string title2" in t and "text: title2" in t, "current file renamed in the editor (unsaved)")
    check(main.count("title2") == 3 and "caption" not in main, "Main.qml rewritten on disk")
    print("Main.qml now:", main.replace("\n", " | ")[:160])
    open(f"{P}/Main.qml", "w").write(MAIN0)   # restore test fixture
    app.quit()
QTimer.singleShot(1000, s1)
