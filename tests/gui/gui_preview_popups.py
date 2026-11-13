"""What a previewed application shows over itself (its sidebar and other
drawers, dialogs) stays in the preview's frame, not over Kreator's own
interface."""

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest


def rect(item):
    p = item.mapToScene(QPointF(0, 0))
    return [round(p.x()), round(p.y()), round(p.x() + item.width()), round(p.y() + item.height())]


def popup_items(parent):
    """name -> the visible popup items below `parent` (named after their popups)."""
    out, stack = {}, list(parent.childItems())
    while stack:
        it = stack.pop()
        if it.inherits("QQuickPopupItem"):
            if it.isVisible():
                out[it.parent().objectName()] = it
        else:
            stack.extend(it.childItems())
    return out


def layer():
    return by_name("previewPopupLayer")[0]


def strays():
    """Popups of the preview that are still drawn over the whole window."""
    content = win.contentItem()
    found = [c for c in content.childItems() if c.inherits("QQuickPopupItem") and c.isVisible()]
    for overlay in [c for c in content.childItems() if c.inherits("QQuickOverlay")]:
        found += [c for c in overlay.childItems() if c.inherits("QQuickPopupItem") and c.isVisible()]
    return [c.parent().objectName() for c in found]


def opened():
    frame = rect(layer())
    items = popup_items(layer())
    rects = {name: rect(it) for name, it in items.items()}
    print("frame", frame, "popups", rects)
    check(not strays(), f"nothing of the preview is left in the window's overlay ({strays()})")
    check(all(frame[0] <= r[0] and frame[1] <= r[1] and r[2] <= frame[2] and r[3] <= frame[3] for r in rects.values()),
          "every popup of the preview is inside its frame")
    check(rects["sidebar"][:2] == frame[:2] and rects["sidebar"][3] == frame[3],
          "the sidebar is at the frame's left edge, as high as the frame")
    check(rects["rightDrawer"][2] == frame[2] and rects["rightDrawer"][1] == frame[1] and rects["rightDrawer"][3] == frame[3],
          "the drawer at the right edge is at the frame's right edge")
    check(rects["bottomDrawer"][3] == frame[3] and rects["bottomDrawer"][0] == frame[0],
          "the drawer at the bottom edge is at the frame's bottom edge")
    d = rects["dialog"]
    check(abs((d[0] + d[2]) - (frame[0] + frame[2])) <= 2 and abs((d[1] + d[3]) - (frame[1] + frame[3])) <= 2,
          "a dialog centred in the window is centred in the frame")
    dialog = items["dialog"].parent()
    veil = by_name("previewPopupVeil")
    check(not dialog.property("modal"), "a modal dialog doesn't block Kreator's window")
    check(bool(veil) and rect(veil[0]) == frame, "it dims the frame instead")

    # as in the application: a click beside the dialog closes it
    pane = layer()
    while pane is not None and pane.metaObject().indexOfProperty("interact") < 0:
        pane = pane.parentItem()
    pane.setProperty("interact", True)
    side_right, right_left = rects["sidebar"][2], rects["rightDrawer"][0]
    QTest.mouseClick(win, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint((side_right + right_left) // 2, frame[1] + 60))
    wait_until(lambda: "dialog" not in popup_items(layer()), closed, what="the dialog closes")


def closed():
    check("dialog" not in popup_items(layer()), "clicking beside the dialog closes it")
    check(not by_name("previewPopupVeil"), "the frame is no longer dimmed")
    backend.openFile(OUT + "/work/SettingsPage.qml")
    wait_until(lambda: backend.fileName == "SettingsPage.qml" and not popup_items(layer()), other,
               what="the popups go with their preview")


def other():
    check(not popup_items(layer()) and not strays(), "another document: the popups went with their preview")
    check(not by_name("previewPopupVeil"), "and nothing is dimmed")
    app.quit()


backend.openFile(OUT + "/popups/DrawerWindow.qml")
def shown():
    """All four are open (the drawers have slid in) and taken into the frame."""
    items = popup_items(layer())
    return len(items) == 4 and not strays() and all(
        it.parent().property("position") == 1 for it in items.values() if it.parent().inherits("QQuickDrawer"))


wait_until(shown, opened, what="the preview's popups are shown")
