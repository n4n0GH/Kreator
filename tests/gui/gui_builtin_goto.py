"""Built-in editor: go to definition and go to line."""

PLAIN_EDITOR = True
NEEDS = ['qmlls']

from PySide6.QtCore import QObject, Qt, QEvent, QMetaObject, Q_ARG
from PySide6.QtGui import QKeyEvent, QGuiApplication
from PySide6.QtTest import QTest
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
def v(x): return x.toVariant() if hasattr(x, "toVariant") else x
def typ(text):
    for ch in text:
        key = {":": Qt.Key_Colon, "+": Qt.Key_Plus, "-": Qt.Key_Minus, "x": Qt.Key_X}.get(ch, Qt.Key(ord(ch)) if ch.isdigit() else Qt.Key_unknown)
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
def line(): return ed.property("text")[:ed.property("cursorPosition")].count("\n") + 1
def col(): t = ed.property("text"); p = ed.property("cursorPosition"); return p - (t.rfind("\n", 0, p) + 1) + 1
def s1():
    page.setProperty("sourceMode", True); QTimer.singleShot(800, s2)
def s2():
    global ed, pane, gbar, flick
    ed = find(lambda it: it.metaObject().indexOfProperty("persistentSelection") >= 0 and it.property("persistentSelection"))
    pane = find(lambda it: it.metaObject().indexOfProperty("foldRegions") >= 0)
    gbar = find(lambda it: it.metaObject().indexOfProperty("error") >= 0 and it.metaObject().indexOfMethod("go()") >= 0)
    flick = ed.parentItem().parentItem().parentItem()
    ed.forceActiveFocus()
    QTest.keyClick(win, Qt.Key_G, Qt.ControlModifier)
    check(gbar.isVisible(), "Ctrl+G opens the bar")
    typ("150"); QTest.keyClick(win, Qt.Key_Return)
    check(line() == 150 and not gbar.isVisible() and ed.hasActiveFocus(), f"jumped to line {line()}, bar closed, editor focused")
    r = ed.positionToRectangle(ed.property("cursorPosition"))
    check(flick.property("contentY") < r.y() < flick.property("contentY") + flick.height(), "target line visible")
    QTest.keyClick(win, Qt.Key_G, Qt.ControlModifier); typ("33:13"); QTest.keyClick(win, Qt.Key_Return)
    check(line() == 33 and col() == 13, f"line:column -> {line()}:{col()}")
    QTest.keyClick(win, Qt.Key_G, Qt.ControlModifier); typ("+10"); QTest.keyClick(win, Qt.Key_Return)
    check(line() == 43, f"relative +10 -> {line()}")
    QTest.keyClick(win, Qt.Key_G, Qt.ControlModifier); typ("99999"); QTest.keyClick(win, Qt.Key_Return)
    check(line() == len(ed.property("text").split("\n")), f"past the end clamps to last line {line()}")
    QTest.keyClick(win, Qt.Key_G, Qt.ControlModifier); typ("x"); QTest.keyClick(win, Qt.Key_Return)
    check(gbar.isVisible() and gbar.property("error") != "", "invalid input keeps bar open with a hint")
    QTest.keyClick(win, Qt.Key_Escape)
    check(not gbar.isVisible(), "Esc closes")
    # into folded code
    QMetaObject.invokeMethod(pane, "foldTopLevel", Q_ARG("QVariant", True))
    QTest.keyClick(win, Qt.Key_G, Qt.ControlModifier); typ("120"); QTest.keyClick(win, Qt.Key_Return)
    QTimer.singleShot(300, s3)
def s3():
    check(line() == 120 and not v(pane.property("hiddenLines")).get("119"), "going into folded code unfolds it")
    QTest.keyClick(win, Qt.Key_G, Qt.ControlModifier)
    QTimer.singleShot(200, lambda: (win.grabWindow().save(f"{OUT}/goto.png"), app.quit()))
QTimer.singleShot(1000, s1)
