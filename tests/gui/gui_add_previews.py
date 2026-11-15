"""The Add tab shows what a component looks like before it is added: beside
the row the pointer is on, or the current one with the arrow keys."""

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest

from kreator import palette

TIMEOUT = 180

warnings = []
backend.engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))


def item(name):
    return find_all(lambda it: it.objectName() == name)[0]


def rows():
    """The list's rows on screen, by component name."""
    return {r.property("name"): r for r in find_all(
        lambda it: it.property("iconName") is not None and it.property("module") is not None) if r.isVisible()}


def hover(it):
    p = it.mapToScene(QPointF(it.width() / 2, it.height() / 2)).toPoint()
    QTest.mouseMove(win, p + QPoint(4, 0))
    QTest.mouseMove(win, p)


def type_text(text):
    for ch in text:
        QTest.keyClick(win, ch)


def shown():
    """The name of the component the preview shows ("" if it is hidden)."""
    return flyout.property("name") if flyout.isVisible() else ""


def steps(*fns, pause=300):
    def run(i):
        fns[i]()
        if i + 1 < len(fns):
            QTimer.singleShot(pause, lambda: run(i + 1))
    run(0)


backend.openFile(REPO + "/examples/SettingsPage.qml")
panel = find_all(lambda it: it.property("componentPreviews") is not None and it.property("shownTab") is not None)[0]
flyout = item("componentPreview")
stage = item("componentPreviewStage")
search = find_all(lambda it: it.property("placeholderText") == "Search components…")[0]


def every_qml_component():
    panel.setProperty("currentTab", 2)
    failed, wrong = [], []
    for i, e in enumerate(backend.adapter.palette()):
        got = backend.componentPreview(i, stage)
        drawn = palette.preview_stage(e) != "none"
        if drawn and got["kind"] != "item":
            failed.append(f"{e['name']}: {backend.qml_preview.demo_errors(palette.preview_qml(e)) or got}")
        elif not drawn and (got["kind"] != "none" or not got["note"]):
            wrong.append(e["name"])
        elif drawn and got["item"].parentItem() is not stage:
            wrong.append(e["name"])
        QTest.qWait(30)
    check(not failed, f"every component that is drawn can be shown: {failed or 'all of them'}")
    check(not wrong, f"what isn't drawn says so in a note, the others stand on the stage: {wrong or 'all of them'}")
    backend.clearComponentPreview()
    QTest.qWait(200)
    check(not stage.childItems(), f"nothing is left on the stage: {len(stage.childItems())} items")
    ours = [w for w in dict.fromkeys(warnings) if ".kreator-palette-" in w]
    check(not ours, f"the previews make no warnings: {ours or 'none'}")
    check(backend.previewNote == "", f"and none end up among the document's: {backend.previewNote!r}")


def with_the_pointer():
    check(shown() == "", "no preview before a row is pointed at")
    hover(rows()["Page"])
    wait_until(lambda: shown() == "Page", pointed, 5, "pointing at a row shows its preview")


def pointed():
    check(shown() == "Page", "pointing at a row shows its preview")
    live = stage.childItems()
    check(len(live) == 1 and live[0].width() > 100 and live[0].height() > 100,
          f"with the live component on its stage: {[(c.width(), c.height()) for c in live]}")
    edge = panel.mapToScene(QPointF(panel.width(), 0)).x()
    check(flyout.mapToScene(QPointF(0, 0)).x() >= edge, "beside the sidebar, not over the list")
    row = rows()["Page"]
    mid = row.mapToScene(QPointF(0, row.height() / 2)).y()
    top = flyout.mapToScene(QPointF(0, 0)).y()
    check(top >= 0 and top + flyout.height() <= win.height() and top <= mid + 1, "level with its row, inside the window")
    check(item("componentPreviewName").property("text") == "Page", "named in its header")
    win.grabWindow().save(f"{OUT}/preview-page.png")
    hover(rows()["GlobalDrawer"])
    wait_until(lambda: shown() == "GlobalDrawer", moved, 3, "the preview follows the pointer")


def moved():
    check(shown() == "GlobalDrawer", "the preview follows the pointer to the next row")
    check("sketch" in item("componentPreviewNote").property("text"), "a note says what the preview can't show")
    # typing goes on while a dialog is previewed: it doesn't take the keyboard
    search.forceActiveFocus()
    type_text("dialog")
    QTest.qWait(300)
    hover(rows()["PromptDialog"])
    wait_until(lambda: shown() == "PromptDialog", dialog, 3, "a dialog's preview")


def dialog():
    QTest.qWait(400)
    check(shown() == "PromptDialog", "a dialog is shown open")
    win.grabWindow().save(f"{OUT}/preview-dialog.png")
    type_text("x")
    check(search.property("text") == "dialogx", f"the keyboard stays with the search field: {search.property('text')!r}")
    # away from the list: gone, with what it showed
    QTest.mouseMove(win, QPoint(win.width() - 300, win.height() // 2))
    wait_until(lambda: shown() == "", left, 3, "the preview goes when the pointer leaves the list")


def left():
    check(shown() == "", "the preview goes when the pointer leaves the list")
    QTest.qWait(200)
    check(not stage.childItems() and backend._palette_item is None, "and its component with it")
    # with the keyboard: down from the search field, Enter adds
    search.setProperty("text", "chip")
    QTest.qWait(300)
    QTest.keyClick(win, Qt.Key_Down)
    wait_until(lambda: shown() == "Chip", by_keyboard, 5, "the arrow keys show a preview")


def by_keyboard():
    check(shown() == "Chip", "Down from the search field shows the first component's preview")
    QTest.keyClick(win, Qt.Key_Return)
    QTest.qWait(300)
    check("Kirigami.Chip {" in backend.sourceText, "Enter adds it")
    backend.undo()
    QTest.keyClick(win, Qt.Key_Escape)
    wait_until(lambda: shown() == "", switched_off, 3, "Escape closes the preview")


def switched_off():
    check(shown() == "", "Escape closes the preview")
    view = find_all(lambda it: it.property("byKeyboard") is not None)[0]
    search.forceActiveFocus()
    search.setProperty("text", "")
    QTest.qWait(300)
    check(view.property("currentIndex") == -1 and view.property("contentY") == 0,
          f"back in the search field, the list has no current row to scroll to: row {view.property('currentIndex')}, "
          f"scrolled by {view.property('contentY')}")
    button = item("componentPreviewsButton")
    check(button.property("checked") is True, "previews are on at first")
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier,
                     button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint())
    check(panel.property("componentPreviews") is False, "the button switches them off")
    hover(rows()["Page"])
    QTest.qWait(1500)
    check(shown() == "", "then pointing at a row shows none")
    panel.setProperty("componentPreviews", True)
    check(button.property("checked") is True, "and on again")
    QTest.mouseMove(win, QPoint(win.width() - 300, win.height() // 2))
    QTest.qWait(200)

    # a form: pictures of the widgets
    backend.openFile(f"{OUT}/work/dialog.ui")
    QTest.qWait(500)
    bad = []
    for i, e in enumerate(backend.adapter.palette()):
        got = backend.componentPreview(i, stage)
        if got["kind"] == "image":
            if not (got["width"] > 0 and got["height"] > 0 and got["source"].startswith("image://kreatorpalette/")):
                bad.append(e["name"])
        elif e["name"] != "QWidget" and e.get("type") != "QFrame":   # (a frame: drawn by some styles only)
            bad.append(e["name"])
        elif not got["note"]:
            bad.append(e["name"])
    check(not bad, f"every widget has a picture: {bad or 'all of them'}")
    hover(rows()["QVBoxLayout"])
    wait_until(lambda: shown() == "QVBoxLayout", widget, 5, "a widget's preview")


def widget():
    picture = item("componentPreviewImage")
    check(shown() == "QVBoxLayout" and picture.isVisible() and picture.width() > 40 and picture.height() > 40,
          f"a form's components are shown as pictures: {picture.width()} × {picture.height()}")
    win.grabWindow().save(f"{OUT}/preview-widget.png")
    app.quit()


steps(lambda: None, every_qml_component, with_the_pointer, pause=1000)
