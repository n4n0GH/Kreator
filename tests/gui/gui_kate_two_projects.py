"""Kate's LSP client with files of two projects: a server each, kept running."""

KATE = True
NEEDS = ['qmlls']

import sys as _s, traceback as _t, time, os, subprocess
_s.excepthook = lambda *a: (_t.print_exception(*a), app.exit(3))
import warnings; warnings.simplefilter("ignore")
from PySide6.QtCore import QObject, QMetaObject
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
page = win.findChild(QObject, "editorPage")
def find_all(pred):
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems() if hasattr(it, "childItems") else [])
    return out
def wait(pred, timeout, then, what):
    t0 = time.time()
    def tick():
        try: ok = pred()
        except Exception: ok = False
        if ok: then()
        elif time.time() - t0 > timeout:
            check(False, f"{what} (timed out)"); then()
        else: QTimer.singleShot(250, tick)
    tick()
def procs():
    kids = subprocess.run(["ps", "-o", "pid=,args=", "--ppid", str(os.getpid())], capture_output=True, text=True).stdout
    return [l for l in kids.splitlines() if "qmlls" in l]
backend.openFile(f"{OUT}/proj/Main.qml")
page.setProperty("sourceMode", True)
def area():
    return find_all(lambda it: it.objectName() == "kateToolArea")[0]
def s1():
    globals()["ed"] = find_all(lambda it: it.objectName() == "kateEditor")[0]
    QTimer.singleShot(4000, s2)
def s2():
    globals()["first"] = procs()
    check(len(first) == 1, f"one qmlls ({len(first)})")
    # a file of another folder: Kreator's server restarts for that root
    backend.openFile(f"{OUT}/lintproj/Broken.qml")
    wait(lambda: any("Broken.qml" in x for x in area().itemTexts("Diagnostics")), 25, s3,
         "Kate's diagnostics for the file of the other folder")
def s3():
    now = procs()
    check(len(now) == 2 and first[0] in now, f"a second qmlls for the other folder; the first keeps running ({len(now)})")
    texts = area().itemTexts("Diagnostics")
    check(any("Broken.qml" in x for x in texts), "Kate's client works with the new server")
    # back: the first server again (no restart, no new process)
    backend.switchTo(f"{OUT}/proj/Main.qml")
    QTimer.singleShot(2500, s4)
def s4():
    now = procs()
    check(len(now) == 2 and first[0] in now, f"back to the first folder: no new qmlls ({len(now)})")
    from PySide6.QtCore import Qt, QEvent
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication
    t = ed.property("text")
    ed.setProperty("text", t.replace("ApplicationWindow {", "ApplicationWindow {\n    notAThing: 1", 1))
    ed.setCursorPosition(1, 0)
    for tp in (QEvent.KeyPress, QEvent.KeyRelease):
        QApplication.sendEvent(win, QKeyEvent(tp, Qt.Key_unknown, Qt.NoModifier, " "))
    wait(lambda: any("notAThing" in x for x in area().itemTexts("Diagnostics")), 25, s5,
         "Kate's client gets diagnostics from the first server again")
def s5():
    check(any("notAThing" in x for x in area().itemTexts("Diagnostics")), "Kate's client works with the first server again")
    backend.discardAll()
    QTimer.singleShot(300, app.quit)
QTimer.singleShot(1500, s1)
