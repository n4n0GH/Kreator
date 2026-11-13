"""Built-in editor: turning semantic highlighting on and off."""

PLAIN_EDITOR = True
NEEDS = ['qmlls']

import json
from PySide6.QtCore import QObject
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
page = win.findChild(QObject, "editorPage")
import gc
from kreator.lsp import LanguageSupport
L = next(o for o in gc.get_objects() if isinstance(o, LanguageSupport))
def color_at(line, word):
    doc = L._sem_doc.textDocument(); b = doc.findBlockByNumber(line - 1); idx = b.text().index(word)
    for r in b.layout().formats():
        if r.start <= idx < r.start + r.length:
            return r.format.foreground().color().name()
def setsem(on):
    c = json.loads(backend.editorSettingsJson()); c["lsp"]["semantic"] = on; backend.setEditorSettingsJson(json.dumps(c))
backend.openFile(f"{OUT}/qf/Fixes.qml"); page.setProperty("sourceMode", True)
seq = []
def s1():
    check(L.property("ownHighlighting"), "own highlighter on")
    win.grabWindow().save(f"{OUT}/sem_on.png")
    setsem(False); QTimer.singleShot(1500, s2)
def s2():
    check(not L.property("ownHighlighting") and color_at(10, "Label") is not None, f"off: KSyntaxHighlighting colours ({color_at(10, 'Label')})")
    check(color_at(11, "counter") in (None, "#cfcfc2"), f"no semantic colour when off ({color_at(11, 'counter')})")
    win.grabWindow().save(f"{OUT}/sem_off.png")
    setsem(True); QTimer.singleShot(4000, s3)
def s3():
    check(L.property("ownHighlighting") and color_at(11, "counter") == "#2980b9", "back on: semantic colours again")
    setsem(True)
    app.quit()
QTimer.singleShot(6000, s1)
