"""Document tabs: opening, switching, modified marks, closing."""


from PySide6.QtCore import QObject, Qt, QMetaObject, Q_ARG
from PySide6.QtTest import QTest
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
def v(x): return x.toVariant() if hasattr(x, "toVariant") else x
P = f"{OUT}/proj"
page = win.findChild(QObject, "editorPage")
def find_all(pred):
    out = []; stack = [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems())
    return out
def tabs(): return [(d["name"], d["current"], d["modified"]) for d in v(backend.property("openDocuments"))]
backend.openFolder(P)
for f in ("Main.qml", "MyButton.qml", "forms/dialog.ui"):
    QMetaObject.invokeMethod(win, "switchFile", Q_ARG("QVariant", f"{P}/{f}"))
def s1():
    print("tabs:", tabs())
    check([t[0] for t in tabs()] == ["Main.qml", "MyButton.qml", "dialog.ui"] and tabs()[2][1], "three tabs in opening order, last one current")
    # toolbar: Open/Save/Undo/Redo on the left, no file name heading
    from PySide6.QtCore import QPointF
    btns = find_all(lambda it: it.metaObject().className().startswith("ToolButton") and it.isVisible() and it.mapToScene(QPointF(0, 0)).y() < 40)
    btns.sort(key=lambda b: b.mapToScene(QPointF(0, 0)).x())
    texts = [b.property("text") for b in btns]
    print("toolbar buttons with actions:", texts[:8])
    check(texts[:4] == ["Open…", "Save", "Undo", "Redo"], "Open/Save/Undo/Redo at the left of the toolbar")
    headings = [h for h in find_all(lambda it: it.metaObject().className().startswith("Heading") and it.isVisible())]
    check(not any(h.property("text") in ("dialog.ui",) for h in headings), "no file name heading in the toolbar")
    QTest.keyClick(win, Qt.Key_Tab, Qt.ControlModifier)
    QTimer.singleShot(600, s2)
def s2():
    check(tabs()[0][1], "Ctrl+Tab wraps to the first tab")
    QTest.keyClick(win, Qt.Key_Tab, Qt.ControlModifier | Qt.ShiftModifier)
    QTimer.singleShot(600, s3)
def s3():
    check(tabs()[2][1], "Ctrl+Shift+Tab goes back")
    # modify MyButton in background then close its tab -> asks
    QMetaObject.invokeMethod(win, "switchFile", Q_ARG("QVariant", f"{P}/MyButton.qml"))
    backend.setProperty("caption", "string", "Edited")
    QMetaObject.invokeMethod(win, "switchFile", Q_ARG("QVariant", f"{P}/Main.qml"))
    check(tabs()[1][2], "MyButton tab marked modified")
    win.grabWindow().save(f"{OUT}/tabs1.png")
    # close an unmodified background tab directly
    QMetaObject.invokeMethod(win, "closeTab", Q_ARG("QVariant", f"{P}/forms/dialog.ui"))
    check([t[0] for t in tabs()] == ["Main.qml", "MyButton.qml"], "closing an unmodified background tab")
    # close the modified one -> switches to it and asks
    QMetaObject.invokeMethod(win, "closeTab", Q_ARG("QVariant", f"{P}/MyButton.qml"))
    QTimer.singleShot(400, s4)
def s4():
    dlg = [o for o in win.findChildren(QObject) if o.metaObject().indexOfProperty("customFooterActions") >= 0 and o.property("opened")]
    check(dlg and backend.property("fileName") == "MyButton.qml", "closing a modified tab shows it and asks")
    dlg[0].close()
    backend.discardAll() if False else None
    # close current unmodified Main -> neighbour
    QMetaObject.invokeMethod(win, "switchFile", Q_ARG("QVariant", f"{P}/Main.qml"))
    QMetaObject.invokeMethod(win, "closeTab", Q_ARG("QVariant", f"{P}/Main.qml"))
    QTimer.singleShot(400, s5)
def s5():
    check([t[0] for t in tabs()] == ["MyButton.qml"] and backend.property("fileName") == "MyButton.qml", "closing the current tab shows its neighbour")
    # folder sidebar collapse
    panel = find_all(lambda it: it.metaObject().className().startswith("ProjectPanel"))[0]
    check(panel.isVisible(), "folder sidebar shown")
    QTest.keyClick(win, Qt.Key_F9)
    QTimer.singleShot(300, lambda: s6(panel))
def s6(panel):
    check(not panel.isVisible(), "F9 hides the folder sidebar")
    win.grabWindow().save(f"{OUT}/tabs2.png")
    QTest.keyClick(win, Qt.Key_F9)
    QTimer.singleShot(300, lambda: (check(panel.isVisible(), "F9 shows it again"), backend.discardAll(), app.quit()))
QTimer.singleShot(1500, s1)
