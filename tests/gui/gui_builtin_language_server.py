"""Built-in editor: completion, diagnostics, go to definition with qmlls."""

PLAIN_EDITOR = True
NEEDS = ['qmlls']

from PySide6.QtCore import QObject, Qt, QEvent, QMetaObject, Q_ARG
from PySide6.QtGui import QKeyEvent, QGuiApplication
from PySide6.QtTest import QTest
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
def v(x): return x.toVariant() if hasattr(x, "toVariant") else x
def typ(text):
    for ch in text:
        key = {".": Qt.Key_Period, " ": Qt.Key_Space}.get(ch, Qt.Key(ord(ch.upper())) if ch.isalnum() else Qt.Key_unknown)
        for tp in (QEvent.KeyPress, QEvent.KeyRelease):
            QGuiApplication.sendEvent(win, QKeyEvent(tp, key, Qt.NoModifier, ch))
        app.processEvents()
import kreator.lsp as L
_orig_send = L.LspClient._send
def _send(self, msg, force=False):
    if msg.get("method") in ("textDocument/completion", "textDocument/definition"):
        print("SEND", msg["method"], msg.get("params", {}).get("position"), flush=True)
    return _orig_send(self, msg, force)
L.LspClient._send = _send
_orig_disp = L.LspClient._dispatch
def _disp(self, msg):
    if "id" in msg and "method" not in msg:
        r = msg.get("result")
        n = len(r.get("items", [])) if isinstance(r, dict) else (len(r) if isinstance(r, list) else r)
        print("RECV id", msg["id"], "result size", n, "error", msg.get("error"), flush=True)
    return _orig_disp(self, msg)
L.LspClient._dispatch = _disp
backend.openFile(f"{OUT}/work/SettingsPage.qml")
page = win.findChild(QObject, "editorPage")
lsp = None
def find(pred):
    stack = [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): return it
        stack.extend(it.childItems())
def s1():
    page.setProperty("sourceMode", True); QTimer.singleShot(5000, s2)   # server start + warm-up
def s2():
    global ed, pane, popup, lspobj
    import gc
    from kreator.lsp import LanguageSupport
    lspobj = next(o for o in gc.get_objects() if isinstance(o, LanguageSupport))
    ed = find(lambda it: it.metaObject().indexOfProperty("persistentSelection") >= 0 and it.property("persistentSelection"))
    pane = find(lambda it: it.metaObject().indexOfProperty("foldRegions") >= 0)
    popup = ed.findChild(QObject, "") 
    print("lsp running:", lspobj.property("running"), "status:", lspobj.property("status"))
    check(lspobj.property("running"), "qmlls started for the document")
    diags = v(lspobj.property("diagnostics"))
    print("diagnostics:", [(d["line"] + 1, d["severity"], d["message"][:50]) for d in diags][:8])
    check(not any("i18n" in d["message"] for d in diags) and lspobj.property("warningCount") >= 0, "no i18n false positives")
    win.grabWindow().save(f"{OUT}/lsp0.png")
    # completion after typing 3 chars of a property inside the TextField block
    t = ed.property("text")
    p = t.index('placeholderText: "Your name"') + len('placeholderText: "Your name"')
    ed.forceActiveFocus(); ed.setProperty("cursorPosition", p)
    QTest.keyClick(win, Qt.Key_Return)
    typ("plac")
    QTimer.singleShot(1500, s3)
def s3():
    comp = find(lambda it: it.metaObject().indexOfProperty("shown") >= 0) or None
    # the popup's content lives in the overlay; read the Popup object via the editor's children
    popups = [o for o in ed.children() if o.metaObject().indexOfProperty("shown") >= 0]
    global cp
    cp = popups[0] if popups else None
    shown = v(cp.property("shown")) if cp else []
    print("completion shown:", [i["label"] for i in shown][:6], "opened:", cp.property("opened") if cp else None)
    check(cp is not None and cp.property("opened") and shown and shown[0]["label"].startswith("placeholderText"), "auto-completion popup after 'plac'")
    win.grabWindow().save(f"{OUT}/lsp1.png")
    QTest.keyClick(win, Qt.Key_Down); QTest.keyClick(win, Qt.Key_Return)
    t = ed.property("text")
    check("placeholderTextColor" in t and not cp.property("opened"), "Down + Enter accepts the second item")
    # enum after a dot
    typ(": Text.")
    QTimer.singleShot(1200, s4)
def s4():
    shown = v(cp.property("shown"))
    print("after 'Text.':", [i["label"] for i in shown][:6])
    check(not any(i["label"].startswith("__") for i in shown), "no JS internals offered")
    check(cp.property("opened") and len(shown) > 3, "completion after '.'")
    QTest.keyClick(win, Qt.Key_Escape)
    check(not cp.property("opened"), "Esc closes the list")
    # Ctrl+Space on an empty word
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)   # undo the typing
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)
    QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)
    # introduce an error and wait for diagnostics
    t = ed.property("text")
    p = t.index("spacing: 10")
    ed.setProperty("cursorPosition", p + len("spacing: 10"))
    typ(" +")
    QTimer.singleShot(2500, s5)
def s5():
    diags = v(lspobj.property("diagnostics"))
    print("diagnostics after error:", [(d["line"] + 1, d["severity"], d["message"][:60]) for d in diags][:5])
    check(lspobj.property("errorCount") >= 1, "syntax error reported")
    win.grabWindow().save(f"{OUT}/lsp2.png")
    t = ed.property("text"); i = t.index("spacing: 10 +")
    ed.select(i + len("spacing: 10"), i + len("spacing: 10 +")); QTest.keyClick(win, Qt.Key_Delete)
    check("spacing: 10 +" not in ed.property("text"), "error removed")
    QTimer.singleShot(1500, s5b)
def s5b():
    check(lspobj.property("errorCount") == 0, "diagnostics cleared after the fix")
    # go to definition of nameField (used in the Button's onClicked)
    t = ed.property("text")
    p = t.index("nameField.text") + 3
    ed.setProperty("cursorPosition", p)
    QTest.keyClick(win, Qt.Key_F12)
    QTimer.singleShot(1500, s6)
def s6():
    t = ed.property("text"); p = ed.property("cursorPosition")
    line = t[:p].count("\n") + 1
    print("after F12 cursor line", line, repr(t[p:p+20]))
    check("nameField" in t[p-10:p+20] and line < 40, "F12 jumps to the id definition")
    app.quit()
QTimer.singleShot(1000, s1)
