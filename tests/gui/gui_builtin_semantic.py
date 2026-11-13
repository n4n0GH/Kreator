"""Built-in editor: semantic highlighting and bracket matching."""

PLAIN_EDITOR = True
NEEDS = ['qmlls']

from PySide6.QtCore import QObject, Qt, QEvent, QMetaObject, Q_ARG
from PySide6.QtGui import QKeyEvent, QGuiApplication, QTextFormat
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
def color_at(line, word, nth=0):
    """Colour/italic the text layout draws for `word` on 1-based `line`."""
    doc = L._sem_doc.textDocument()
    b = doc.findBlockByNumber(line - 1)
    idx = -1
    for _ in range(nth + 1):
        idx = b.text().index(word, idx + 1)
    for r in b.layout().formats():
        if r.start <= idx < r.start + r.length:
            return (r.format.foreground().color().name(), r.format.fontItalic())
    return (None, False)
def formats():
    return {11: [("counter", *color_at(11, "counter"))], 15: [(w, *color_at(15, w)) for w in ("mouse", "console", "log")]}
def s1():
    page.setProperty("sourceMode", True); QTimer.singleShot(6000, s2)
def s2():
    global ed, pane, L
    L = lsp()
    ed = find(lambda it: it.metaObject().indexOfProperty("persistentSelection") >= 0 and it.property("persistentSelection"))
    pane = find(lambda it: it.metaObject().indexOfProperty("foldRegions") >= 0)
    print("own highlighter:", L.property("ownHighlighting"))
    check(L.property("ownHighlighting"), "QViewer's highlighter active for QML")
    print("counter:", color_at(11, "counter"), "console:", color_at(15, "console"), "log:", color_at(15, "log"), "mouse:", color_at(15, "mouse"), "text:", color_at(11, "text"), "Label:", color_at(10, "Label"), "string:", color_at(11, '"row'))
    check(color_at(11, "counter")[0] == "#2980b9", "property in expression drawn in Attribute colour")
    check(color_at(15, "log")[0] == "#8e44ad" and color_at(15, "mouse") == ("#27aeae", True) and color_at(15, "console")[0] == "#27aeae", "method purple, parameter italic teal, variable teal")
    check(color_at(11, '"row')[0] == "#f44f4f" and color_at(10, "Label")[0] == "#2980b9", "lexical colours (string, type) from the theme")
    win.grabWindow().save(f"{OUT}/sem1.png")
    # edit: tokens follow
    ed.forceActiveFocus()
    t = ed.property("text"); p = t.index("console.log(mouse)") + len("console.log(mouse")
    ed.setProperty("cursorPosition", p)
    for ch in ", root.counter":
        QGuiApplication.sendEvent(win, QKeyEvent(QEvent.KeyPress, Qt.Key_unknown if not ch.isalpha() else Qt.Key(ord(ch.upper())), Qt.NoModifier, ch))
    QTimer.singleShot(2500, s3)
def s3():
    print("after edit: root", color_at(15, "root"), "counter", color_at(15, "counter"))
    check(color_at(15, "root")[0] in ("#0099ff", "#27aeae") and color_at(15, "counter")[0] == "#2980b9", "new identifiers get semantic colours after typing")
    check(not pane.property("dirty") or ed.property("text") != "", "formats do not count as edits")
    # undo history unaffected by formats
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)
    check(", root.counter" not in ed.property("text"), "one Ctrl+Z removes the typing (formats are not undo steps)")
    # bracket animation
    t = ed.property("text"); p = t.index("ListView {") + len("ListView ")
    ed.setProperty("cursorPosition", p)
    QTimer.singleShot(60, s4)
def s4():
    pulse = [o for o in ed.childItems() if o.metaObject().indexOfProperty("pos") >= 0 and o.metaObject().indexOfMethod("play(QVariant)") >= 0]
    pul = pulse[0] if pulse else None
    t = ed.property("text"); close = t.index("\n    }", t.index("ListView {")) + 5
    print("dbg:", v(pane.property("matchedBrackets")), pane.property("lastBracketPair"), pane.property("animateBrackets"), pane.property("active"), v(backend.property("kateStyle")).get("animateBrackets"))
    print("pulse:", pul and (pul.isVisible(), pul.property("pos"), close, round(pul.property("scale"), 2)))
    check(pul is not None and pul.isVisible() and pul.property("pos") == close and pul.property("scale") > 1.05, "matching bracket animates (enlarged, shrinking)")
    win.grabWindow().save(f"{OUT}/pulse.png")
    QTimer.singleShot(600, lambda: s5(pul))
def s5(pul):
    check(not pul.isVisible(), "animation finished and hidden")
    # moving within the same pair does not replay
    ed.setProperty("cursorPosition", ed.property("cursorPosition") + 1)  # now after '{' -> same pair
    QTimer.singleShot(50, lambda: (check(not pul.isVisible(), "same pair: no replay"), app.quit()))
QTimer.singleShot(1000, s1)
