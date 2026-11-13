"""The 'Open in' button and Ctrl+Shift+O."""

PLAIN_EDITOR = True

from PySide6.QtCore import QObject, Qt
from PySide6.QtTest import QTest
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
import kreator.backend as B
launched = []
class FP:
    @staticmethod
    def startDetached(p, a, w): launched.append([p, *a]); return (True, 1)
B.QProcess = FP
backend.openFile(f"{OUT}/work/Brackets.qml")
page = win.findChild(QObject, "editorPage")
acts = [a.property("text") for a in page.property("actions")] if False else None
def find(pred):
    stack = [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): return it
        stack.extend(it.childItems())
def s1():
    # toolbar: no "Open in" button
    texts = []
    stack = [win.contentItem()]
    while stack:
        it = stack.pop()
        if it.metaObject().indexOfProperty("text") >= 0 and it.isVisible():
            v = it.property("text")
            if isinstance(v, str) and v.startswith("Open in"):
                texts.append((it.metaObject().className(), v))
        stack.extend(it.childItems())
    check(not texts, f"no 'Open in' button in design view: {texts}")
    QTest.keyClick(win, Qt.Key_O, Qt.ControlModifier | Qt.ShiftModifier)
    check(len(launched) == 1, "Ctrl+Shift+O still opens the editor")
    page.setProperty("sourceMode", True); QTimer.singleShot(800, s2)
def s2():
    global ed, pane
    ed = find(lambda it: it.metaObject().indexOfProperty("persistentSelection") >= 0 and it.property("persistentSelection"))
    pane = find(lambda it: it.metaObject().indexOfProperty("bracketPairs") >= 0)
    ed.forceActiveFocus()
    t = ed.property("text")
    def matched(): 
        v = pane.property("matchedBrackets"); return v.toVariant() if hasattr(v, "toVariant") else v
    o = t.index("ColumnLayout {") + len("ColumnLayout ")
    ed.setProperty("cursorPosition", o)     # before '{'
    m = matched()
    # expected closing brace of ColumnLayout: the "}" at 4-space indent before the final "}"
    close = t.rindex("\n    }") + 5
    check(m == [o, close], f"ColumnLayout braces matched {m} (expected {[o, close]})")
    ed.setProperty("cursorPosition", close + 1)   # after '}'
    check(matched() == [close, o], "match from the closing brace (cursor after it)")
    p = t.index('console.log(') + len("console.log")
    ed.setProperty("cursorPosition", p)
    m = matched(); closep = t.index('")', p) + 1
    check(m == [p, closep], f"parens around a string with brackets inside matched {m} vs {[p, closep]}")
    ed.setProperty("cursorPosition", t.index("tricky") + 2)
    check(matched() == [], "no highlight inside a word")
    win.grabWindow().save(f"{OUT}/brackets.png")
    ed.setProperty("cursorPosition", o)
    QTimer.singleShot(300, lambda: (win.grabWindow().save(f"{OUT}/brackets2.png"), app.quit()))
QTimer.singleShot(1000, s1)
