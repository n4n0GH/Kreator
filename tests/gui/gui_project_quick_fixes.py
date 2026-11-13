"""qmllint quick fixes from the project list, as unsaved changes."""

NEEDS = ['qmlls']

import sys as _s, traceback as _t
_s.excepthook = lambda *a: (_t.print_exception(*a), app.exit(3))
import gc, os
from PySide6.QtCore import QObject, Qt, QPointF
from PySide6.QtTest import QTest
from kreator.lsp import LanguageSupport
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
lsp = next(o for o in gc.get_objects() if isinstance(o, LanguageSupport))
page = win.findChild(QObject, "editorPage")
D = f"{OUT}/fixproj"
def find_all(pred):
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems())
    return out
def rows(): return lsp.property("projectDiagnostics")
def row(file, pred): return next((r for r in rows() if r["file"] == file and pred(r)), None)
def click(item):
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint())
def fix_button(file, line):
    r = [x for x in find_all(lambda it: it.objectName() == f"lint:{file}:{line}") if x.isVisible()]
    if not r: return None
    b = [x for x in find_all(lambda it: it.objectName() == "lintFix") if x.isVisible()]
    rr = r[0].mapToScene(QPointF(0, 0)).y(); h = r[0].height()
    return next((x for x in b if rr <= x.mapToScene(QPointF(0, 0)).y() <= rr + h), None)
def wait_done(then, n=0):
    if (lsp.property("indexing") or lsp._pdiag_timer.isActive()) and n < 600:
        QTimer.singleShot(50, lambda: wait_done(then, n + 1)); return
    QTimer.singleShot(300, then)
backend.openFolder(D)
backend.openFile(f"{D}/Current.qml")
def s1():
    for r in rows(): print("  ", r["file"], r["line"] + 1, r["message"][:50], "| fix:", r["fix"], "auto" if r["autoFix"] else "", "needsInput" if r["needsInput"] else "")
    c = row("Fixes.qml", lambda r: "colr" in r["message"])
    q = row("Fixes.qml", lambda r: "Unqualified" in r["message"])
    ni = row("NoId.qml", lambda r: "Unqualified" in r["message"])
    check(c and c["fix"] and not c["autoFix"], f"suggestion fix offered: {c and c['fix']}")
    check(q and q["autoFix"], f"safe fix offered: {q and q['fix']}")
    check(ni and ni["needsInput"] and not ni["fix"], "a fix that needs an id is marked as such")
    win.findChild(QObject, "editorPage")
    [x for x in find_all(lambda it: it.metaObject().className().startswith("SidePanel"))][0].showTab(3)
    # the HIG/qmllint switch: a document is open, choose qmllint
    btn = [x for x in find_all(lambda it: it.property("text") and str(it.property("text")).startswith("qmllint")) if x.isVisible()][0]
    click(btn)
    QTimer.singleShot(300, s2)
def s2():
    win.grabWindow().save(f"{OUT}/fix1.png")
    b = fix_button("Fixes.qml", 7)
    check(b is not None and b.property("text") == "Fix", "Fix button on the row")
    nb = fix_button("NoId.qml", 6)
    check(nb is not None and nb.property("text") == "Fix…", "'Fix…' for the one needing an id")
    click(b)
    QTimer.singleShot(200, lambda: wait_done(s3))
def s3():
    disk = open(f"{D}/Fixes.qml").read()
    st = backend.docs.get(f"{D}/Fixes.qml")
    check("colr" in disk, "nothing written to disk")
    check(st is not None and st.modified and 'color: "red"' in st.adapter.text(), "the file opened as a background tab with the fix as an unsaved change")
    check(backend.currentKey == f"{D}/Current.qml", "the shown document stays")
    check(not row("Fixes.qml", lambda r: "colr" in r["message"]), "the finding is gone after re-checking")
    # Fix All: the safe 'root.' qualifications
    n_auto = sum(1 for r in rows() if r["autoFix"])
    n = lsp.applyProjectFixes("")
    print("auto fixes", n_auto, "applied", n)
    QTimer.singleShot(200, lambda: wait_done(s4))
def s4():
    t = backend.docs[f"{D}/Fixes.qml"].adapter.text()
    check("width: root.n" in t and "height: root.n" in t, "Fix All applied the safe fixes")
    check(not any(r["autoFix"] for r in rows()), "no safe fixes left")
    # undo in that tab
    backend.switchTo(f"{D}/Fixes.qml")
    backend.undo()
    t = backend.property("sourceText")
    check("root.n" not in t and 'color: "red"' in t, "undo takes the Fix All back")
    backend.undo()
    check("colr" in backend.property("sourceText") and not backend.modified, "and the first fix")
    QTimer.singleShot(1200, lambda: wait_done(s4b))
def s4b():
    check(row("Fixes.qml", lambda r: "colr" in r["message"]) is not None, "after undo the finding is back in the list")
    # the shown document, in the design view
    backend.switchTo(f"{D}/Current.qml")
    QTimer.singleShot(300, s5)
def s5():
    c = row("Current.qml", lambda r: "colr" in r["message"])
    ok = lsp.applyProjectFix(c["path"], c["index"])
    check(ok and backend.modified and 'color: "blue"' in backend.property("sourceText"), "fix in the shown document (design view)")
    QTimer.singleShot(200, lambda: wait_done(s6))
def s6():
    check(not row("Current.qml", lambda r: "colr" in r["message"]), "its finding goes away")
    # stale text is refused
    with open(f"{D}/NoId.qml", "a") as fh: fh.write("\n")
    ni = row("NoId.qml", lambda r: True)
    lsp._project_texts[ni["path"]] = "something else"
    check(not lsp.applyProjectFix(ni["path"], ni["index"]), "a fix for text that changed is refused")
    for f in ("Fixes.qml", "Current.qml", "NoId.qml"):
        check(open(f"{D}/{f}").read().rstrip("\n") == open(f"{OUT}/fixproj.orig/{f}").read().rstrip("\n"), f"{f} on disk untouched")
    backend.discardAll()
    app.quit()
QTimer.singleShot(300, lambda: wait_done(s1))
