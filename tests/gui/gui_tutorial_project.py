"""From nothing to a working application, entirely in Kreator: New Project…,
then the to-do app of the Kirigami Design Guide's tutorial
(https://n4n0gh.github.io/Doku/tutorial/overview/), built step by step with
what Kreator offers: the Add tab (also into a page's header and footer, a
control's contentItem, a field's actions), the properties panel (values,
expressions, signal handlers, declared properties), the outline (duplicate,
delete, change the type) and, for the functions, the source view.

After every step of the tutorial the preview has to be free of errors; at the
end the application is used in the preview (add, tick, filter, delete with
undo, clear, remember the list) and run on its own with qml6.
"""

NEEDS = ["qml6"]
TIMEOUT = 240

import os
import re

from PySide6.QtCore import QMetaObject, QObject, Q_ARG
from PySide6.QtQml import QQmlExpression, qmlContext

PROJECTS = f"{OUT}/projects"
MAIN = f"{PROJECTS}/Tasks/Main.qml"
errors = []
backend.errorOccurred.connect(errors.append)


def v(x):
    return x.toVariant() if hasattr(x, "toVariant") else x


def obj(name):
    return win.findChild(QObject, name)


# ------------------------------------------------------------------ what a user does
def pal(name):
    return next(i for i, e in enumerate(backend.adapter.palette()) if e["name"] == name)


def sel(type_, ident=None, label=None, nth=0):
    """Select an object in the outline."""
    found = [r for r in backend.outline.rows()
             if r["typeName"] == type_ and (ident is None or r["objectId"] == ident)
             and (label is None or r["label"] == label)]
    backend.select(found[nth]["uid"])
    return found[nth]["uid"]


def add(name, into=""):
    """Click a component in the Add tab; `into`: the entry of "Add to" chosen first."""
    if into:
        box = obj("insertSlotBox")
        choices = v(box.property("model"))
        index = next(i for i, c in enumerate(choices) if c["name"] == into)
        if choices[index]["full"]:
            raise AssertionError(f"{into} is taken")
        QMetaObject.invokeMethod(box, "activated", Q_ARG(int, index))
        app.processEvents()
        if backend.insertSlot != into or box.property("currentIndex") != index:
            raise AssertionError(f"Add to: {into} was not chosen")
    backend.insertComponent(pal(name))
    if into:
        # the new object is selected, to be filled next: back to its contents
        app.processEvents()
        if backend.insertSlot != "" or obj("insertSlotBox").property("currentIndex") != 0:
            raise AssertionError("Add to: did not go back to the contents")
        if backend.adapter.doc.locate(backend.selectedUid)[1].name != into:
            raise AssertionError(f"{name} was not put into {into}")


def new_property(name, value=""):
    """The fields at the bottom of the properties panel, and Add."""
    obj("newPropertyName").setProperty("text", name)
    obj("newPropertyValue").setProperty("text", value)
    button = obj("addPropertyButton")
    if not button.property("enabled"):
        raise AssertionError(f"Add is disabled for {name!r}")
    QMetaObject.invokeMethod(button, "clicked")


def edit(name, value, expression=False):
    """A property's editor in the properties panel (expression: "Edit as Expression")."""
    row = next(r for r in backend.properties.rows() if r["name"] == name)
    kind = "expression" if expression or row["kind"] == "unset" else row["kind"]
    backend.setProperty(name, kind, value)


def remove(name):
    backend.removeProperty(name)


def write_code(change):
    """The source view: change the text, then Apply."""
    text = change(backend.sourceText)
    if not backend.applySource(text):
        raise AssertionError("source does not parse: " + backend.sourceError)


def window_code(code):
    """Add code (functions) to the window, above its page."""
    block = "".join(("    " + ln if ln.strip() else "") + "\n" for ln in code.strip("\n").split("\n"))
    def change(text):
        at = text.index("    pageStack.initialPage:")
        return text[:at] + block + "\n" + text[at:]
    write_code(change)


def replace_code(pattern, replacement):
    def change(text):
        new, n = re.subn(pattern, lambda _m: replacement, text, count=1, flags=re.S)
        if n != 1:
            raise AssertionError("not found in the source: " + pattern)
        return new
    write_code(change)


# ------------------------------------------------------------------ the running preview
def js(expression):
    root = backend.previewObject
    e = QQmlExpression(qmlContext(root), root, expression)
    result = e.evaluate()
    if e.hasError():
        raise AssertionError(f"{expression}: {e.error().toString()}")
    return result[0] if isinstance(result, tuple) else result


def settled(then):
    """Once the preview shows the document as it is now."""
    def wait():
        wait_until(lambda: not backend._preview_timer.isActive(), lambda: QTimer.singleShot(400, then),
                   what="the preview is up to date")
    QTimer.singleShot(50, wait)


def in_turns(steps, then):
    """Run a generator; at every `yield` the preview catches up first (as it
    has for a user by the time they look at the Add tab again)."""
    def advance():
        try:
            next(steps)
        except StopIteration:
            then()
            return
        settled(advance)
    advance()


def step_done(name, *expected):
    src = backend.sourceText
    problems = [backend.previewError] if backend.previewError else []
    problems += [ln for ln in backend.previewNote.split("\n") if "Error" in ln or "left out" in ln.lower()]
    check(not problems and not errors, f"{name}: the preview shows it without errors {problems + errors}")
    missing = [e for e in expected if e not in src]
    check(not missing, f"{name}: the document has what the tutorial's has {missing}")
    errors.clear()
    check(backend.save() and open(MAIN, encoding="utf-8").read() == src, f"{name}: saved")


# ------------------------------------------------------------------ New Project…
def create_project():
    check(len(by_name("newProjectButton")) == 1, "the welcome screen offers New Project…")
    QMetaObject.invokeMethod(win, "newProject")
    wait_until(lambda: obj("newProjectDialog").property("opened"), fill_in, what="the dialog opens")


def fill_in():
    dialog = obj("newProjectDialog")
    check(dialog.property("problem") != "" and not obj("createProjectAction").property("enabled"),
          "without a name, Create is disabled")
    obj("projectLocationField").setProperty("text", PROJECTS)
    obj("projectNameField").setProperty("text", "Tasks")
    app.processEvents()
    check(dialog.property("problem") == "" and dialog.property("filePath") == MAIN,
          "name and folder given: says what it creates")
    win.grabWindow().save(f"{OUT}/tutorial_new_project.png")
    QMetaObject.invokeMethod(obj("createProjectAction"), "trigger")
    wait_until(lambda: backend.filePath == MAIN, lambda: settled(project_created), what="the project opens")


def project_created():
    check(os.path.isfile(MAIN) and backend.projectPath == f"{PROJECTS}/Tasks" and not backend.modified,
          "the folder and Main.qml exist and are open")
    check([r["relPath"] for r in backend.projectFiles.rows()] == ["Main.qml"], "the Files tab lists Main.qml")
    check(not obj("newProjectDialog").property("opened") and not page.property("sourceMode")
          and len(by_name("insertSlotBox")) == 1, "the design view with the Add tab is shown")
    check(backend.previewMode == "window" and backend.previewError == "" and backend.issueCount == 0,
          "the new window previews, and follows the guidelines")
    check(backend.projectProblem("Tasks", PROJECTS) != "", "the same project can't be created twice")
    step1()


# ------------------------------------------------------------------ 1. A window and a page
def step1():
    # the window and its page are there; the window is selected
    check(backend.isRootSelected, "the window is selected")
    add("Label")                       # what is drawn goes on the window's page
    edit("text", "Nothing here yet.")
    settled(lambda: (step_done("step 1", 'title: qsTr("Tasks")', "width: Kirigami.Units.gridUnit * 24",
                               "pageStack.initialPage: Kirigami.ScrollablePage {",
                               'text: qsTr("Nothing here yet.")'),
                     check(backend.adapter.parent_type(backend.selectedUid).endswith("ScrollablePage"),
                           "the label was added to the page"),
                     step2()))


# ------------------------------------------------------------------ 2. A list of tasks
def step2():
    sel("ApplicationWindow")
    add("ListModel")                   # not drawn: stays with the window
    backend.setSelectedId("tasksModel")
    add("ListElement")
    new_property("title", '"Water the plants"')
    new_property("done", "true")
    backend.duplicateSelected()
    edit("title", "Reply to Konqi")
    edit("done", "false")
    backend.duplicateSelected()
    edit("title", "Book train tickets")
    check(backend.issueCount == 0, "a ListElement's texts are data: no “untranslated” issues")

    sel("Label")
    backend.deleteSelected()
    sel("ScrollablePage")
    add("ListView")
    edit("model", "tasksModel", expression=True)
    new_property("currentIndex", "-1")
    sel("ItemDelegate", label="delegate")
    backend.setSelectedType("QQC2.CheckDelegate")
    new_property("required property string title")
    new_property("required property bool done")
    edit("text", "title", expression=True)
    new_property("checked", "done")
    settled(lambda: (step_done("step 2", "ListModel {\n        id: tasksModel",
                               'ListElement {\n            title: "Water the plants"\n            done: true',
                               'title: "Book train tickets"\n            done: false',
                               "model: tasksModel", "currentIndex: -1", "delegate: QQC2.CheckDelegate {",
                               "required property string title", "required property bool done",
                               "width: ListView.view.width", "text: title", "checked: done"),
                     check(js("tasksModel.count") == 3 and js("listView.count") == 3, "the list shows three tasks"),
                     step3()))


# ------------------------------------------------------------------ 3. Adding tasks
def step3():
    in_turns(step3_build(), lambda: step_done(
        "step 3", "function addTask(title: string): void {",
        "header: QQC2.ToolBar {", "contentItem: Kirigami.ActionTextField {\n                id: newTaskField",
        'placeholderText: qsTr("Add a task")', "rightActions: Kirigami.Action {",
        'icon.name: "list-add"', 'text: qsTr("Add Task")',
        "enabled: newTaskField.text.trim().length > 0", "onTriggered: newTaskField.accepted()") or step3_try())


def step3_build():
    window_code("""
function addTask(title: string): void {
    const trimmed = title.trim()
    if (trimmed.length > 0) {
        tasksModel.append({ title: trimmed, done: false })
    }
}
""")
    yield
    sel("ScrollablePage")
    add("ToolBar", into="header")
    yield
    add("ActionTextField", into="contentItem")
    backend.setSelectedId("newTaskField")
    edit("placeholderText", "Add a task")
    new_property("onAccepted", "{ root.addTask(text); clear() }")
    sel("Action", label="rightActions")
    edit("text", "Add Task")
    new_property("enabled", "newTaskField.text.trim().length > 0")
    new_property("onTriggered", "newTaskField.accepted()")
    yield


def step3_try():
    js('newTaskField.text = "Call the plumber"')
    js("newTaskField.accepted()")
    js('newTaskField.text = "   "')
    js("newTaskField.accepted()")
    check(js("tasksModel.count") == 4 and js("tasksModel.get(3).title") == "Call the plumber"
          and js("newTaskField.text") == "", "typing a task and Enter adds it; only spaces add nothing")
    step4()


# ------------------------------------------------------------------ 4. Ticking off and deleting
def step4():
    in_turns(step4_build(), lambda: step_done(
        "step 4", "import QtQuick.Layouts", "delegate: QQC2.ItemDelegate {\n                id: row",
        "required property int index", 'onClicked: tasksModel.setProperty(index, "done", !done)',
        "contentItem: RowLayout {", "spacing: Kirigami.Units.smallSpacing",
        "checked: row.done", 'onToggled: tasksModel.setProperty(row.index, "done", checked)',
        "Layout.fillWidth: true", "text: row.title", "elide: Text.ElideRight",
        "font.strikeout: row.done", "opacity: row.done ? 0.6 : 1",
        'text: qsTr("Delete")', 'icon.name: "edit-delete"',
        "display: QQC2.AbstractButton.IconOnly", "onClicked: root.deleteTask(row.index)",
        "QQC2.ToolTip.text: text", "function deleteTask(row: int): void {") or step4_try())


def step4_build():
    sel("CheckDelegate")
    backend.setSelectedType("QQC2.ItemDelegate")
    backend.setSelectedId("row")
    remove("text")
    remove("checked")
    new_property("onClicked", 'tasksModel.setProperty(index, "done", !done)')
    yield
    add("RowLayout", into="contentItem")
    add("CheckBox")
    remove("text")
    new_property("checked", "row.done")
    new_property("onToggled", 'tasksModel.setProperty(row.index, "done", checked)')
    add("Label")                       # after the check box
    edit("Layout.fillWidth", "true")   # offered: its parent is a layout
    edit("text", "row.title", expression=True)
    new_property("elide", "Text.ElideRight")
    new_property("font.strikeout", "row.done")
    new_property("opacity", "row.done ? 0.6 : 1")
    add("ToolButton")
    edit("text", "Delete")
    edit("icon.name", "edit-delete")
    new_property("onClicked", "root.deleteTask(row.index)")
    window_code("""
function deleteTask(row: int): void {
    // Keep a copy so the deletion can be undone.
    const task = { title: tasksModel.get(row).title, done: tasksModel.get(row).done }
    tasksModel.remove(row)
    showPassiveNotification("“" + task.title + "” deleted", "long", "Undo",
        () => tasksModel.insert(row, task))
}
""")
    yield


def step4_try():
    js('tasksModel.setProperty(1, "done", true)')
    js("root.deleteTask(2)")
    check(js("tasksModel.count") == 2 and js("tasksModel.get(1).done") is True,
          "ticking changes the data; deleting removes the task")
    step5()


# ------------------------------------------------------------------ 5. The empty state and a counter
def step5():
    in_turns(step5_build(), lambda: step_done(
        "step 5", "ListView {\n            id: tasksView", "anchors.centerIn: parent",
        "width: parent.width - Kirigami.Units.gridUnit * 4", "visible: tasksView.count === 0",
        'icon.name: "checkmark"', 'text: qsTr("No tasks")',
        'explanation: qsTr("Type in the field above and press Enter to add one.")',
        "property int remaining: 0", "function recount(): void {",
        "Connections {", "target: tasksModel", "function onCountChanged() { root.recount() }",
        "Component.onCompleted: recount()", "footer: QQC2.ToolBar {",
        "visible: tasksModel.count > 0", "leftPadding: Kirigami.Units.largeSpacing") or step5_try())


def step5_build():
    sel("ListView")
    backend.setSelectedId("tasksView")
    add("PlaceholderMessage")
    edit("width", "parent.width - Kirigami.Units.gridUnit * 4")
    new_property("visible", "tasksView.count === 0")
    edit("icon.name", "checkmark")
    edit("text", "No tasks")
    edit("explanation", "Type in the field above and press Enter to add one.")

    sel("ApplicationWindow")
    new_property("property int remaining", "0")
    window_code("""
function recount(): void {
    let open = 0
    for (let i = 0; i < tasksModel.count; i++) {
        if (!tasksModel.get(i).done) {
            open++
        }
    }
    remaining = open
}
""")
    sel("ApplicationWindow")
    add("Connections")
    edit("target", "tasksModel")
    replace_code(r"(?<=target: tasksModel\n)", """        function onCountChanged() { root.recount() }
        function onDataChanged() { root.recount() }
""")
    sel("ApplicationWindow")
    new_property("Component.onCompleted", "recount()")

    yield
    sel("ScrollablePage")
    add("ToolBar", into="footer")
    new_property("visible", "tasksModel.count > 0")
    yield
    add("Label", into="contentItem")
    new_property("leftPadding", "Kirigami.Units.largeSpacing")
    edit("text", 'root.remaining === 1 ? qsTr("1 task left") : qsTr("%1 tasks left").arg(root.remaining)',
         expression=True)
    yield


def step5_try():
    check(js("root.remaining") == 2, "two of the three sample tasks are left")
    js('tasksModel.setProperty(1, "done", true)')
    check(js("root.remaining") == 1, "ticking one off counts again")
    js("tasksModel.clear()")
    check(js("tasksView.count") == 0 and js("root.remaining") == 0, "no tasks: the list is empty")
    step6()


# ------------------------------------------------------------------ 6. Filtering
def step6():
    sel("ApplicationWindow")
    new_property("property string filter", '"all"')
    new_property("onFilterChanged", "visibleTasks.invalidateFilter()")
    add("KSortFilterProxyModel")
    backend.setSelectedId("visibleTasks")
    edit("sourceModel", "tasksModel")
    new_property("filterRowCallback", '(row, parent) => { const done = tasksModel.get(row).done; '
                 'return root.filter === "all" || (root.filter === "active" && !done) '
                 '|| (root.filter === "completed" && done) }')
    sel("ListView")
    edit("model", "visibleTasks")
    replace_code(r"function onDataChanged\(\) \{ root\.recount\(\) \}", """function onDataChanged() {
            root.recount()
            visibleTasks.invalidateFilter()
        }""")
    window_code("""
// The list shows filtered rows; this finds a row's place in the real data.
function sourceRow(row: int): int {
    return visibleTasks.mapToSource(visibleTasks.index(row, 0)).row
}

function clearCompleted(): void {
    for (let i = tasksModel.count - 1; i >= 0; i--) {
        if (tasksModel.get(i).done) {
            tasksModel.remove(i)
        }
    }
}
""")
    # the three places where a row touches the data
    sel("ItemDelegate", "row")
    edit("onClicked", 'tasksModel.setProperty(root.sourceRow(index), "done", !done)')
    sel("CheckBox")
    edit("onToggled", 'tasksModel.setProperty(root.sourceRow(row.index), "done", checked)')
    sel("ToolButton")
    edit("onClicked", "root.deleteTask(root.sourceRow(row.index))")

    # the page's actions: a menu with three choices, and a button
    sel("ScrollablePage")
    add("Action")                      # goes into the page's actions
    show = backend.selectedUid
    edit("text", "Show")
    edit("icon.name", "view-filter")
    add("Action")                      # an action in an action: a menu entry
    remove("icon.name")
    edit("text", "All Tasks")
    new_property("checkable", "true")
    new_property("autoExclusive", "true")
    new_property("checked", 'root.filter === "all"')
    new_property("onTriggered", 'root.filter = "all"')
    for text, word in (("Active", "active"), ("Completed", "completed")):
        backend.duplicateSelected()
        edit("text", text)
        edit("checked", f'root.filter === "{word}"')
        edit("onTriggered", f'root.filter = "{word}"')
    check(backend.adapter.doc.locate(backend.selectedUid)[0].uid == show, "the three choices are in the Show action")
    sel("ScrollablePage")
    add("Action")
    edit("text", "Clear Completed")
    edit("icon.name", "edit-clear-all")
    new_property("enabled", "root.remaining < tasksModel.count")
    new_property("onTriggered", "root.clearCompleted()")

    sel("PlaceholderMessage")
    edit("text", 'tasksModel.count === 0 ? qsTr("No tasks") : qsTr("Nothing to show")', expression=True)
    edit("explanation", 'tasksModel.count === 0 ? qsTr("Type in the field above and press Enter to add one.") '
         ': qsTr("No tasks match the current filter.")', expression=True)
    settled(lambda: (step_done("step 6", "import org.kde.kitemmodels as KItemModels", 'property string filter: "all"',
                               "onFilterChanged: visibleTasks.invalidateFilter()",
                               "KItemModels.KSortFilterProxyModel {\n        id: visibleTasks\n        sourceModel: tasksModel",
                               "filterRowCallback: (row, parent) => {", "model: visibleTasks",
                               "function sourceRow(row: int): int {", "function clearCompleted(): void {",
                               'onClicked: tasksModel.setProperty(root.sourceRow(index), "done", !done)',
                               "onClicked: root.deleteTask(root.sourceRow(row.index))", "actions: [",
                               'text: qsTr("Show")', 'icon.name: "view-filter"', 'text: qsTr("All Tasks")',
                               "checkable: true", "autoExclusive: true", 'checked: root.filter === "active"',
                               'onTriggered: root.filter = "completed"', 'text: qsTr("Clear Completed")',
                               'icon.name: "edit-clear-all"', "enabled: root.remaining < tasksModel.count",
                               "onTriggered: root.clearCompleted()"),
                     step6_try()))


def step6_try():
    js('tasksModel.setProperty(0, "done", true)')
    js('root.filter = "active"')
    active = js("tasksView.count")
    js('root.filter = "completed"')
    completed = js("tasksView.count")
    row = js("root.sourceRow(0)")
    js('root.filter = "all"')
    check((active, completed, js("tasksView.count"), row) == (2, 1, 3, 0),
          f"the list shows all, the open or the finished tasks ({active}, {completed})")
    js("root.clearCompleted()")
    check(js("tasksModel.count") == 2 and js("root.remaining") == 2, "Clear Completed removes the finished ones")
    step7()


# ------------------------------------------------------------------ 7. Remembering the list
def step7():
    for _ in range(3):
        sel("ListElement")
        backend.deleteSelected()
    sel("ApplicationWindow")
    add("Settings")
    remove("category")
    new_property("location", 'StandardPaths.writableLocation(StandardPaths.GenericConfigLocation) + "/tasks-tutorial.ini"')
    new_property("property string tasks", '"[]"')
    window_code("""
function load(): void {
    for (const task of JSON.parse(settings.tasks)) {
        tasksModel.append({ title: task.title, done: task.done })
    }
}

function save(): void {
    const list = []
    for (let i = 0; i < tasksModel.count; i++) {
        list.push({ title: tasksModel.get(i).title, done: tasksModel.get(i).done })
    }
    settings.tasks = JSON.stringify(list)
}
""")
    replace_code(r"function onCountChanged\(\) \{ root\.recount\(\) \}", """function onCountChanged() {
            root.recount()
            root.save()
        }""")
    replace_code(r"(?<=visibleTasks\.invalidateFilter\(\)\n)(?=        \})", "            root.save()\n")
    sel("ApplicationWindow")
    edit("Component.onCompleted", "{\n    load()\n    recount()\n}")
    settled(lambda: (step_done("step 7", "import QtCore", "ListModel {\n        id: tasksModel\n    }",
                               "Settings {\n        id: settings", 'property string tasks: "[]"',
                               'location: StandardPaths.writableLocation(StandardPaths.GenericConfigLocation) + "/tasks-tutorial.ini"',
                               "function load(): void {", "function save(): void {",
                               "Component.onCompleted: {\n        load()\n        recount()\n    }"),
                     check("ListElement" not in backend.sourceText, "the sample tasks are gone"),
                     use_it()))


# ------------------------------------------------------------------ the finished application
def use_it():
    win.grabWindow().save(f"{OUT}/tutorial_finished.png")
    check(js("tasksView.count") == 0, "first start: the list is empty")
    for title in ("Water the plants", "Reply to Konqi", "Book train tickets", "  "):
        js(f'root.addTask("{title}")')
    js('tasksModel.setProperty(0, "done", true)')
    check((js("tasksModel.count"), js("root.remaining")) == (3, 2), "three tasks added, one ticked: 2 tasks left")
    js('root.filter = "active"')
    js("root.deleteTask(root.sourceRow(0))")          # the first open task: Reply to Konqi
    check(js("tasksModel.count") == 2 and js("tasksModel.get(1).title") == "Book train tickets",
          "deleting a row of the filtered list removes that task")
    js('root.filter = "all"')
    # (Settings writes its values a moment after they change)
    QTimer.singleShot(1500, lambda: (backend.refresh_preview(),   # the application starts again
                                     settled(started_again)))


def started_again():
    titles = [js(f"tasksModel.get({i}).title") for i in range(js("tasksModel.count"))]
    check(titles == ["Water the plants", "Book train tickets"] and js("tasksModel.get(0).done") is True
          and js("root.remaining") == 1, f"started again: the list was remembered {titles}")
    js("tasksModel.clear()")

    outline = [(r["depth"], (r["label"] + ": " if r["label"] else "") + r["typeName"]) for r in backend.outline.rows()]
    wanted = [(0, "ApplicationWindow"), (1, "pageStack.initialPage: ScrollablePage"), (2, "actions: Action"),
              (3, "Action"), (3, "Action"), (3, "Action"), (2, "actions: Action"), (2, "header: ToolBar"),
              (3, "contentItem: ActionTextField"), (4, "rightActions: Action"), (2, "footer: ToolBar"),
              (3, "contentItem: Label"), (2, "ListView"), (3, "delegate: ItemDelegate"), (4, "contentItem: RowLayout"),
              (5, "CheckBox"), (5, "Label"), (5, "ToolButton"), (3, "PlaceholderMessage"), (1, "ListModel"),
              (1, "Connections"), (1, "KSortFilterProxyModel"), (1, "Settings")]
    check(sorted(outline) == sorted(wanted), "the same objects as the tutorial's finished file")
    if sorted(outline) != sorted(wanted):
        print("outline:", outline)

    # on its own, as the tutorial runs it after every step: Run
    check(not backend.modified and backend.runName == "Main.qml",
          "everything is saved; the project's Main.qml is what Run starts")
    run_problems = []
    backend.runProblem.connect(run_problems.append)
    QMetaObject.invokeMethod(page.findChild(QObject, "runAction"), "trigger")
    wait_until(lambda: backend.running, lambda: QTimer.singleShot(4000, lambda: ran(run_problems)),
               what="Run starts the application")


def ran(run_problems):
    check(backend.running and not run_problems and backend.runOutput == "$ qml6 Main.qml",
          f"it runs on its own without a complaint {run_problems} {backend.runOutput!r}")
    backend.stopRun()
    wait_until(lambda: not backend.running, finish, what="Stop ends it")


def finish():
    # the example in the source tree is this application
    with open(f"{REPO}/examples/tasks/Main.qml", encoding="utf-8") as fh:
        check(fh.read() == backend.sourceText,
              f"examples/tasks/Main.qml is what was built (if it should change: copy {MAIN} there)")
    app.quit()


QTimer.singleShot(800, create_project)
