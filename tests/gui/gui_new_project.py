"""New Project…: the dialog says why a project can't be created, creates the
folder with its first file for each kind of project, remembers where, and
leaves what is open alone."""

import os

from PySide6.QtCore import QMetaObject, QObject

WHERE = f"{OUT}/new projects"
errors = []
backend.errorOccurred.connect(errors.append)


def obj(name):
    return win.findChild(QObject, name)


def dialog():
    return obj("newProjectDialog")


def fill(name, location=None, template=None):
    obj("projectNameField").setProperty("text", name)
    if location is not None:
        obj("projectLocationField").setProperty("text", location)
    if template is not None:
        box = obj("projectTemplateBox")
        keys = [t["key"] for t in backend.projectTemplates()]
        box.setProperty("currentIndex", keys.index(template))
    app.processEvents()


def can_create():
    return bool(obj("createProjectAction").property("enabled"))


def open_dialog(then):
    QMetaObject.invokeMethod(win, "newProject")
    wait_until(lambda: dialog().property("opened"), then, what="the dialog opens")


def s1():
    check(any(a.property("text") == "New Project…" for a in page.findChildren(QObject)
              if a.metaObject().indexOfProperty("displayHint") >= 0), "New Project… is in the menu")
    check(os.path.isdir(obj("projectLocationField").property("text")), "an existing folder is suggested: "
          + obj("projectLocationField").property("text"))
    check(not can_create(), "nothing typed: Create is disabled")
    fill("proj", OUT)                       # a folder of the fixtures, with files
    check(not can_create() and "not empty" in dialog().property("problem"), "an existing folder isn't taken over")
    fill("a/b", WHERE)
    check(not can_create() and dialog().property("problem") != "", "a name with a slash is refused")
    fill("Kontakte", WHERE, "widgets-form")
    check(can_create() and dialog().property("filePath") == f"{WHERE}/Kontakte/form.ui",
          "a form project says what it creates: " + dialog().property("filePath"))
    win.grabWindow().save(f"{OUT}/new_project_form.png")
    # Cancel creates nothing
    dialog().close()
    app.processEvents()
    check(not os.path.exists(WHERE) and not backend.hasDocument and backend.projectPath == "", "closed: nothing created")
    open_dialog(s2)


def s2():
    check(obj("projectNameField").property("text") == "", "the dialog starts empty again")
    fill("Kontakte", WHERE, "widgets-form")
    QMetaObject.invokeMethod(dialog(), "create")
    wait_until(lambda: backend.filePath == f"{WHERE}/Kontakte/form.ui", lambda: QTimer.singleShot(700, s3),
               what="the form project opens")


def s3():
    text = open(f"{WHERE}/Kontakte/form.ui", encoding="utf-8").read()
    check(backend.docKind == "ui" and "<class>Kontakte</class>" in text and "<string>Kontakte</string>" in text,
          "the form is named after the project")
    check(backend.projectName == "Kontakte" and backend.previewError == "" and backend.previewMode == "ui",
          "the form is shown")
    check(backend.defaultProjectLocation() == WHERE, "the next project is suggested next to this one")
    # with a project open: another one, of Qt Quick
    backend.setProperty("windowTitle", "string", "Contacts")
    check(backend.modified, "the form has unsaved changes")
    open_dialog(s4)


def s4():
    check(obj("projectLocationField").property("text") == WHERE, "the dialog suggests the folder used last")
    fill("Kontakte")
    check(not can_create(), "the same name again is refused")
    fill("Quick One", None, "qtquick")
    QMetaObject.invokeMethod(dialog(), "create")
    wait_until(lambda: backend.filePath == f"{WHERE}/Quick One/Main.qml", lambda: QTimer.singleShot(700, s5),
               what="the Qt Quick project opens")


def s5():
    check(backend.projectName == "Quick One" and 'title: qsTr("Quick One")' in backend.sourceText
          and backend.previewError == "", "the Qt Quick window is shown")
    docs = {d["name"]: d for d in backend.openDocuments}
    check(set(docs) == {"form.ui", "Main.qml"} and docs["form.ui"]["modified"],
          "the form stays open, with its unsaved changes")
    check([r["relPath"] for r in backend.projectFiles.rows()] == ["Main.qml"], "the Files tab shows the new project")
    check(not errors, f"no errors {errors}")
    # a folder that can't be written to: reported, the dialog stays
    check(backend.createProject("x", "/proc/kreator-test", "kirigami-app") is False and len(errors) == 1,
          f"a project that can't be created is reported {errors}")
    app.quit()


QTimer.singleShot(800, lambda: open_dialog(s1))
