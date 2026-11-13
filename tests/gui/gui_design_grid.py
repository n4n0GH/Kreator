"""The design view's grid: showing it, moving objects by dragging and with the
arrow keys, snapped to it (positions written in Kirigami units), and placing
components dragged from the Add tab; then the same for a form without layouts."""

import os
import re

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest

os.makedirs(f"{OUT}/grid", exist_ok=True)
QML = f"{OUT}/grid/Grid.qml"
UI = f"{OUT}/grid/free.ui"
with open(QML, "w") as fh:
    fh.write("""import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

Item {
    id: root
    width: 400
    height: 300

    Rectangle {
        id: box
        x: 10
        y: 10
        width: 60
        height: 40
        color: "tomato"
    }
    Item {
        id: area
        x: 96
        y: 48
        width: 200
        height: 120
    }
    Column {
        id: col
        x: 160
        y: 200
        width: 84   // (not its button's text width, which varies by a pixel)
        QQC2.Button {
            id: inColumn
            text: "In a column"
        }
    }
    Rectangle {
        id: anchored
        anchors.right: parent.right
        width: 20
        height: 20
    }
    Rectangle {
        id: computed
        x: box.width + 300
        y: 250
        width: 20
        height: 20
    }
}
""")
with open(UI, "w") as fh:
    fh.write("""<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Free</class>
 <widget class="QWidget" name="Free">
  <property name="geometry">
   <rect><x>0</x><y>0</y><width>400</width><height>300</height></rect>
  </property>
  <widget class="QPushButton" name="okButton">
   <property name="geometry">
    <rect><x>10</x><y>10</y><width>90</width><height>30</height></rect>
   </property>
   <property name="text"><string>OK</string></property>
  </widget>
  <widget class="QGroupBox" name="laidOut">
   <property name="geometry">
    <rect><x>200</x><y>150</y><width>180</width><height>120</height></rect>
   </property>
   <layout class="QVBoxLayout" name="verticalLayout">
    <item>
     <widget class="QCheckBox" name="option"/>
    </item>
   </layout>
  </widget>
 </widget>
</ui>
""")

win.resize(1400, 900)
backend.openFile(QML)
pane = None


def uid(ident):
    return next(r["uid"] for r in backend.outline.rows() if r["objectId"] == ident)


def binding(ident, name):
    m = re.search(r"id: " + ident + r"\n((?:\s+[^\n]*\n)*?)\s*}", backend.sourceText)
    b = re.search(r"\n\s*" + name + r": ([^\n]+)", "\n" + m.group(1)) if m else None
    return b.group(1).strip() if b else None


def one(name):
    found = by_name(name)
    return found[0] if found else None


def scene_of(frame_x, frame_y):
    """A point of the design view (preview coordinates) in the window."""
    canvas = one("designCanvas")
    return canvas.mapToScene(QPointF(frame_x, frame_y)).toPoint()


def drag(a, b, steps=10, shot=""):
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, steps + 1):
        QTest.mouseMove(win, a + (b - a) * i / steps)
        QTest.qWait(20)
    if shot:
        win.grabWindow().save(f"{OUT}/{shot}.png")
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, b)
    QTest.qWait(150)


def grid_lines():
    g = one("designGrid")
    return 0 if g is None else sum(1 for c in g.childItems() if c.width() == 1 or c.height() == 1)


def s1():
    global pane
    pane = find_all(lambda i: i.property("gridStep") is not None and i.property("snapToGrid") is not None)[0]
    check(pane.property("gridStep") == 8 and pane.property("snapToGrid") and not pane.property("showGrid"),
          "the grid: Large Spacing (8 px), snapping on, hidden at first")
    check(one("designGrid") is None, "no grid drawn while it is hidden")
    button = one("showGridButton")
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint())
    QTest.qWait(100)
    check(pane.property("showGrid") and grid_lines() > 40, f"Show Grid draws it ({grid_lines()} lines)")

    # what can be moved
    check(backend.placementProblem(uid("box")) == "", "a rectangle in an Item can be moved")
    check("layout" in backend.placementProblem(uid("inColumn")), "a button in a Column can't: " + backend.placementProblem(uid("inColumn")))
    check("anchored" in backend.placementProblem(uid("anchored")), "an anchored object can't")
    check("expression" in backend.placementProblem(uid("computed")), "nor one whose x is an expression")
    check("root" in backend.placementProblem(backend.adapter.doc.root.uid), "nor the root object")

    # drag the box: its top-left corner lands on the grid, written in Kirigami units
    backend.select(uid("box"))
    drag(scene_of(40, 30), scene_of(40 + 37, 30 + 25), shot="moving")
    check(binding("box", "x") == "Kirigami.Units.largeSpacing * 6" and binding("box", "y") == "Kirigami.Units.largeSpacing * 4",
          f"dragged box snapped to the grid: x {binding('box', 'x')}, y {binding('box', 'y')}")
    check(backend.selectedId == "box" and backend.canUndo, "still selected; undoable")
    QTimer.singleShot(300, s2)


def s2():
    # the preview follows: the box is now at (48, 32)
    item = backend.previewItemFor(uid("box"))[0]
    check((item.x(), item.y()) == (48, 32), f"the preview shows it there ({item.x()}, {item.y()})")
    # arrow keys: to the next grid line; Shift: one pixel
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, scene_of(60, 45))
    QTest.keyClick(win, Qt.Key_Right)
    QTest.qWait(100)
    check(binding("box", "x") == "Kirigami.Units.largeSpacing * 7", "Right: next grid line: " + str(binding("box", "x")))
    QTest.keyClick(win, Qt.Key_Up, Qt.ShiftModifier)
    QTest.qWait(100)
    check(binding("box", "y") == "31", "Shift+Up: one pixel, in pixels: " + str(binding("box", "y")))
    QTest.keyClick(win, Qt.Key_Down)
    QTest.qWait(100)
    check(binding("box", "y") == "Kirigami.Units.largeSpacing * 4", "Down from off the grid: the next line: " + str(binding("box", "y")))

    # Escape while dragging: nothing changes
    before = backend.sourceText
    a = scene_of(70, 45)
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, 6):
        QTest.mouseMove(win, a + QPoint(10 * i, 10 * i))
        QTest.qWait(20)
    ghost = one("moveGhost")
    check(ghost is not None, "a frame shows where it goes while dragging")
    QTest.keyClick(win, Qt.Key_Escape)
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, a + QPoint(50, 50))
    QTest.qWait(150)
    check(backend.sourceText == before, "Escape cancels the move")

    # an object in a Column: dragging says why it can't move, and changes nothing
    backend.select(uid("inColumn"))
    QTest.qWait(200)
    it = backend.previewItemFor(uid("inColumn"))[0]
    a = it.mapToScene(QPointF(5, 5)).toPoint()
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, 6):
        QTest.mouseMove(win, a + QPoint(12 * i, 0))
        QTest.qWait(20)
    problem = one("moveProblem")
    check(problem is not None, "dragging an object in a layout explains why it can't move")
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, a + QPoint(60, 0))
    QTest.qWait(150)
    check(backend.sourceText == before, "and changes nothing")

    # snapping off: positions in pixels
    backend.select(uid("box"))
    backend.placeAt(one("previewHost"), uid("box"), 13, 27, 0, "")
    check(binding("box", "x") == "13" and binding("box", "y") == "27", "placed freely: pixels")
    QTimer.singleShot(300, s2b)


def click(item):
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint())
    QTest.qWait(250)


def menu_item(text, timeout=5):
    """A visible menu item (waiting for the menu to open)."""
    import time
    t0 = time.time()
    while True:
        found = [i for i in find_all(lambda i: i.property("text") == text and i.property("checkable") is not None) if i.isVisible()]
        if found or time.time() - t0 > timeout:
            return found[0] if found else None
        QTest.qWait(50)


def s2b():
    # the grid's size, from the toolbar's menu
    click(one("gridSizeButton"))
    item = menu_item("Grid Unit (18 px)")
    check(item is not None, "the grid size menu offers the Grid Unit")
    if item is None:
        return finish()
    click(item)
    check(pane.property("gridStep") == 18 and one("gridSizeButton").property("text") == "18 px", "Grid Unit chosen: 18 px")
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, scene_of(20, 35))
    QTest.keyClick(win, Qt.Key_Right)
    QTest.qWait(100)
    check(backend.selectedId == "box" and binding("box", "x") == "Kirigami.Units.gridUnit",
          "Right: to the next grid unit: " + str(binding("box", "x")))
    click(one("gridSizeButton"))
    click(menu_item("Large Spacing (8 px)"))
    check(pane.property("gridStep") == 8, "back to Large Spacing")
    QTimer.singleShot(300, r1)


def handle(name, timeout=5):
    """A visible resize handle (waiting for it to appear; timeout 0: now)."""
    import time
    t0 = time.time()
    while True:
        found = one("resizeHandle_" + name)
        if found is not None or time.time() - t0 >= timeout:
            return found
        QTest.qWait(50)


def center(item):
    return item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()


def r1():
    # resizing `area` (96, 48, 200 × 120) by its handles
    backend.select(uid("area"))
    QTest.qWait(400)
    check(all(handle(n) is not None for n in ("tl", "t", "tr", "r", "br", "b", "bl", "l")), "eight resize handles")
    tag = one("selectionTag")
    tag_bottom = tag.mapToScene(QPointF(0, tag.height())).y()
    top = one("designCanvas").mapToScene(QPointF(0, 48)).y()
    check(tag is not None and tag_bottom <= top + 0.5 and tag.property("visible"),
          f"the id tag sits above the border, outside the object ({tag_bottom} <= {top})")
    a = center(handle("br"))
    drag(a, a + QPoint(21, -9), shot="resizing")
    check(binding("area", "width") == "Kirigami.Units.largeSpacing * 28" and binding("area", "height") == "Kirigami.Units.largeSpacing * 14",
          f"bottom-right handle: the corner on the grid: {binding('area', 'width')}, {binding('area', 'height')}")
    check(binding("area", "x") == "96" and binding("area", "y") == "48", "position untouched")
    QTimer.singleShot(300, r2)


def r2():
    a = center(handle("tl"))
    drag(a, a + QPoint(10, 10))
    check((binding("area", "x"), binding("area", "y"), binding("area", "width"), binding("area", "height")) ==
          ("Kirigami.Units.largeSpacing * 13", "Kirigami.Units.largeSpacing * 7",
           "Kirigami.Units.largeSpacing * 27", "Kirigami.Units.largeSpacing * 13"),
          f"top-left handle: moves the corner, the opposite one stays: {binding('area', 'x')}, {binding('area', 'width')}")
    item = backend.previewItemFor(uid("area"))[0]
    check((item.x(), item.y(), item.width(), item.height()) == (104, 56, 216, 104), "the preview shows the new rectangle")
    # Ctrl+arrow keys: the right / bottom side to the next grid line
    QTest.keyClick(win, Qt.Key_Right, Qt.ControlModifier)
    QTest.qWait(100)
    check(binding("area", "width") == "Kirigami.Units.largeSpacing * 28", "Ctrl+Right: one grid step wider")
    QTest.keyClick(win, Qt.Key_Up, Qt.ControlModifier | Qt.ShiftModifier)
    QTest.qWait(100)
    check(binding("area", "height") == "103", "Ctrl+Shift+Up: a pixel shorter")
    # can't be made smaller than a grid step
    a = center(handle("r"))
    drag(a, a - QPoint(400, 0))
    check(binding("area", "width") == "Kirigami.Units.largeSpacing", "at least one grid step wide: " + str(binding("area", "width")))
    for _ in range(5):
        backend.undo()
    check((binding("area", "x"), binding("area", "width"), binding("area", "height")) == ("96", "200", "120"),
          "five undo steps restore the area")

    # in a Column: resizable, not movable; only the right / bottom handles
    backend.select(uid("inColumn"))
    wait_until(lambda: handle("br", 0) is not None, r3, timeout=5, what="handles of the button in the Column")


def r3():
    check(handle("br") is not None and handle("tl", 0) is None and handle("l", 0) is None,
          f"in a Column: only the right and bottom handles ({[n for n in ('tl','t','tr','r','br','b','bl','l') if handle(n, 0)]})")
    check(backend.resizeProblem(uid("anchored")) == "it is anchored", "an anchored object can't be resized")
    QTimer.singleShot(300, g1)


def guides():
    return [(round(g.x()), round(g.y()), round(g.width()), round(g.height()))
            for g in find_all(lambda i: i.objectName() == "alignGuide") if g.isVisible()]


def g1():
    # alignment guides: moving the box (18, 27, 60 × 40) so that its centre
    # comes near the area's (96 + 100 = 196): it aligns there, not on the grid
    backend.select(uid("box"))
    QTest.qWait(300)
    rects = backend.guideRects(one("previewHost"), uid("box"))
    check([96.0, 48.0, 200.0, 120.0] in [list(r) for r in rects] and [0.0, 0.0, 400.0, 300.0] in [list(r) for r in rects],
          f"it aligns with its parent and its siblings ({len(rects)} rectangles)")
    a = scene_of(48, 47)
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, 11):
        QTest.mouseMove(win, a + QPoint(147, 0) * i / 10)
        QTest.qWait(20)
    shown = guides()
    zoom = pane.property("zoom")
    centre = round(one("designCanvas").mapToItem(one("selectionOverlay").parentItem(), QPointF(196, 0)).x())
    check(any(w == 1 and x == centre for x, _y, w, _h in shown), f"a vertical guide at the area's centre ({shown}, {centre})")
    win.grabWindow().save(f"{OUT}/guides.png")
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, a + QPoint(147, 0))
    QTest.qWait(200)
    check(binding("box", "x") == "166", "the box's centre on the area's: x " + str(binding("box", "x")))
    check(guides() == [], "the guides go away after the move")
    # far from anything: the grid as before
    a = scene_of(180, 47)
    drag(a, a + QPoint(88, 0))
    check(binding("box", "x") == "Kirigami.Units.largeSpacing * 32", "away from others: on the grid: " + str(binding("box", "x")))
    QTimer.singleShot(300, n1)


def key(k, mods=Qt.NoModifier):
    QTest.keyClick(win, k, mods)
    QTest.qWait(150)


def n1():
    # arrow keys and guides: the box is at x 256 (60 wide); the Column's
    # right side is at 244, the area's at 296
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, scene_of(280, 45))
    key(Qt.Key_Left)
    check(binding("box", "x") == "Kirigami.Units.largeSpacing * 31", "without the option: the next grid line (248)")
    check(guides() == [], "and no guides")
    click(one("gridSizeButton"))
    item = menu_item("Arrow Keys Stop at Guides")
    check(item is not None and not item.property("checked"), "the option is in the grid menu, off by default")
    click(item)
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, scene_of(280, 45))
    key(Qt.Key_Left)
    check(binding("box", "x") == "244",
          f"with it: stops at the Column's right side (244) before the grid line (240): {binding('box', 'x')}")
    check(len(guides()) > 0, "a guide shows what it lined up with")
    key(Qt.Key_Left)
    check(binding("box", "x") == "Kirigami.Units.largeSpacing * 30", "then the grid line, the nearer stop: " + str(binding("box", "x")))
    key(Qt.Key_Left, Qt.ShiftModifier)
    check(binding("box", "x") == "239", "Shift: still one pixel")
    QTest.qWait(1200)
    check(guides() == [], "the guide goes away after a moment")
    QTimer.singleShot(300, d1)


def distances():
    return sorted(i.property("text") for i in find_all(lambda i: i.objectName() == "distance") if i.isVisible())


def d1():
    # distances: the box (239, 28, 60 × 40) dragged to (32, 80): 4 px left of
    # the area (96), 32 from the root's left side, 80 from its top
    box = backend.previewItemFor(uid("box"))[0]
    p = box.mapToItem(one("previewHost"), QPointF(30, 10))   # (above the area, which overlaps it)
    a = scene_of(p.x(), p.y())
    b = a + QPoint(28 - 239, 80 - 28)
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, 11):
        QTest.mouseMove(win, a + (b - a) * i / 10)
        QTest.qWait(20)
    shown = distances()
    win.grabWindow().save(f"{OUT}/distances.png")
    check(shown == sorted(["4 · smallSpacing", "32", "80"]), f"distances while moving: {shown}")
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, b)
    QTest.qWait(200)
    check((binding("box", "x"), binding("box", "y")) == ("Kirigami.Units.largeSpacing * 4", "Kirigami.Units.largeSpacing * 10"),
          f"placed at (32, 80): {binding('box', 'x')}, {binding('box', 'y')}")
    check(distances() == [], "no distances after the move")
    key(Qt.Key_Right, Qt.ShiftModifier)
    check("3" in distances(), f"after a nudge, for a moment: {distances()}")
    QTest.qWait(1200)
    check(distances() == [], "then gone")
    QTimer.singleShot(300, s3)


def s3():
    # drag a Button from the Add tab into `area` (at 96, 48)
    side = find_all(lambda i: i.property("shownTab") is not None and i.property("lintCount") is not None)[0]
    side.setProperty("currentTab", 2)
    backend.setPaletteFilter("button")   # (so that it is in view)
    QTest.qWait(300)
    delegates = [i for i in find_all(lambda i: i.property("text") == "Button" and i.property("iconName") is not None) if i.isVisible()]
    check(len(delegates) == 1, "the Add tab lists Button")
    if not delegates:
        return finish()
    d = delegates[0]
    target = backend.dropTarget(one("previewHost"), 130, 90)
    check(target.get("label") == "area" and target.get("free"), f"dropping on the area adds to it, placed: {target}")
    col = backend.dropTarget(one("previewHost"), 170, 210)
    check(col.get("label") == "col" and not col.get("free"), f"dropping on the Column: its layout places it: {col}")
    drag(d.mapToScene(QPointF(d.width() / 3, d.height() / 2)).toPoint(), scene_of(96 + 8 + 2, 48 + 16 - 3), steps=20, shot="dropping")
    QTimer.singleShot(400, s4)


def s4():
    check(backend.selectedType.endswith("Button") and backend.selectedId == "button",
          f"the dropped Button is added and selected ({backend.selectedType} {backend.selectedId})")
    check(re.search(r"id: area\n(?:.*\n)*?\s+QQC2\.Button \{\n\s+id: button", backend.sourceText) is not None,
          "inside the area")
    check(binding("button", "x") == "Kirigami.Units.largeSpacing" and binding("button", "y") == "Kirigami.Units.largeSpacing * 2",
          f"at the grid point it was dropped on, relative to the area: {binding('button', 'x')}, {binding('button', 'y')}")
    item = backend.previewItemFor(backend.selectedUid)[0]
    p = item.mapToItem(one("previewHost"), QPointF(0, 0))
    check((p.x(), p.y()) == (104, 64), f"and shown there ({p.x()}, {p.y()})")
    backend.undo()
    check("id: button" not in backend.sourceText, "one undo step removes it")
    # a component that goes into a Column isn't positioned
    idx = next(i for i, e in enumerate(backend.adapter.palette()) if e["name"] == "Label")
    QTest.qWait(400)   # (the preview of the undone document, laid out)
    backend.insertComponentAt(one("previewHost"), idx, 170, 210, 8, "largeSpacing")
    check(re.search(r"id: col\n(?:.*\n)*?\s+QQC2\.Label \{\n\s+id: label\n\s+text", backend.sourceText) is not None
          and binding("label", "x") is None,
          "dropped into a Column: added to it, without a position")
    QTimer.singleShot(300, s4b)


def s4b():
    # dropped near the area's centre and middle lines: it lines up with them
    # (196, 108), not with the grid (192, 112)
    d = [i for i in find_all(lambda i: i.property("text") == "Button" and i.property("iconName") is not None) if i.isVisible()][0]
    a, b = d.mapToScene(QPointF(d.width() / 3, d.height() / 2)).toPoint(), scene_of(195, 111)
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, 21):
        QTest.mouseMove(win, a + (b - a) * i / 20)
        QTest.qWait(20)
    shown = guides()
    check(any(w == 1 for _x, _y, w, _h in shown) and any(h == 1 for _x, _y, _w, h in shown),
          f"guides while dropping: {shown}")
    win.grabWindow().save(f"{OUT}/drop-guides.png")
    ghost = one("dropGhost")
    gpos = ghost.mapToItem(one("previewHost"), QPointF(0, 0)) if ghost else None
    check(ghost is not None and (round(gpos.x()), round(gpos.y())) == (196, 108),
          f"a preview of its size, at the aligned point ({gpos.x() if gpos else None}, {gpos.y() if gpos else None})")
    ghost_size = (round(ghost.width()), round(ghost.height())) if ghost else None
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, b)
    QTest.qWait(400)
    check(one("dropGhost") is None, "no size preview after the drop")
    item = backend.previewItemFor(backend.selectedUid)[0]
    check(ghost_size == (round(item.width()), round(item.height())),
          f"the preview had the dropped Button's size ({ghost_size}, {item.width()} × {item.height()})")
    check(backend.selectedId == "button" and binding("button", "x") == "100" and binding("button", "y") == "60",
          f"dropped on the area's centre lines: {binding('button', 'x')}, {binding('button', 'y')}")
    check(guides() == [], "no guides after the drop")
    backend.undo()
    QTimer.singleShot(300, e1)


def e1():
    # equal spacing: a and b are 22 apart in a row; m is dragged next to b
    backend.discardAll()
    with open(f"{OUT}/grid/Spacing.qml", "w") as fh:
        fh.write("""import QtQuick
import org.kde.kirigami as Kirigami

Item {
    width: 400
    height: 300
    Rectangle {
        id: a
        x: 40
        y: 100
        width: 40
        height: 40
    }
    Rectangle {
        id: b
        x: 102
        y: 100
        width: 40
        height: 40
    }
    Rectangle {
        id: m
        x: 200
        y: 200
        width: 40
        height: 40
        color: "steelblue"
    }
    Rectangle {
        id: c
        x: 300
        y: 100
        width: 40
        height: 40
    }
}
""")
    backend.openFile(f"{OUT}/grid/Spacing.qml")
    wait_until(lambda: backend.previewItemFor(uid("m")), e2, timeout=20, what="the spacing document")


def drag_m(to_x, to_y, then):
    backend.select(uid("m"))
    QTest.qWait(300)
    it = backend.previewItemFor(uid("m"))[0]
    p = it.mapToItem(one("previewHost"), QPointF(0, 0))
    a = scene_of(p.x() + 20, p.y() + 20)
    b = a + QPoint(round(to_x - p.x()), round(to_y - p.y()))
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, 11):
        QTest.mouseMove(win, a + (b - a) * i / 10)
        QTest.qWait(20)
    shown = distances()
    win.grabWindow().save(f"{OUT}/equal-{to_x}.png")
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, b)
    QTest.qWait(300)
    then(shown)


def e2():
    # to 2 px past the gap of a and b (b's right side is at 142, 142 + 22 = 164;
    # the grid would say 168)
    def after(shown):
        check(binding("m", "x") == "164", "snapped to the same gap as a and b: x " + str(binding("m", "x")))
        check(shown.count("= 22") == 2, f"both equal gaps marked: {shown}")
        QTimer.singleShot(300, e3)
    drag_m(166, 100, after)


def e3():
    # between b (ends at 142) and c (starts at 300): midway is 201
    def after(shown):
        check(binding("m", "x") == "201", "midway between its neighbours: x " + str(binding("m", "x")))
        check(shown.count("= 59") == 2, f"its two gaps marked equal: {shown}")
        backend.undo()
        backend.undo()
        QTimer.singleShot(300, e4)
    drag_m(204, 100, after)


def e4():
    # resizing b (102–142) by its right handle toward c (300): 2 px short of
    # the gap of a and b (300 - 22 = 278; the grid would say 280)
    backend.select(uid("b"))
    a = center(handle("r"))
    b = a + QPoint(280 - 142, 0)
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, 11):
        QTest.mouseMove(win, a + (b - a) * i / 10)
        QTest.qWait(20)
    shown = distances()
    win.grabWindow().save(f"{OUT}/equal-resize.png")
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, b)
    QTest.qWait(300)
    check(binding("b", "width") == "Kirigami.Units.largeSpacing * 22", "right side (176 wide) snapped to the same gap as on its left: width " + str(binding("b", "width")))
    check(shown.count("= 22") == 2, f"both gaps marked equal: {shown}")
    # the left handle toward a: the gap it has on its right (22) again
    a = center(handle("l"))
    b = a + QPoint(105 - 102, 0)
    drag(a, b)
    check(binding("b", "x") == "102" and binding("b", "width") == "Kirigami.Units.largeSpacing * 22", "and its left side keeps it: x " + str(binding("b", "x")))
    backend.undo()
    QTimer.singleShot(300, e5)


def e5():
    # a Button (80 × 24) dropped into the gap between b (ends at 142) and c
    # (starts at 300): stretched to fill it with a and b's gap (22) on both
    # sides: x 164, 114 wide
    d = [i for i in find_all(lambda i: i.property("text") == "Button" and i.property("iconName") is not None) if i.isVisible()][0]
    a, b = d.mapToScene(QPointF(d.width() / 3, d.height() / 2)).toPoint(), scene_of(180, 108)
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, 21):
        QTest.mouseMove(win, a + (b - a) * i / 20)
        QTest.qWait(20)
    ghost = one("dropGhost")
    gpos = ghost.mapToItem(one("previewHost"), QPointF(0, 0)) if ghost else None
    shown = distances()
    win.grabWindow().save(f"{OUT}/fit.png")
    check(ghost is not None and (round(gpos.x()), round(ghost.width())) == (164, 114),
          f"the preview fills the gap: x {gpos.x() if gpos else None}, {ghost.width() if ghost else None} wide")
    check(shown.count("= 22") == 3, f"with equal gaps on both sides: {shown}")
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, b)
    QTest.qWait(400)
    check(binding("button", "x") == "164" and binding("button", "width") == "114",
          f"dropped with that size: x {binding('button', 'x')}, width {binding('button', 'width')}")
    check(binding("button", "height") is None, "its height is its own (nothing to fit in a column)")
    backend.undo()
    QTimer.singleShot(300, e6)


def e6():
    # a BusyIndicator (36 × 36) dropped in the open, above m: as wide and high
    # as the 40 × 40 squares around it
    backend.setPaletteFilter("busy")
    QTest.qWait(300)
    d = [i for i in find_all(lambda i: i.property("text") == "BusyIndicator" and i.property("iconName") is not None) if i.isVisible()][0]
    a, b = d.mapToScene(QPointF(d.width() / 3, d.height() / 2)).toPoint(), scene_of(203, 33)
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, 21):
        QTest.mouseMove(win, a + (b - a) * i / 20)
        QTest.qWait(20)
    ghost = one("dropGhost")
    shown = distances()
    win.grabWindow().save(f"{OUT}/equal-size-drop.png")
    check(ghost is not None and (round(ghost.width()), round(ghost.height())) == (40, 40),
          f"the preview takes the others' size: {ghost.width() if ghost else None} × {ghost.height() if ghost else None}")
    check(shown.count("= 40") >= 2, f"equal sizes marked: {shown}")
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, b)
    QTest.qWait(400)
    new = backend.selectedId
    check(binding(new, "width") == "Kirigami.Units.largeSpacing * 5" and binding(new, "height") == "Kirigami.Units.largeSpacing * 5",
          f"dropped at that size: {binding(new, 'width')}, {binding(new, 'height')}")
    backend.undo()
    backend.setPaletteFilter("button")
    QTimer.singleShot(300, v1)


def v1():
    # the same in a column: p and q are 22 apart, r is further down
    backend.discardAll()
    with open(f"{OUT}/grid/Column.qml", "w") as fh:
        fh.write("""import QtQuick
import org.kde.kirigami as Kirigami

Item {
    width: 400
    height: 300
    Rectangle {
        id: p
        x: 100
        y: 20
        width: 80
        height: 40
    }
    Rectangle {
        id: q
        x: 100
        y: 82
        width: 80
        height: 40
    }
    Rectangle {
        id: r
        x: 100
        y: 250
        width: 80
        height: 40
    }
    Rectangle {
        id: s
        x: 250
        y: 20
        width: 50
        height: 37
    }
}
""")
    backend.openFile(f"{OUT}/grid/Column.qml")
    wait_until(lambda: backend.previewItemFor(uid("r")), v2, timeout=20, what="the column document")


def v2():
    # a Button (80 × 24) dropped below q (ends at 122), above r (starts at
    # 250): as tall as the gap leaves with 22 above and below: y 144, 84 high
    d = [i for i in find_all(lambda i: i.property("text") == "Button" and i.property("iconName") is not None) if i.isVisible()][0]
    a, b = d.mapToScene(QPointF(d.width() / 3, d.height() / 2)).toPoint(), scene_of(110, 150)
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, 21):
        QTest.mouseMove(win, a + (b - a) * i / 20)
        QTest.qWait(20)
    ghost = one("dropGhost")
    gpos = ghost.mapToItem(one("previewHost"), QPointF(0, 0)) if ghost else None
    shown = distances()
    win.grabWindow().save(f"{OUT}/fit-column.png")
    check(ghost is not None and (round(gpos.y()), round(ghost.height())) == (144, 84),
          f"the preview fills the gap in the column: y {gpos.y() if gpos else None}, {ghost.height() if ghost else None} high")
    check(shown.count("= 22") == 3, f"with equal gaps above and below: {shown}")
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, b)
    QTest.qWait(400)
    check(binding("button", "y") == "Kirigami.Units.largeSpacing * 18" and binding("button", "height") == "84",
          f"dropped with that height: y {binding('button', 'y')}, height {binding('button', 'height')}")
    check(binding("button", "width") is None, "its width is its own (nothing to fit in a row)")
    backend.undo()
    QTimer.singleShot(300, v3)


def v3():
    # equal sizes: s (250, 20, 50 × 37) widened by its right handle to 2 px
    # short of p, q and r's width (80); the grid alone would say 78
    backend.select(uid("s"))
    a = center(handle("r"))
    b = a + QPoint(28, 0)
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, 11):
        QTest.mouseMove(win, a + (b - a) * i / 10)
        QTest.qWait(20)
    shown = distances()
    win.grabWindow().save(f"{OUT}/equal-size.png")
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, b)
    QTest.qWait(300)
    check(binding("s", "width") == "Kirigami.Units.largeSpacing * 10", "as wide as the others (80): " + str(binding("s", "width")))
    check(shown.count("= 80") == 3, f"it and the two as wide nearby marked (r is too far): {shown}")
    # its bottom handle: 2 px down, to 39, 1 short of the others' height (40);
    # the grid alone would say 36 (bottom 56). (Past the drag threshold first.)
    a = center(handle("b"))
    b = a + QPoint(0, 2)
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, a)
    for p in [a + QPoint(0, 6 * i) for i in range(1, 4)] + [a + QPoint(0, 10), a + QPoint(0, 6), b]:
        QTest.mouseMove(win, p)
        QTest.qWait(20)
    shown = distances()
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, b)
    QTest.qWait(300)
    check(binding("s", "height") == "Kirigami.Units.largeSpacing * 5", "as high as the others (40): " + str(binding("s", "height")))
    check(shown.count("= 40") == 3 and "= 80" not in shown, f"heights marked, not widths: {shown}")
    backend.undo()
    backend.undo()
    QTimer.singleShot(300, s5)


def s5():
    # a document without Kirigami: pixels
    backend.discardAll()
    with open(f"{OUT}/grid/Plain.qml", "w") as fh:
        fh.write("import QtQuick\n\nItem {\n    width: 200\n    height: 200\n    Rectangle {\n        id: r\n        width: 20\n        height: 20\n    }\n}\n")
    backend.openFile(f"{OUT}/grid/Plain.qml")
    QTimer.singleShot(800, s6)


def s6():
    backend.placeAt(one("previewHost"), uid("r"), 24, 16, 8, "largeSpacing")
    check(binding("r", "x") == "24" and binding("r", "y") == "16" and "kirigami" not in backend.sourceText,
          "without a Kirigami import: pixels, and no import added")
    backend.discardAll()
    backend.openFile(UI)
    QTimer.singleShot(1000, s7)


def s7():
    check(backend.placementProblem(uid("okButton")) == "", "a widget in a form without a layout can be moved")
    check("layout" in backend.placementProblem(uid("option")), "one in a layout can't")
    backend.select(uid("okButton"))
    drag(scene_of(40, 20), scene_of(40 + 29, 20 + 13), shot="moving-ui")
    t = backend.sourceText
    check("<x>40</x>" in t and "<y>24</y>" in t and "<width>90</width>" in t,
          "dragged widget snapped to the grid, size kept")
    QTest.keyClick(win, Qt.Key_Left)
    QTest.qWait(100)
    check("<x>32</x>" in backend.sourceText, "Left: previous grid line")
    a = center(handle("br"))
    drag(a, a + QPoint(13, 5))
    check("<width>104</width>" in backend.sourceText and "<height>32</height>" in backend.sourceText,
          "form: resized widget's corner on the grid")
    target = backend.dropTarget(None, 50, 200)
    check(target.get("label") == "Free" and target.get("free"), f"drop target: the form ({target})")
    laid = backend.dropTarget(None, 250, 200)
    check(laid.get("label") == "laidOut" and not laid.get("free"), f"the group box with a layout: placed by it ({laid})")
    idx = next(i for i, e in enumerate(backend.adapter.palette()) if e.get("type") == "QLabel")
    backend.insertComponentAt(None, idx, 48, 104, 8, "largeSpacing")
    QTimer.singleShot(800, s8)


def s8():
    t = backend.sourceText
    m = re.search(r'<widget class="QLabel" name="\w+">(?:(?!</widget>).)*<x>48</x>\s*<y>104</y>', t, re.S)
    check(m is not None, "a dropped label is placed at that point, with a geometry")
    check(backend.uiRect(backend.selectedUid)[:2] == [48, 104], f"and shown there ({backend.uiRect(backend.selectedUid)})")
    finish()


def finish():
    win.grabWindow().save(f"{OUT}/grid.png")
    backend.discardAll()
    QTimer.singleShot(300, app.quit)

wait_until(lambda: one("showGridButton") is not None and backend.previewItemFor(uid("box")), s1, timeout=30, what="the design view")
