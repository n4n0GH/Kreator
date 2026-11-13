"""Objects covered by others in the design view: the selected one can still be
dragged where another lies on top of it (a plain click there selects the one
on top), and Alt+click selects the object under the selected one, going round;
for QML documents and for forms without layouts."""

import os
import re

from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest

os.makedirs(f"{OUT}/covered", exist_ok=True)
QML = f"{OUT}/covered/Covered.qml"
UI = f"{OUT}/covered/covered.ui"
with open(QML, "w") as fh:
    fh.write("""import QtQuick

Item {
    id: root
    width: 400
    height: 300

    Rectangle {
        id: under
        x: 40
        y: 40
        width: 120
        height: 80
        color: "steelblue"
    }
    Rectangle {
        id: over
        x: 80
        y: 56
        width: 120
        height: 80
        color: "tomato"
    }
    Rectangle {
        id: holder
        x: 240
        y: 160
        width: 120
        height: 100
        Rectangle {
            id: inner
            x: 16
            y: 16
            width: 40
            height: 40
        }
    }
}
""")
with open(UI, "w") as fh:
    fh.write("""<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Covered</class>
 <widget class="QWidget" name="Covered">
  <property name="geometry">
   <rect><x>0</x><y>0</y><width>400</width><height>300</height></rect>
  </property>
  <widget class="QFrame" name="underFrame">
   <property name="geometry">
    <rect><x>40</x><y>40</y><width>120</width><height>80</height></rect>
   </property>
   <property name="frameShape"><enum>QFrame::Box</enum></property>
  </widget>
  <widget class="QFrame" name="overFrame">
   <property name="geometry">
    <rect><x>80</x><y>56</y><width>120</width><height>80</height></rect>
   </property>
   <property name="frameShape"><enum>QFrame::Box</enum></property>
  </widget>
 </widget>
</ui>
""")

win.resize(1400, 900)
backend.openFile(QML)


def uid(ident):
    return next(r["uid"] for r in backend.outline.rows() if r["objectId"] == ident)


def binding(ident, name):
    m = re.search(r"id: " + ident + r"\n((?:\s+[^\n]*\n)*?)\s*}", backend.sourceText)
    b = re.search(r"\n\s*" + name + r": ([^\n]+)", "\n" + m.group(1)) if m else None
    return b.group(1).strip() if b else None


def ui_geometry(name):
    m = re.search(r'name="' + name + r'">\s*<property name="geometry">\s*<rect>\s*<x>(\d+)</x>\s*<y>(\d+)</y>', backend.sourceText)
    return (int(m.group(1)), int(m.group(2))) if m else None


def at(x, y):
    """A point of the design view (preview coordinates) in the window."""
    return by_name("designCanvas")[0].mapToScene(QPointF(x, y)).toPoint()


def click(p, modifiers=Qt.NoModifier):
    QTest.mouseClick(win, Qt.LeftButton, modifiers, p)
    QTest.qWait(100)


def drag(a, b, steps=8):
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, steps + 1):
        QTest.mouseMove(win, a + (b - a) * i / steps)
        QTest.qWait(20)
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, b)
    QTest.qWait(200)


# where both rectangles are: (100, 70); only the lower one: (50, 50)
def q1():
    click(at(100, 70))
    check(backend.selectedId == "over", f"a click where two overlap selects the one on top ({backend.selectedId})")
    click(at(100, 70), Qt.AltModifier)
    check(backend.selectedId == "under", f"Alt+click: the one under it ({backend.selectedId})")
    click(at(100, 70), Qt.AltModifier)
    check(backend.selectedId == "root", f"Alt+click again: the next one down ({backend.selectedId})")
    click(at(100, 70), Qt.AltModifier)
    check(backend.selectedId == "over", f"and round to the top again ({backend.selectedId})")

    # the covered one, selected, is dragged by where the other covers it
    backend.select(uid("under"))
    QTest.qWait(150)
    drag(at(100, 70), at(100 + 64, 70 + 120))
    check((binding("under", "x"), binding("under", "y")) == ("104", "160"),
          f"dragging the selected, covered rectangle moves it ({binding('under', 'x')}, {binding('under', 'y')})")
    check(binding("over", "x") == "80" and backend.selectedId == "under", "not the one on top, which stays put")
    backend.undo()
    QTimer.singleShot(400, q2)


def q2():
    backend.select(uid("under"))
    QTest.qWait(150)
    click(at(100, 70))
    check(backend.selectedId == "over", f"a plain click there still selects the one on top ({backend.selectedId})")

    # objects inside the selected one are not covering it: they are picked as before
    backend.select(uid("holder"))
    QTest.qWait(150)
    drag(at(240 + 30, 160 + 30), at(240 + 30 + 16, 160 + 30))
    check(backend.selectedId == "inner" and binding("inner", "x") == "32" and binding("holder", "x") == "240",
          f"a child of the selected one is selected and dragged ({backend.selectedId}, {binding('inner', 'x')})")
    backend.discardAll()
    backend.openFile(UI)
    wait_until(lambda: len(backend.uiRect(next(r["uid"] for r in backend.outline.rows() if r["objectId"] == "overFrame"))) == 4,
               u1, what="the form's preview")


def u1():
    click(at(100, 70))
    check(backend.selectedId == "overFrame", f"form: a click selects the widget on top ({backend.selectedId})")
    click(at(100, 70), Qt.AltModifier)
    check(backend.selectedId == "underFrame", f"form: Alt+click, the one under it ({backend.selectedId})")
    drag(at(100, 70), at(100 + 64, 70 + 120))
    check(ui_geometry("underFrame") == (104, 160) and ui_geometry("overFrame") == (80, 56),
          f"form: dragging moves the covered widget ({ui_geometry('underFrame')})")
    backend.discardAll()
    QTimer.singleShot(300, app.quit)


wait_until(lambda: backend.previewItemFor(uid("over")), lambda: QTimer.singleShot(300, q1), what="the preview")
