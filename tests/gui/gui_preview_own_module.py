"""A file of an application's QML module is previewed with the module's
compiled types (its singletons) stood in for, as found in the build folder,
though it doesn't import the module."""

from PySide6.QtCore import QObject

backend.openFile(OUT + "/ownmodule/src/Main.qml")


def shown():
    o = backend.previewObject
    check(backend.previewError == "", f"the preview is made ({backend.previewError!r})")
    check(o.property("storeTitle") == "" and o.property("noteCount") == 0 and o.property("hasUndo") is True,
          "the module's singleton is stood in for: its properties and methods are there")
    lst = o.findChild(QObject, "list")
    check(lst is not None and lst.property("seesStore") is True, "the module's other files see it too")
    QTimer.singleShot(300, noted)


def noted():
    note = backend.previewNote
    check("org.example.notes" in note and "dummy Store" in note, f"the preview says what is simulated ({note!r})")
    check("not defined" not in note and "Error" not in note,
          "nothing is missing, also in a file the build doesn't know yet")
    app.quit()


wait_until(lambda: backend.previewObject is not None and backend.fileName == "Main.qml", shown,
           what="the preview is shown")
