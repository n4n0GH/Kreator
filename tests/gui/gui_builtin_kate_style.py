"""Built-in editor: Kate's theme, font and typing behaviour."""

PLAIN_EDITOR = True

from PySide6.QtCore import QObject, Qt
from PySide6.QtTest import QTest
from PySide6.QtQuick import QQuickItem
from PySide6.QtGui import QKeyEvent, QGuiApplication
from PySide6.QtCore import QEvent
def typ(text):
    for ch in text:
        key = {"{": Qt.Key_BraceLeft, "(": Qt.Key_ParenLeft, ")": Qt.Key_ParenRight, '"': Qt.Key_QuoteDbl,
               " ": Qt.Key_Space, ":": Qt.Key_Colon}.get(ch, Qt.Key(ord(ch.upper())) if ch.isalpha() else Qt.Key_unknown)
        for t in (QEvent.KeyPress, QEvent.KeyRelease):
            QGuiApplication.sendEvent(win, QKeyEvent(t, key, Qt.NoModifier, ch))
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
backend.openFile(f"{OUT}/work/SettingsPage.qml")
print("style:", {k: backend.kateStyle[k] for k in ("enabled", "theme", "fontFamily", "background", "indentWidth")})
page = win.findChild(QObject, "editorPage")
def find_editor():
    stack = [win.contentItem()]
    while stack:
        it = stack.pop()
        if it.metaObject().indexOfProperty("persistentSelection") >= 0 and it.property("persistentSelection"):
            return it
        stack.extend(it.childItems())
def s1():
    global ed
    page.setProperty("sourceMode", True)
    QTimer.singleShot(600, s2)
def s2():
    global ed
    ed = find_editor(); ed.forceActiveFocus()
    t = ed.property("text")
    p = t.index("ColumnLayout {") + len("ColumnLayout {")
    ed.setProperty("cursorPosition", p)
    QTest.keyClick(win, Qt.Key_Return)
    t2 = ed.property("text")
    check(t2[p:p+9] == "\n        " and ed.property("cursorPosition") == p + 9, "enter indents after {")
    typ("Label {")
    t3 = ed.property("text")
    check("Label {}" in t3, "auto-bracket {}")
    QTest.keyClick(win, Qt.Key_Return)
    t4 = ed.property("text")
    i = t4.index("Label {")
    check(t4[i:i+40].startswith("Label {\n            \n        }"), "enter between {} splits block")
    typ('text: ("x"')
    t5 = ed.property("text")
    check('text: ("x")' in t5, "typing over closers / quotes: " + repr(t5[t5.index("text: ("):t5.index("text: (")+14]))
    # comment toggle on this line
    QTest.keyClick(win, Qt.Key_Slash, Qt.ControlModifier)
    check('// text: ("x")' in ed.property("text"), "Ctrl+/ comments")
    QTest.keyClick(win, Qt.Key_Slash, Qt.ControlModifier)
    check('// text' not in ed.property("text"), "Ctrl+/ uncomments")
    # Ctrl+D must not duplicate an object while typing here
    n = backend.sourceText.count("spinBox")
    QTest.keyClick(win, Qt.Key_D, Qt.ControlModifier)
    check(backend.sourceText.count("ColumnLayout") == 1, "object shortcuts off in source view")
    # select 2 lines and indent / unindent
    t = ed.property("text"); a = t.index("Kirigami.InlineMessage {"); b = t.index("Layout.fillWidth: true", a) + 3
    ed.select(a, b)
    QTest.keyClick(win, Qt.Key_Tab)
    check("            Kirigami.InlineMessage {\n                Layout.fillWidth" in ed.property("text"), "Tab indents selection")
    QTest.keyClick(win, Qt.Key_Backtab, Qt.ShiftModifier)
    check("        Kirigami.InlineMessage {\n            Layout.fillWidth" in ed.property("text"), "Shift+Tab unindents")
    QTest.keyClick(win, Qt.Key_Return, Qt.ControlModifier)
    QTimer.singleShot(500, s3)
def s3():
    check("Label {" in backend.sourceText and backend.sourceError == "", "Ctrl+Return applies: " + backend.sourceError)
    ed.setProperty("cursorPosition", ed.property("text").index("Kirigami.FormLayout"))
    QTimer.singleShot(300, lambda: (win.grabWindow().save(f"{OUT}/kateedit.png"), app.quit()))
QTimer.singleShot(1000, s1)
