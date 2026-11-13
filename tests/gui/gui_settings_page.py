"""The settings page opens."""


from PySide6.QtCore import QObject
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
page = win.findChild(QObject, "editorPage")
backend.openFile(f"{OUT}/proj/Main.qml")
def s1():
    check(page.property("title") == "Main.qml", "editor page loads a file")
    from PySide6.QtCore import QMetaObject
    QMetaObject.invokeMethod(win, "configureEditors")
    QTimer.singleShot(800, s2)
def s2():
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if it.metaObject().className().startswith("EditorSettingsPage"): out.append(it)
        stack.extend(it.childItems())
    check(bool(out) and out[0].isVisible(), f"settings page opens ({len(out)})")
    backend.discardAll(); QTimer.singleShot(300, app.quit)
QTimer.singleShot(1000, s1)
