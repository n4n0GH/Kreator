"""The window without a folder or document."""


from PySide6.QtCore import QObject, Qt, QMetaObject, Q_ARG
from PySide6.QtTest import QTest
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
P = f"{OUT}/proj"
def find_all(pred):
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems())
    return out
def vis_buttons(text):
    return [b for b in find_all(lambda it: it.property("text") == text and it.metaObject().className().startswith(("ToolButton", "QQuickToolButton", "Button", "QQuickButton"))) if b.isVisible()]
backend.openFolder(P)
backend.openFile(f"{P}/Main.qml")
def s1():
    panel = find_all(lambda it: it.metaObject().className().startswith("ProjectPanel"))[0]
    check(not vis_buttons("Close Folder") and len(vis_buttons("Hide Sidebar")) == 1, "sidebar header buttons gone (only the tab bar toggle)")
    QMetaObject.invokeMethod(win, "closeFolder")
    QTimer.singleShot(400, lambda: s2(panel))
def s2(panel):
    check(backend.projectPath == "" and panel.isVisible(), "after Close Folder the sidebar stays")
    check(len(vis_buttons("Open Folder…")) >= 1, "it offers Open Folder…")
    recent = [it for it in find_all(lambda it: it.property("text") == "proj" and it.metaObject().className().startswith("ItemDelegate")) if it.isVisible()]
    check(len(recent) == 1, "recent folder listed")
    win.grabWindow().save(f"{OUT}/nofolder.png")
    QTest.keyClick(win, Qt.Key_F9)
    QTimer.singleShot(300, lambda: s3(panel, recent[0]))
def s3(panel, rec):
    check(not panel.isVisible() and len(vis_buttons("Show Sidebar")) == 1, "F9 hides it, toggle still there without a folder")
    QTest.keyClick(win, Qt.Key_F9)
    QTimer.singleShot(300, lambda: s4(panel, rec))
def s4(panel, rec):
    check(panel.isVisible(), "F9 shows it again")
    QMetaObject.invokeMethod(rec, "clicked")
    QTimer.singleShot(400, lambda: (check(backend.projectPath == P and len(backend.projectFiles.rows()) > 0, "clicking a recent folder reopens it"),
                                    win.grabWindow().save(f"{OUT}/nofolder2.png"), app.quit()))
QTimer.singleShot(800, s1)
