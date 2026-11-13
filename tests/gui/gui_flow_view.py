"""The signal flow view of a QML file and a form: nodes, ports, red ports, arrows, clicks."""


import sys as _s, traceback as _t
_s.excepthook = lambda *a: (_t.print_exception(*a), app.exit(3))
import warnings; warnings.simplefilter("ignore")
from PySide6.QtCore import QObject, QPointF, Qt
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
page = win.findChild(QObject, "editorPage")
P = f"{OUT}/flowproj"
def items(pred):
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems())
    return out
def named(prefix):
    return [i for i in items(lambda it: it.objectName().startswith(prefix)) if i.isVisible()]
def fp(): return items(lambda it: it.objectName() == "flowPane")[0]
backend.openFolder(P); backend.openFile(f"{P}/Flow.qml")
page.setProperty("flowMode", True)
import os
ZOOM = float(os.environ.get('ZOOM', '0.5'))
def port(node, name): return [i for i in named("flowPort_") if i.objectName() == f"flowPort_{node}_{name}"]
def dot(prefix): return [i for i in named("flowEdge_") if i.objectName().startswith(prefix)]
def s1():
    pane = fp()
    check(pane.property("visible") and pane.property("active"), "flow view shown")
    nodes = sorted(n.objectName()[9:] for n in named("flowNode_"))
    check(nodes == sorted(["root", "“Save”", "field", "status", "backendDialog", "timer", "Backend", "advanced"]), f"nodes {nodes}")
    want = len(backend.signalFlow(["signal", "binding"], 0, False)["edges"])
    check(len(named("flowEdge_")) == want, f"an arrow (with its dot) per port pair: {len(named('flowEdge_'))} of {want}")
    check(bool(port("“Save”", "clicked")) and bool(port("root", "save()")) and bool(port("backendDialog", "open()")),
          "ports: Save's clicked, root's save(), the dialog's open()")
    check(bool(port("advanced", "checked")) and bool(port("field", "enabled")), "binding ports: checked -> enabled")
    lonely = port("root", "lonely()")
    check(bool(lonely) and lonely[0].property("loose") and not port("root", "save()")[0].property("loose"),
          "a function nothing calls is shown, in red; a called one isn't red")
    lo = port("root", "leftover")
    check(bool(lo) and lo[0].property("loose"), "a declared property nothing uses is shown, in red")
    win.grabWindow().save(f"{OUT}/flow1.png")
    rects = [(n.x(), n.y(), n.width(), n.height()) for n in named("flowNode_")]
    ov = any(a != b and a[0] < b[0]+b[2] and b[0] < a[0]+a[2] and a[1] < b[1]+b[3] and b[1] < a[1]+a[3] for a in rects for b in rects)
    check(not ov, "objects don't overlap")
    # the arrows start and end at their ports' connectors
    pane.setProperty("zoom", 1.0)
    QTimer.singleShot(200, s1b)
def s1b():
    pane = fp()
    e = [x for x in backend.signalFlow(["signal", "binding"], 0, False)["edges"] if x["fromPort"] == "clicked"][0]
    from PySide6.QtCore import QMetaObject, Q_RETURN_ARG, Q_ARG
    gm = QMetaObject.invokeMethod(pane, "geometry", Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", e))
    src = port("“Save”", "clicked")[0]; dst = port("root", "save()")[0]
    canvas = named("flowNode_root")[0].parentItem()
    sp = src.mapToItem(canvas, QPointF(src.width(), src.height() / 2)); dp = dst.mapToItem(canvas, QPointF(0, dst.height() / 2))
    d = gm.property("d").toString() if hasattr(gm, "property") else gm["d"]
    nums = [float(x) for x in d.replace("M", " ").replace("C", " ").split()]
    check(abs(nums[0] - sp.x()) < 1.5 and abs(nums[1] - sp.y()) < 1.5, f"arrow leaves clicked's connector ({nums[:2]} vs {sp})")
    check(abs(nums[-2] - dp.x()) < 1.5 and abs(nums[-1] - dp.y()) < 1.5, f"and enters save()'s ({nums[-2:]} vs {dp})")
    b = named("flowLayout")[0]; b.toggle(); b.toggled.emit()
    QTimer.singleShot(300, s2)
def s2():
    want = len(backend.signalFlow(["signal", "binding", "layout"], 0, False)["edges"])
    check(len(named("flowEdge_")) == want, f"layout bindings shown: {len(named('flowEdge_'))} of {want}")
    b = named("flowLayout")[0]; b.toggle(); b.toggled.emit()
    fp().setProperty("zoom", 0.5)
    QTimer.singleShot(300, s2b)
def s2b():
    # select a node by clicking it (its type line)
    n = named("flowNode_status")[0]
    from PySide6.QtTest import QTest
    p = n.mapToScene(QPointF(n.width()/2, fp().property("titleHeight") + fp().property("typeHeight") / 2)).toPoint()
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, p)
    QTimer.singleShot(300, s3)
def s3():
    check(backend.property("selectedId") == "status", f"click selects the object ({backend.property('selectedId')})")
    win.grabWindow().save(f"{OUT}/flow2.png")
    s = named("flowSelectedOnly")[0]; s.toggle(); s.toggled.emit()
    QTimer.singleShot(300, s4)
def s4():
    nodes = sorted(n.objectName()[9:] for n in named("flowNode_"))
    check(nodes == sorted(["status", "field", "backendDialog", "Backend"]), f"selected only: {nodes}")
    s = named("flowSelectedOnly")[0]; s.toggle(); s.toggled.emit()
    fp().setProperty("zoom", ZOOM)
    QTimer.singleShot(300, s4b)
def s4b():
    # click an arrow's dot -> the code it stands for
    d = [i for i in named("flowEdge_") if ".clicked_" in i.objectName()][0]
    at = d.mapToScene(QPointF(d.width()/2, d.height()/2))
    from PySide6.QtTest import QTest
    QTest.mouseMove(win, at.toPoint()); QTest.qWait(Kirigami_delay := 900)   # its tooltip shows
    tip = [o for o in items(lambda it: it.objectName() == "flowTip")]
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, at.toPoint())
    QTimer.singleShot(2500, s5)
def s5():
    check(page.property("sourceMode") and not page.property("flowMode"), "clicking an arrow's dot opens the source view")
    check(page.property("sourceLine") == 15, f"at the handler's line 16 ({page.property('sourceLine') + 1})")
    page.setProperty("flowMode", True)
    QTimer.singleShot(800, s5b)
def s5b():
    # click a port -> where it is written (save() at line 9)
    q = port("root", "save()")[0]
    from PySide6.QtTest import QTest
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, q.mapToScene(QPointF(q.width()/2, q.height()/2)).toPoint())
    QTimer.singleShot(2500, s5c)
def s5c():
    check(page.property("sourceMode") and page.property("sourceLine") == 8, f"clicking a port shows where it is written (line {page.property('sourceLine') + 1})")
    page.setProperty("flowMode", True)
    backend.openFile(f"{P}/dialog.ui")
    QTimer.singleShot(800, s6)
def s6():
    nodes = sorted(n.objectName()[9:] for n in named("flowNode_"))
    check(nodes == ["Dialog", "buttonBox", "checkBox", "lineEdit"], f".ui nodes {nodes}")
    check(bool(port("checkBox", "toggled(bool)")) and bool(port("lineEdit", "setEnabled(bool)")), ".ui ports: signal and slot")
    check(not named("flowBindings"), "no binding filter for forms")
    win.grabWindow().save(f"{OUT}/flow3.png")
    backend.discardAll()
    QTimer.singleShot(300, app.quit)
QTimer.singleShot(1500, s1)
