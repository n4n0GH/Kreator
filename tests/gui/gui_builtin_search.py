"""Built-in editor: search and replace."""

PLAIN_EDITOR = True

from PySide6.QtCore import QObject, Qt, QEvent, QMetaObject, Q_ARG
from PySide6.QtGui import QKeyEvent, QGuiApplication
from PySide6.QtTest import QTest
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
def v(x): return x.toVariant() if hasattr(x, "toVariant") else x
def typ(text):
    for ch in text:
        key = Qt.Key(ord(ch.upper())) if ch.isalnum() and ord(ch) < 128 else Qt.Key_unknown
        for tp in (QEvent.KeyPress, QEvent.KeyRelease):
            QGuiApplication.sendEvent(win, QKeyEvent(tp, key, Qt.NoModifier, ch))
backend.openFile(f"{OUT}/work/Big.qml")
page = win.findChild(QObject, "editorPage")
def find(pred):
    stack = [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): return it
        stack.extend(it.childItems())
def s1():
    page.setProperty("sourceMode", True); QTimer.singleShot(800, s2)
def s2():
    global ed, pane, flick, bar
    ed = find(lambda it: it.metaObject().indexOfProperty("persistentSelection") >= 0 and it.property("persistentSelection"))
    pane = find(lambda it: it.metaObject().indexOfProperty("foldRegions") >= 0)
    bar = find(lambda it: it.metaObject().indexOfProperty("replaceMode") >= 0)
    flick = ed.parentItem().parentItem().parentItem()
    ed.forceActiveFocus()
    t = ed.property("text")
    ed.setProperty("cursorPosition", t.index("id: label3"))       # caret near the top
    flick.setProperty("contentY", 1800)                            # user scrolled far down
    regions = v(pane.property("foldRegions"))
    # a region whose top is on screen at contentY 1800
    tops = v(pane.property("lineTops"))
    line = next(int(k) for k in sorted(regions, key=int) if 1800 < tops[int(k)] < 1800 + flick.height() - 60)
    y0 = flick.property("contentY")
    QMetaObject.invokeMethod(pane, "toggleFold", Q_ARG("QVariant", line))
    QTimer.singleShot(300, lambda: s3(y0, line))
def s3(y0, line):
    check(abs(flick.property("contentY") - y0) < 1, f"folding line {line+1} far from the caret keeps the view ({y0:.0f} -> {flick.property('contentY'):.0f})")
    QMetaObject.invokeMethod(pane, "unfoldAll")
    # ---- search
    ed.setProperty("cursorPosition", 0); ed.forceActiveFocus()
    afi = win.activeFocusItem()
    print("focus item:", afi.metaObject().className() if afi else None, afi is ed or (afi and afi == ed))
    QTest.keyClick(win, Qt.Key_F, Qt.ControlModifier)
    check(bar.isVisible(), "Ctrl+F opens the bar")
    typ("row 1")
    ms = v(bar.property("matches"))
    check(len(ms) == 11, f"case-insensitive 'row 1' finds Row 1, Row 10..19: {len(ms)}")
    sel = ed.property("selectedText")
    check(sel == "Row 1", "first match selected incrementally")
    QTest.keyClick(win, Qt.Key_Return)
    check(bar.property("current") == 1, "Enter goes to next")
    QTest.keyClick(win, Qt.Key_Return, Qt.ShiftModifier)
    check(bar.property("current") == 0, "Shift+Enter goes back")
    QTest.keyClick(win, Qt.Key_Return, Qt.ShiftModifier)
    check(bar.property("current") == 10 and "bottom" in bar.property("notice"), "wraps around: " + bar.property("notice"))
    # whole words
    find(lambda it: it.metaObject().indexOfProperty("checkable") >= 0 and it.property("text") == "\\b").setProperty("checked", True)
    QMetaObject.invokeMethod(bar, "search", Q_ARG("QVariant", False))
    check(len(v(bar.property("matches"))) == 1, f"whole words: only 'Row 1' -> {len(v(bar.property('matches')))}")
    win.grabWindow().save(f"{OUT}/search1.png")
    find(lambda it: it.metaObject().indexOfProperty("checkable") >= 0 and it.property("text") == "\\b").setProperty("checked", False)
    # regex replace with groups, replace all = one undo step
    rx = find(lambda it: it.metaObject().indexOfProperty("checkable") >= 0 and it.property("text") == ".*")
    rx.setProperty("checked", True)
    fields = []
    stack = [bar]
    while stack:
        it = stack.pop()
        if it.metaObject().indexOfProperty("placeholderText") >= 0: fields.append(it)
        stack.extend(it.childItems())
    findf = next(f for f in fields if "Find" in f.property("placeholderText"))
    repf = next(f for f in fields if "Replace" in f.property("placeholderText"))
    findf.setProperty("text", r'Row (\d+)')
    repf.setProperty("text", r'Item \1')
    before = ed.property("text")
    QMetaObject.invokeMethod(bar, "replaceAll")
    after = ed.property("text")
    check('i18n("Item 39")' in after and "Row 7" not in after, "regex Replace All with \\1")
    check("Replaced 40" in bar.property("notice"), bar.property("notice"))
    ed.forceActiveFocus()
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)
    check(ed.property("text") == before, "Replace All undone in one step")
    # invalid regex
    findf.setProperty("text", "Row (")
    check(bar.property("error") != "", "invalid regex reported: " + bar.property("error"))
    # search into folded code unfolds
    rx.setProperty("checked", False)
    findf.setProperty("text", "")
    QMetaObject.invokeMethod(pane, "foldTopLevel", Q_ARG("QVariant", True))
    QTimer.singleShot(300, s4)
def s4():
    check(len(v(pane.property("folds"))) >= 1, "folded")
    fields = []
    stack = [bar]
    while stack:
        it = stack.pop()
        if it.metaObject().indexOfProperty("placeholderText") >= 0: fields.append(it)
        stack.extend(it.childItems())
    findf = next(f for f in fields if "Find" in f.property("placeholderText"))
    findf.setProperty("text", "label25")
    QTimer.singleShot(300, s5)
def s5():
    check(ed.property("selectedText") == "label25" and not v(pane.property("hiddenLines")).get(str(int(ed.property("text")[:ed.property("cursorPosition")].count("\n")))), "match inside folded code is revealed")
    win.grabWindow().save(f"{OUT}/search2.png")
    QTest.keyClick(win, Qt.Key_Escape)
    check(not bar.isVisible(), "Esc closes the bar")
    app.quit()
QTimer.singleShot(1000, s1)
