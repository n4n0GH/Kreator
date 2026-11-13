import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import QtQuick.Layouts
import org.kde.kitemmodels as KItemModels
import QtCore

Kirigami.ApplicationWindow {
    id: root
    property int remaining: 0
    property string filter: "all"

    title: qsTr("Tasks")
    width: Kirigami.Units.gridUnit * 24
    height: Kirigami.Units.gridUnit * 28
    Component.onCompleted: {
        load()
        recount()
    }
    onFilterChanged: visibleTasks.invalidateFilter()

    function addTask(title: string): void {
        const trimmed = title.trim()
        if (trimmed.length > 0) {
            tasksModel.append({ title: trimmed, done: false })
        }
    }

    function deleteTask(row: int): void {
        // Keep a copy so the deletion can be undone.
        const task = { title: tasksModel.get(row).title, done: tasksModel.get(row).done }
        tasksModel.remove(row)
        showPassiveNotification("“" + task.title + "” deleted", "long", "Undo",
            () => tasksModel.insert(row, task))
    }

    function recount(): void {
        let open = 0
        for (let i = 0; i < tasksModel.count; i++) {
            if (!tasksModel.get(i).done) {
                open++
            }
        }
        remaining = open
    }

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

    pageStack.initialPage: Kirigami.ScrollablePage {
        id: page

        title: qsTr("Tasks")
        actions: [
            Kirigami.Action {
                id: action
                icon.name: "view-filter"
                text: qsTr("Show")
                Kirigami.Action {
                    id: action2
                    text: qsTr("All Tasks")
                    checkable: true
                    autoExclusive: true
                    checked: root.filter === "all"
                    onTriggered: root.filter = "all"
                }
                Kirigami.Action {
                    id: action3
                    text: qsTr("Active")
                    checkable: true
                    autoExclusive: true
                    checked: root.filter === "active"
                    onTriggered: root.filter = "active"
                }
                Kirigami.Action {
                    id: action4
                    text: qsTr("Completed")
                    checkable: true
                    autoExclusive: true
                    checked: root.filter === "completed"
                    onTriggered: root.filter = "completed"
                }
            },
            Kirigami.Action {
                id: action5
                icon.name: "edit-clear-all"
                text: qsTr("Clear Completed")
                enabled: root.remaining < tasksModel.count
                onTriggered: root.clearCompleted()
            }
        ]
        header: QQC2.ToolBar {
            id: toolBar
            contentItem: Kirigami.ActionTextField {
                id: newTaskField
                placeholderText: qsTr("Add a task")
                onAccepted: { root.addTask(text); clear() }
                rightActions: Kirigami.Action {
                    icon.name: "list-add"
                    text: qsTr("Add Task")
                    enabled: newTaskField.text.trim().length > 0
                    onTriggered: newTaskField.accepted()
                }
            }
        }
        footer: QQC2.ToolBar {
            id: toolBar2
            visible: tasksModel.count > 0
            contentItem: QQC2.Label {
                id: label2
                text: root.remaining === 1 ? qsTr("1 task left") : qsTr("%1 tasks left").arg(root.remaining)
                leftPadding: Kirigami.Units.largeSpacing
            }
        }
        ListView {
            id: tasksView
            model: visibleTasks
            currentIndex: -1
            delegate: QQC2.ItemDelegate {
                id: row
                required property int index
                required property string title
                required property bool done
                width: ListView.view.width
                onClicked: tasksModel.setProperty(root.sourceRow(index), "done", !done)
                contentItem: RowLayout {
                    id: rowLayout
                    spacing: Kirigami.Units.smallSpacing
                    QQC2.CheckBox {
                        id: checkBox
                        checked: row.done
                        onToggled: tasksModel.setProperty(root.sourceRow(row.index), "done", checked)
                    }
                    QQC2.Label {
                        id: label
                        text: row.title
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        font.strikeout: row.done
                        opacity: row.done ? 0.6 : 1
                    }
                    QQC2.ToolButton {
                        id: toolButton
                        icon.name: "edit-delete"
                        text: qsTr("Delete")
                        display: QQC2.AbstractButton.IconOnly
                        QQC2.ToolTip.text: text
                        QQC2.ToolTip.visible: hovered
                        QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                        onClicked: root.deleteTask(root.sourceRow(row.index))
                    }
                }
            }
            Kirigami.PlaceholderMessage {
                id: placeholderMessage
                anchors.centerIn: parent
                width: parent.width - Kirigami.Units.gridUnit * 4
                icon.name: "checkmark"
                text: tasksModel.count === 0 ? qsTr("No tasks") : qsTr("Nothing to show")
                explanation: tasksModel.count === 0 ? qsTr("Type in the field above and press Enter to add one.") : qsTr("No tasks match the current filter.")
                visible: tasksView.count === 0
            }
        }
    }
    ListModel {
        id: tasksModel
    }
    Connections {
        id: connections
        target: tasksModel
        function onCountChanged() {
            root.recount()
            root.save()
        }
        function onDataChanged() {
            root.recount()
            visibleTasks.invalidateFilter()
            root.save()
        }
    }
    KItemModels.KSortFilterProxyModel {
        id: visibleTasks
        sourceModel: tasksModel
        filterRowCallback: (row, parent) => { const done = tasksModel.get(row).done; return root.filter === "all" || (root.filter === "active" && !done) || (root.filter === "completed" && done) }
    }
    Settings {
        id: settings
        property string tasks: "[]"
        location: StandardPaths.writableLocation(StandardPaths.GenericConfigLocation) + "/tasks-tutorial.ini"
    }
}
