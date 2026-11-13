"""Built-in editor: wrapped rows aligned with the indentation."""

PLAIN_EDITOR = True

from PySide6.QtCore import QObject, Qt, QPointF, QPoint, QEvent
from PySide6.QtGui import QKeyEvent, QGuiApplication
from PySide6.QtTest import QTest
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
def typ(text):
    for ch in text:
        key = Qt.Key(ord(ch.upper())) if ch.isalpha() else Qt.Key_Space
        for t in (QEvent.KeyPress, QEvent.KeyRelease):
            QGuiApplication.sendEvent(win, QKeyEvent(t, key, Qt.NoModifier, ch))
backend.openFile(f"{OUT}/work/Long.qml")
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
    global ed, pane
    ed = find(lambda it: it.metaObject().indexOfProperty("persistentSelection") >= 0 and it.property("persistentSelection"))
    pane = find(lambda it: it.metaObject().indexOfProperty("lineTops") >= 0)
    t = ed.property("text")
    start = t.index('            text: i18n("Changes')   # 12 spaces indent
    first = ed.positionToRectangle(start + 12)          # 't' of text:
    # a character on the 2nd visual row of that line
    pos2 = ed.positionAt(first.x() + 40, first.y() + first.height() * 1.5)
    r2 = ed.positionToRectangle(pos2)
    rowstart = ed.positionAt(0, r2.y() + r2.height() / 2)
    r_rowstart = ed.positionToRectangle(rowstart)
    print(f"first row text starts x={first.x():.1f}; second row starts x={r_rowstart.x():.1f} (y {first.y():.0f} -> {r_rowstart.y():.0f})")
    check(r_rowstart.y() > first.y() and abs(r_rowstart.x() - first.x()) < 1.5, "wrapped row aligned with indentation")
    unindented = ed.positionToRectangle(t.index("import QtQuick"))
    check(abs(unindented.x() - ed.positionToRectangle(0).x()) < 0.5, "unindented lines unaffected")
    win.grabWindow().save(f"{OUT}/hang.png")
    # undo / redo
    ed.forceActiveFocus()
    p = t.index("visible: true") + len("visible: true")
    ed.setProperty("cursorPosition", p)
    typ(" hello")
    check(ed.property("text")[p:p+6] == " hello", "typed")
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)
    check(ed.property("text") == t, "Ctrl+Z undoes the typing in one step")
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier)
    check(ed.property("text")[p:p+6] == " hello", "Ctrl+Shift+Z redoes")
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)
    # tab-indent a selection, then one undo restores
    a = t.index("Kirigami.InlineMessage {"); b = t.index("visible: true", a)
    ed.select(a, b)
    QTest.keyClick(win, Qt.Key_Tab)
    changed = ed.property("text") != t
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)
    check(changed and ed.property("text") == t, "Tab indent undone in one step")
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)
    check(ed.property("text") == t, "no formatting steps in the history (extra undo is a no-op)")
    QTimer.singleShot(300, s3)
def s3():
    # narrow the view: alignment must follow the new width and keep the 80% rule
    pane.setProperty("wrapOverride", False); pane.setProperty("wrapOverridden", True)
    QTimer.singleShot(300, s4)
def s4():
    t = ed.property("text")
    start = t.index('            text: i18n("Changes')
    a = ed.positionToRectangle(start + 12); b = ed.positionToRectangle(start + 200)
    check(abs(a.y() - b.y()) < 1, "wrap off: long line on one row")
    app.quit()
QTimer.singleShot(1000, s1)
