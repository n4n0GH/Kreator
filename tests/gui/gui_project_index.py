"""Indexing a folder's files in the background, with its progress."""

NEEDS = ['qmlls']

import time, os, gc
from PySide6.QtCore import QObject, Qt
from PySide6.QtTest import QTest
from kreator.lsp import LanguageSupport
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
D = f"{OUT}/many"
lsp = next(o for o in gc.get_objects() if isinstance(o, LanguageSupport))
page = win.findChild(QObject, "editorPage")
def find_all(pred):
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems())
    return out
def cls(name): return [it for it in find_all(lambda it: it.metaObject().className().startswith(name))]
seen = {"max_done": 0, "status_seen": False, "t0": time.time()}
def watch():
    if lsp.property("indexing"):
        st = [s for s in cls("IndexStatus") if s.isVisible()]
        if st and not seen["status_seen"]:
            seen["status_seen"] = True
            win.grabWindow().save(f"{OUT}/idx_progress.png")
        seen["max_done"] = max(seen["max_done"], lsp.property("indexDone"))
backend.openFolder(D)
timer = QTimer(); timer.timeout.connect(watch); timer.start(20)
def wait_done(then, n=0):
    if (lsp.property("indexing") or lsp.property("loadingTypes")) and n < 600:
        QTimer.singleShot(50, lambda: wait_done(then, n + 1)); return
    then()
def s1():
    print(f"indexed in {time.time()-seen['t0']:.1f}s total={lsp.property('indexTotal')} done={lsp.property('indexDone')}")
    check(seen["status_seen"], "status bar shown at the bottom of the sidebar while indexing")
    check(lsp.property("indexTotal") == 14 and lsp.property("indexDone") == 14 and len(lsp._index_cache) == 14, "all 14 project files indexed at start, no source view needed")
    check(not page.property("sourceMode"), "(still in the design view)")
    QTimer.singleShot(3500, s2)
def s2():
    check(not any(s.isVisible() for s in cls("IndexStatus")), "status bar hides after 'done'")
    backend.switchTo(f"{D}/Component07.qml")
    page.setProperty("sourceMode", True)
    QTimer.singleShot(60, s3)
def s3():
    syms = lsp.property("symbols")
    check(len(syms) > 0, f"symbols shown right away on switching to the source view ({len(syms)})")
    win.grabWindow().save(f"{OUT}/idx_symbols.png")
    tabs = [t for t in cls("SideTab") if t.isVisible()]
    check(len(tabs) == 4, f"one sidebar with 4 tabs ({len(tabs)})")
    check(len(cls("ProjectPanel")) == 1 and not any(t.property("text") == "Hide Folder" for t in find_all(lambda it: True)), "folder view lives in the sidebar")
    # click the Files tab
    t0 = sorted(tabs, key=lambda t: t.mapToScene(t.boundingRect().topLeft()).x())[0]
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, t0.mapToScene(t0.boundingRect().center()).toPoint())
    QTimer.singleShot(200, s4)
def s4():
    check(cls("ProjectPanel")[0].isVisible(), "Files tab shows the folder")
    win.grabWindow().save(f"{OUT}/idx_files.png")
    # change a file on disk: only it is indexed again
    with open(f"{D}/Component02.qml", "a") as fh: fh.write("\n// touched\n")
    seen["status_seen"] = False
    QTimer.singleShot(1500, lambda: wait_done(s5))
def s5():
    check(lsp.property("indexTotal") == 1 and "// touched" in lsp._index_cache[f"{D}/Component02.qml"][0], f"a changed file is re-indexed alone (total={lsp.property('indexTotal')})")
    app.quit()
QTimer.singleShot(200, lambda: wait_done(s1))
