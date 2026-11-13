"""Built-in editor: highlighting of QML and .ui XML."""

PLAIN_EDITOR = True

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
files = [f"{OUT}/work/dialog.ui", f"{OUT}/qf/Fixes.qml"] * 3
def step(i=0):
    if i >= len(files):
        print("switched", len(files), "times without crashing"); app.quit(); return
    backend.openFile(files[i]); page.setProperty("sourceMode", True)
    QTimer.singleShot(1200, lambda: verify(i))
def verify(i):
    f = files[i]
    if f.endswith(".ui"):
        check(type(L._hl).__name__ == "XmlHighlighter" and color_at(4, "widget") == "#cfcfc2" and color_at(4, "class") == "#27ae60" and color_at(4, '"QDialog"') == "#f44f4f",
              f"XML: element/attribute/value coloured ({color_at(4, 'widget')}, {color_at(4, 'class')}, {color_at(4, chr(34) + 'QDialog')})")
    else:
        check(type(L._hl).__name__ == "QmlHighlighter" and color_at(10, "Label") == "#2980b9", "QML highlighted")
    step(i + 1)
QTimer.singleShot(1000, step)
