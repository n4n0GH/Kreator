"""The project's qmllint list in the Guidelines tab."""

KATE = True
NEEDS = ['qmlls']

import sys as _s, traceback as _t
_s.excepthook = lambda *a: (_t.print_exception(*a), app.exit(3))
import gc, os
from PySide6.QtCore import QObject, Qt, QPointF, QPoint
from PySide6.QtTest import QTest
from kreator.lsp import LanguageSupport
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
lsp = next(o for o in gc.get_objects() if isinstance(o, LanguageSupport))
page = win.findChild(QObject, "editorPage")
D = f"{OUT}/lintproj"
def find_all(pred):
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems())
    return out
def cls(n): return [i for i in find_all(lambda it: it.metaObject().className().startswith(n)) if i.isVisible()]
def diags(): return [(d["file"], d["line"] + 1, d["severity"], d["message"][:40]) for d in lsp.property("projectDiagnostics")]
backend.openFolder(D)
def wait_done(then, n=0):
    if (lsp.property("indexing") or lsp.property("loadingTypes") or lsp._pdiag_timer.isActive()) and n < 600:
        QTimer.singleShot(50, lambda: wait_done(then, n + 1)); return
    QTimer.singleShot(200, then)
def s1():
    d = diags(); print("\n".join(map(str, d)))
    files = {x[0] for x in d}
    check(files == {"Broken.qml", os.path.join("sub", "Warn.qml")}, "diagnostics for the files with problems, none for the clean one, without opening any")
    check(any("colr" in x[3] for x in d) and any("Unqualified" in x[3] for x in d), "qmllint's findings (missing property, unqualified access)")
    check(lsp.property("projectWarningCount") >= 3, f"counts: {lsp.property('projectErrorCount')} errors, {lsp.property('projectWarningCount')} warnings, {lsp.property('projectInfoCount')} notes")
    side = cls("SidePanel")[0]
    side.showTab(3)
    QTimer.singleShot(300, s2)
def s2():
    lv = cls("ProjectLintView")
    check(len(lv) == 1, "Guidelines tab shows the project's qmllint list without a document open")
    tabs = [t for t in cls("SideTab")]
    gl = [t for t in find_all(lambda it: it.metaObject().className().startswith("SideTab")) if "Guidelines" in (t.property("fullText") or "")]
    check(gl and "(" in gl[0].property("fullText"), f"tab label counts them: {gl[0].property('fullText') if gl else None}")
    win.grabWindow().save(f"{OUT}/lint1.png")
    # click the "colr" row
    rows = [r for r in find_all(lambda it: it.objectName() == "lint:Broken.qml:7") if r.isVisible()]
    r = rows[0]
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, r.mapToScene(QPointF(r.width() / 2, r.height() / 2)).toPoint())
    QTimer.singleShot(800, s3)
def s3():
    check(backend.fileName == "Broken.qml" and page.property("sourceMode"), "clicking a finding opens its file in the source view")
    check(page.property("sourceLine") == 6, f"at its line (0-based) ({page.property('sourceLine')})")
    win.grabWindow().save(f"{OUT}/lint2.png")
    # fix it in the source view: the project list follows live
    kate = [e for e in find_all(lambda it: it.objectName() == "kateEditor")]
    if kate:   # Kate's editor: type the fix with real key events
        from PySide6.QtCore import QMetaObject
        k = kate[0]
        QMetaObject.invokeMethod(k, "focusEditor")
        line = next(i for i, l in enumerate(k.property("text").split("\n")) if "colr" in l)
        col = k.property("text").split("\n")[line].index("colr") + 3
        k.setCursorPosition(line, col)
        QTest.keyClick(win, Qt.Key_O, Qt.NoModifier)
    else:
        ed = [e for e in find_all(lambda it: it.metaObject().className().startswith("QQuickTextEdit") and "colr" in (it.property("text") or ""))][0]
        ed.setProperty("text", ed.property("text").replace("colr", "color"))
    QTimer.singleShot(4000, s4)
def s4():
    d = diags()
    check(not any("colr" in x[3] for x in d) and any(x[0] == "Broken.qml" for x in d), f"fixing it in the source view updates the list ({len(d)} left)")
    # collapse a file
    page.setProperty("sourceMode", False)
    cls("SidePanel")[0].showTab(3)
    QTimer.singleShot(300, s4b)
def s4b():
    hdr = [h for h in find_all(lambda it: it.objectName().startswith("lintFile:") and it.objectName().endswith("Warn.qml")) if h.isVisible()]
    win.grabWindow().save(f"{OUT}/lint3.png")
    if hdr:
        s5(hdr[0])
    else:
        check(False, "section header found"); app.quit()
def s5(h):
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, h.mapToScene(QPointF(h.width() / 2, h.height() / 2)).toPoint())
    QTimer.singleShot(300, s6)
def s6():
    vis = [r for r in find_all(lambda it: it.objectName() == "lint:sub/Warn.qml:5") if r.isVisible()]
    hdrs = [h for h in find_all(lambda it: it.objectName().endswith("Warn.qml")) if h.isVisible()]
    check(len(hdrs) == 1, "collapsed file keeps its header")
    check(not vis, "clicking a file header collapses its findings")
    os.remove(f"{D}/sub/Warn.qml")
    QTimer.singleShot(2500, s7)
def s7():
    print(diags())
    check(not any("Warn.qml" in x[0] for x in diags()), "a deleted file's findings go away")
    app.quit()
QTimer.singleShot(300, lambda: wait_done(s1))
