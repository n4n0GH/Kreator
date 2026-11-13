"""Kate's editor settings are shared with Kate's katerc."""

KATE = True

import sys as _s, traceback as _t, os
_s.excepthook = lambda *a: (_t.print_exception(*a), app.exit(3))
import warnings; warnings.simplefilter("ignore")
from PySide6.QtCore import QObject, Qt, QMetaObject
from PySide6.QtWidgets import QApplication, QDialog, QDoubleSpinBox, QDialogButtonBox, QAbstractButton
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
page = win.findChild(QObject, "editorPage")
cfg = os.environ["XDG_CONFIG_HOME"]
def find_all(pred):
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems())
    return out
backend.openFile(f"{OUT}/proj/Main.qml")
page.setProperty("sourceMode", True)
def in_dialog():
    dlgs = [w for w in QApplication.topLevelWidgets() if isinstance(w, QDialog) and w.isVisible()]
    print("dialog:", [d.windowTitle() for d in dlgs], flush=True)
    d = dlgs[0]
    spins = [s for s in d.findChildren(QDoubleSpinBox)]
    print("double spinboxes:", [(s.objectName(), s.value()) for s in spins][:5], flush=True)
    lh = [s for s in spins if abs(s.value() - 1.7) < 0.01]
    if lh:
        lh[0].setValue(1.4)
    box = d.findChildren(QDialogButtonBox)[0]
    ok = box.button(QDialogButtonBox.Ok)
    ok.click()
def s1():
    ed = find_all(lambda it: it.objectName() == "kateEditor")[0]
    QTimer.singleShot(1500, in_dialog)
    QMetaObject.invokeMethod(ed, "configureEditor")   # modal: returns after OK
    QTimer.singleShot(500, s2)
def s2():
    k = open(f"{cfg}/katerc").read()
    check("Line Height Multiplier=1.4" in k, "a change in Kreator's editor settings is written to Kate's katerc")
    check("Something Kate-only=yes" in k, "Kate's other settings are untouched")
    app.quit()
QTimer.singleShot(1500, s1)
