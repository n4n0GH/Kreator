"""The sidebar and its dividers; the source view's Symbols tab."""

KATE = True
NEEDS = ['qmlls']

from PySide6.QtCore import QObject, Qt, QPointF, QPoint
from PySide6.QtTest import QTest
def check(c, m): print(("PASS " if c else "FAIL ") + m, flush=True)
page = win.findChild(QObject, "editorPage")
def find_all(pred):
    out, stack = [], [win.contentItem()]
    while stack:
        it = stack.pop()
        if pred(it): out.append(it)
        stack.extend(it.childItems())
    return out
def cls(n): return [i for i in find_all(lambda it: it.metaObject().className().startswith(n)) if i.isVisible()]
# a folder with 60 files: a file list long enough to scroll
import os
os.makedirs(f"{OUT}/many60", exist_ok=True)
for n in range(1, 61):
    with open(f"{OUT}/many60/File{n:02}.qml", "w") as fh:
        fh.write(f"import QtQuick\n\nItem {{\n    id: c{n:02}\n    function f() {{}}\n}}\n")
backend.openFolder(f"{OUT}/many60")
backend.openFile(f"{OUT}/work/Long.qml")
def drag(x, y0, y1):
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, QPoint(x, y0))
    for k in range(1, 11):
        QTest.mouseMove(win, QPoint(x, y0 + (y1 - y0) * k // 10))
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, QPoint(x, y1))
def vbar_near(x_edge):
    bars = [b for b in find_all(lambda it: "ScrollBar" in it.metaObject().className() and it.property("orientation") == Qt.Vertical) if b.isVisible() and b.width() > 0]
    b = min(bars, key=lambda b: abs(b.mapToScene(QPointF(b.width(), 0)).x() - x_edge))
    p = b.mapToScene(QPointF(b.width() - 2, 0))
    return int(p.x()), b
def widths():
    return [round(p.width()) for p in cls("SidePanel") + cls("PropertyPanel")]
def s1():
    side = cls("SidePanel")[0]
    side.showTab(0)
    page.setProperty("sourceMode", True)
    QTimer.singleShot(400, s2)
def s2():
    side = cls("SidePanel")[0]
    check(side.property("currentTab") == 1 and len(cls("SymbolsView")) == 1, "source view brings up the Symbols tab")
    side.showTab(0)  # files, for the scrollbar test
    QTimer.singleShot(300, s3)
def s3():
    side = cls("SidePanel")[0]
    lists = [l for l in find_all(lambda it: it.metaObject().className() == "QQuickListView" and it.property("count") == 60) if l.isVisible()]
    lv = lists[0]
    r = side.mapToScene(QPointF(side.width(), 0))
    x, bar = vbar_near(r.x())      # the scrollbar's right edge, next to the divider
    print("sidebar bar right edge", x, "divider", r.x())
    y0 = int(lv.mapToScene(QPointF(0, 20)).y())
    before, cy = widths(), lv.property("contentY")
    drag(x, y0, y0 + 200)
    QTimer.singleShot(200, lambda: s4(lv, before, cy))
def s4(lv, before, cy):
    print("sidebar list contentY", cy, "->", lv.property("contentY"), "widths", before, widths())
    check(lv.property("contentY") > cy and widths() == before, "file list scrollbar next to the divider scrolls, no resize")
    page.setProperty("sourceMode", True)
    QTimer.singleShot(400, s5)
def s5():
    prop = cls("PropertyPanel")[0]
    kate = [k for k in find_all(lambda it: it.objectName() == "kateEditor") if k.isVisible()]
    if kate:
        # Kate's scrollbar is in its own native window (mouse input goes there
        # directly); the divider must stay outside that window
        px = int(prop.mapToScene(QPointF(0, 0)).x())
        g = kate[0].nativeGeometry()
        print("kate window right edge", g.x() + g.width(), "properties panel at", px)
        check(g.x() + g.width() <= px - 1, "Kate's editor window ends before the divider (so it stays grabbable)")
        s6b(); return
    flicks = [f for f in find_all(lambda it: it.metaObject().className() == "QQuickFlickable" and it.property("contentHeight") > it.height() > 200) if f.isVisible()]
    fl = max(flicks, key=lambda f: f.property("contentHeight"))
    px = int(prop.mapToScene(QPointF(0, 0)).x())
    x, bar = vbar_near(px)
    print("source bar right edge", x, "divider", px)
    y0 = int(fl.mapToScene(QPointF(0, 30)).y())
    before, cy = widths(), fl.property("contentY")
    win.grabWindow().save(f"{OUT}/split.png")
    drag(x, y0, y0 + 150)
    QTimer.singleShot(200, lambda: s6(fl, before, cy))
def s6b():
    prop = cls("PropertyPanel")[0]
    px = int(prop.mapToScene(QPointF(0, 0)).x())
    before = widths()
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, QPoint(px - 1, 400))
    for k in range(1, 11): QTest.mouseMove(win, QPoint(px - 1 - 6 * k, 400))
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, QPoint(px - 61, 400))
    QTimer.singleShot(200, lambda: (check(widths()[1] > before[1], "the divider itself still resizes"), app.quit()))
def s6(fl, before, cy):
    print("source contentY", cy, "->", fl.property("contentY"), "widths", before, widths())
    check(fl.property("contentY") > cy and widths() == before, "source view scrollbar next to the divider scrolls, no resize")
    # the divider itself still drags
    prop = cls("PropertyPanel")[0]
    px = int(prop.mapToScene(QPointF(0, 0)).x())
    before = widths()
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, QPoint(px - 1, 400))
    for k in range(1, 11): QTest.mouseMove(win, QPoint(px - 1 - 6 * k, 400))
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, QPoint(px - 61, 400))
    QTimer.singleShot(200, lambda: (print("after divider drag", before, widths()), check(widths()[1] > before[1], "the divider itself still resizes"), app.quit()))
QTimer.singleShot(800, s1)
