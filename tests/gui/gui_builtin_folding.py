"""Built-in editor: code folding."""

PLAIN_EDITOR = True

from PySide6.QtCore import QObject, Qt, QEvent
from PySide6.QtGui import QKeyEvent, QGuiApplication
from PySide6.QtTest import QTest
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
def v(x): return x.toVariant() if hasattr(x, "toVariant") else x
backend.openFile(f"{OUT}/work/SettingsPage.qml")
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
    global ed, pane, t
    ed = find(lambda it: it.metaObject().indexOfProperty("persistentSelection") >= 0 and it.property("persistentSelection"))
    pane = find(lambda it: it.metaObject().indexOfProperty("foldRegions") >= 0)
    ed.forceActiveFocus()
    t = ed.property("text")
    regions = v(pane.property("foldRegions"))
    print("fold regions start lines:", sorted(int(k) + 1 for k in regions))
    check("18" in regions and regions["18"]["endLine"] == 63, "ColumnLayout region lines 19-64")
    lines = t.split("\n")
    pos_after = t.index("\n}") + 1    # last line "}" (line 65)
    y0 = ed.positionToRectangle(pos_after).y(); h0 = ed.property("contentHeight")
    from PySide6.QtCore import QMetaObject, Q_ARG
    QMetaObject.invokeMethod(pane, "toggleFold", Q_ARG("QVariant", 18))
    QTimer.singleShot(300, lambda: s3(pos_after, y0, h0))
def s3(pos_after, y0, h0):
    y1 = ed.positionToRectangle(pos_after).y(); h1 = ed.property("contentHeight")
    check(y1 < y0 - 500, f"lines below moved up ({y0:.0f} -> {y1:.0f})")
    check(h1 < h0 - 500, f"content height shrank ({h0:.0f} -> {h1:.0f})")
    vis = [l["n"] for l in v(pane.property("visibleLines"))]
    check(19 in vis and 20 not in vis and 64 not in vis and 65 in vis, f"gutter skips hidden lines: ...{vis[14:22]}")
    badges = v(pane.property("foldBadges"))
    check(len(badges) == 1 and badges[0]["text"] == "... }", f"badge {[b['text'] for b in badges]}")
    win.grabWindow().save(f"{OUT}/fold1.png")
    # edit above the fold: fold stays
    p = t.index("title:")
    ed.setProperty("cursorPosition", p)
    QGuiApplication.sendEvent(win, QKeyEvent(QEvent.KeyPress, Qt.Key_X, Qt.NoModifier, "x"))
    QTimer.singleShot(200, s4)
def s4():
    check(len(v(pane.property("folds"))) == 1, "fold survives an edit above it")
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)
    # move cursor into folded text -> unfold
    tt = ed.property("text")
    ed.setProperty("cursorPosition", tt.index("spacing: 10"))
    QTimer.singleShot(200, s5)
def s5():
    check(len(v(pane.property("folds"))) == 0, "cursor entering folded code unfolds it")
    # Ctrl+- on cursor inside the TextField block folds that block
    tt = ed.property("text")
    ed.setProperty("cursorPosition", tt.index("id: nameField"))
    QTest.keyClick(win, Qt.Key_Minus, Qt.ControlModifier)
    f = v(pane.property("folds"))
    check(len(f) == 1 and tt[int(f[0]["open"])] == "{" and "QQC2.TextField {" in tt[int(f[0]["open"])-20:int(f[0]["open"])+1], "Ctrl+- folds the current block")
    QTest.keyClick(win, Qt.Key_Equal, Qt.ControlModifier)
    check(len(v(pane.property("folds"))) == 0, "Ctrl+= unfolds it")
    QTest.keyClick(win, Qt.Key_Underscore, Qt.ControlModifier | Qt.ShiftModifier)
    f = v(pane.property("folds"))
    print("top-level folds:", [tt[int(x["open"])-15:int(x["open"])+1].strip() for x in f])
    check(len(f) == 2, "Ctrl+Shift+- folds the root object's children (actions, ColumnLayout)")
    QTimer.singleShot(300, s6)
def s6():
    win.grabWindow().save(f"{OUT}/fold2.png")
    backend.openFile(f"{OUT}/work/dialog.ui")
    page.setProperty("sourceMode", False); page.setProperty("sourceMode", True)
    QTimer.singleShot(800, s7)
def s7():
    regions = v(pane.property("foldRegions"))
    print("ui regions:", len(regions), "first:", sorted(int(k) + 1 for k in regions)[:6])
    check(len(regions) > 10 and "1" in regions, "XML elements are foldable")
    check(len(v(pane.property("folds"))) == 0, "folds reset for a new document")
    app.quit()
QTimer.singleShot(1000, s1)
