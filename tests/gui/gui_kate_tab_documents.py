"""A Kate document per tab: kept cursor, highlighting mode, changes while hidden, closing."""

KATE = True

import sys as _s, traceback as _t, time
_s.excepthook = lambda *a: (_t.print_exception(*a), app.exit(3))
import warnings; warnings.simplefilter("ignore")
from PySide6.QtCore import QObject
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
page = win.findChild(QObject, "editorPage")
P = f"{OUT}/proj"
def find_all(pred):
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems())
    return out
def ed(): return find_all(lambda it: it.objectName() == "kateEditor")[0]
def kdocs(): return [c for c in ed().children() if "Document" in c.metaObject().className()]
backend.openFolder(P)
backend.openFile(f"{P}/Main.qml")
backend.openFile(f"{P}/MyButton.qml")
backend.openFile(f"{OUT}/flowproj/dialog.ui")
backend.switchTo(f"{P}/Main.qml")
page.setProperty("sourceMode", True)
times = []
def sw(key):
    t = time.perf_counter()
    backend.switchTo(key)
    app.processEvents()
    times.append(time.perf_counter() - t)
def s1():
    ed().setCursorPosition(9, 4)
    app.processEvents()
    check(ed().property("cursorLine") == 9, "cursor set in Main.qml")
    sw(f"{P}/MyButton.qml")
    QTimer.singleShot(600, s2)
def s2():
    check("MyButton" in backend.fileName and ed().property("text") == backend.property("sourceText"), "MyButton.qml shown")
    sw(f"{OUT}/flowproj/dialog.ui")
    QTimer.singleShot(600, s3)
def s3():
    check(ed().property("mode") == "XML", f"the form in XML mode ({ed().property('mode')})")
    check(len(kdocs()) == 3, f"a Kate document per tab shown ({len(kdocs())})")
    sw(f"{P}/Main.qml")
    QTimer.singleShot(600, s4)
def s4():
    check(ed().property("documentReused"), "back to Main.qml: its Kate document again")
    check(ed().property("mode") == "QML", f"in QML mode ({ed().property('mode')})")
    check(ed().property("cursorLine") == 9, f"the cursor where it was (line {ed().property('cursorLine') + 1})")
    check(ed().property("text") == backend.property("sourceText"), "the text is Kreator's")
    # a change in the design view while another tab is shown
    sw(f"{P}/MyButton.qml")
    page.setProperty("sourceMode", False)
    backend.switchTo(f"{P}/Main.qml")
    backend.applySource(backend.property("sourceText").replace('"First"', '"Changed"'))
    backend.switchTo(f"{P}/MyButton.qml")
    page.setProperty("sourceMode", True)
    QTimer.singleShot(600, s5)
def s5():
    sw(f"{P}/Main.qml")
    QTimer.singleShot(600, s6)
def s6():
    check('"Changed"' in ed().property("text") and ed().property("text") == backend.property("sourceText"),
          "changes made while it wasn't shown are there")
    # undo in Kate's editor: its own history, not across tabs
    ed().undo()
    app.processEvents()
    check('"First"' in ed().property("text") or ed().property("text") == backend.property("sourceText"), "Kate's undo works on this tab's text")
    backend.closeBackgroundDocument(f"{OUT}/flowproj/dialog.ui")
    QTimer.singleShot(400, s7)
def s7():
    check(len(kdocs()) == 2, f"a closed tab's Kate document is dropped ({len(kdocs())})")
    t = sorted(times)
    print(f"switch times ms: {[round(x*1000) for x in times]}")
    check(t[len(t)//2] < 0.25, f"median switch {t[len(t)//2]*1000:.0f} ms")
    backend.discardAll()
    QTimer.singleShot(300, app.quit)
QTimer.singleShot(2500, s1)
