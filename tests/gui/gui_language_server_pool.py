"""A qmlls per project, kept running when switching between projects."""

NEEDS = ['qmlls']

import gc, os
from PySide6.QtCore import QObject, QProcess
from kreator.lsp import LanguageSupport
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
lsp = next(o for o in gc.get_objects() if isinstance(o, LanguageSupport))
page = win.findChild(QObject, "editorPage")
A, B = f"{OUT}/pool/a/Main.qml", f"{OUT}/pool/b/Main.qml"
seen = {"prime_roots": [], "comp": None}
orig = LanguageSupport._prime_types
def spy(self):
    before = self._priming
    orig(self)
    if self._priming and not before:
        seen["prime_roots"].append(self._root)
LanguageSupport._prime_types = spy
lsp.completionReady.connect(lambda rid, items: seen.__setitem__("comp", len(items)))
backend.openFolder(f"{OUT}/pool"); backend.openFile(A)
page.setProperty("sourceMode", True)
def wait(then, n=0):
    if (not lsp.property("running") or lsp.property("loadingTypes") or lsp.property("indexing")) and n < 600:
        QTimer.singleShot(50, lambda: wait(then, n + 1)); return
    then()
def s1():
    seen["a"] = lsp._client
    check(lsp._root.endswith("pool/a"), f"server for a ({lsp._root})")
    backend.openFile(B)
    QTimer.singleShot(500, lambda: wait(lambda: wait_primed(s2)))
def s2():
    check(lsp._root.endswith("pool/b") and lsp._client is not seen["a"], "another server for b")
    check(seen["a"].proc.state() == QProcess.ProcessState.Running, "a's server keeps running (parked)")
    seen["b"] = lsp._client
    n = len(seen["prime_roots"])
    seen["n"] = n
    backend.switchTo(A)
    QTimer.singleShot(400, lambda: s3())
def s3():
    check(lsp._client is seen["a"], "back to a: its server again, not a new one")
    check(not lsp.property("loadingTypes") and len(seen["prime_roots"]) == seen["n"], f"types not loaded again ({seen["prime_roots"]} n={seen["n"]} loading={lsp.property("loadingTypes")})")
    check(lsp.property("running"), "running at once")
    lsp.complete(8, 22)   # after "root."
    QTimer.singleShot(3000, s4)
def s4():
    check(bool(seen["comp"]), f"completion works after switching back ({seen['comp']} items)")
    backend.switchTo(B)
    QTimer.singleShot(400, s5)
def s5():
    check(lsp._client is seen["b"], "and b's server for b")
    procs = [seen["a"].proc, seen["b"].proc]
    lsp.settingsChanged()   # all servers stop
    seen["procs"] = procs
    QTimer.singleShot(3000, s6)
def s6():
    try:
        a_state = seen["procs"][0].state()
        dead = a_state == QProcess.ProcessState.NotRunning
    except RuntimeError:
        dead = True
    check(dead, "a settings change stops the parked server too")
    backend.discardAll()
    QTimer.singleShot(300, app.quit)
def wait_primed(then, n=0):
    if (lsp._primed_root != lsp._root or lsp.property("loadingTypes")) and n < 600:
        QTimer.singleShot(50, lambda: wait_primed(then, n + 1)); return
    then()
QTimer.singleShot(500, lambda: wait(lambda: wait_primed(s1)))
