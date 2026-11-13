"""Quitting with unsaved documents (when the session doesn't keep them)."""

SETTINGS = {'keepUnsaved': False}

from PySide6.QtCore import QObject, QMetaObject, Q_ARG
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
P = f"{OUT}/proj"
page = win.findChild(QObject, "editorPage")
backend.openFolder(P)
QMetaObject.invokeMethod(win, "switchFile", Q_ARG("QVariant", f"{P}/Main.qml"))
def s1():
    u = next(r["uid"] for r in backend.outline.rows() if r["typeName"] == "MyButton")
    backend.select(u); backend.setProperty("caption", "string", "One")
    QMetaObject.invokeMethod(win, "switchFile", Q_ARG("QVariant", f"{P}/MyButton.qml"))
    # MyButton unmodified; edit it on disk while it is shown -> auto reload (existing feature)
    # now switch away and change it on disk in the background
    QMetaObject.invokeMethod(win, "switchFile", Q_ARG("QVariant", f"{P}/forms/dialog.ui"))
    t = open(f"{P}/MyButton.qml").read().replace('"Hello"', '"Changed outside"')
    open(f"{P}/MyButton.qml", "w").write(t)
    QMetaObject.invokeMethod(win, "switchFile", Q_ARG("QVariant", f"{P}/MyButton.qml"))
    QTimer.singleShot(1500, s2)
def s2():
    check('"Changed outside"' in backend.property("sourceText"), "background file changed on disk is reloaded on switching back")
    backend.setProperty("caption", "string", "Two") if False else None
    # quit with unsaved Main
    win.close()
    QTimer.singleShot(500, s3)
def s3():
    dlg = [o for o in win.findChildren(QObject) if o.metaObject().indexOfProperty("actionName") >= 0][0]
    names = dlg.property("subtitle")
    check(dlg.property("opened") and "Main.qml" in names, "quitting asks about unsaved background documents: " + names.replace("\n", " | "))
    win.grabWindow().save(f"{OUT}/proj_quit.png")
    dlg.close()
    open(f"{P}/MyButton.qml", "w").write(open(f"{P}/MyButton.orig").read())
    backend.discardAll()
    app.quit()
QTimer.singleShot(1200, s1)
