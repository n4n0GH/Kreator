import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// The open folder's .qml and .ui files. Clicking one switches to it right away;
// every file keeps its unsaved edits while others are shown (marked with •).
// Without a folder it offers to open one or to create a project. This is the first tab of the
// sidebar (SidePanel), whose tab shows the folder's name; Close Folder is in
// the main menu.
ColumnLayout {
    id: panel
    spacing: 0

    Kirigami.Theme.colorSet: Kirigami.Theme.View
    Kirigami.Theme.inherit: false

    Kirigami.SearchField {
        id: filter
        visible: Backend.projectPath !== ""
        Layout.fillWidth: true
        Layout.margins: Kirigami.Units.smallSpacing
        placeholderText: qsTr("Filter files…")
        focusSequences: []
        onTextChanged: Backend.setProjectFilter(text)
        Keys.onPressed: event => {
            if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && files.count > 0) {
                const r = files.itemAtIndex(0)
                if (r && !r.isDir)
                    applicationWindow().switchFile(r.key)
                event.accepted = true
            } else if (event.key === Qt.Key_Down) {
                files.forceActiveFocus()
                files.currentIndex = 0
                event.accepted = true
            }
        }
    }

    Kirigami.Separator {
        visible: Backend.projectPath !== ""
        Layout.fillWidth: true
    }

    // no folder: open one, or one of the recent ones
    QQC2.ScrollView {
        visible: Backend.projectPath === ""
        Layout.fillWidth: true
        Layout.fillHeight: true
        background: Rectangle {
            color: Kirigami.Theme.backgroundColor
        }
        ListView {
            id: recentList
            clip: true
            model: Backend.recentFolders
            header: ColumnLayout {
                width: ListView.view.width
                spacing: Kirigami.Units.largeSpacing
                Kirigami.PlaceholderMessage {
                    Layout.fillWidth: true
                    Layout.topMargin: Kirigami.Units.gridUnit * 2
                    Layout.leftMargin: Kirigami.Units.largeSpacing
                    Layout.rightMargin: Kirigami.Units.largeSpacing
                    icon.name: "folder-open"
                    text: qsTr("No folder open")
                    explanation: qsTr("Open a folder to work with all of its .qml and .ui files")
                    helpfulAction: Kirigami.Action {
                        icon.name: "folder-open"
                        text: qsTr("Open Folder…")
                        onTriggered: applicationWindow().openFolder()
                    }
                }
                QQC2.Button {
                    Layout.alignment: Qt.AlignHCenter
                    icon.name: "folder-new"
                    text: qsTr("New Project…")
                    onClicked: applicationWindow().newProject()
                }
                Kirigami.Heading {
                    visible: recentList.count > 0
                    Layout.leftMargin: Kirigami.Units.largeSpacing
                    Layout.topMargin: Kirigami.Units.largeSpacing
                    level: 5
                    text: qsTr("Recent Folders")
                    opacity: 0.7
                }
            }
            delegate: QQC2.ItemDelegate {
                required property string modelData
                width: ListView.view.width
                icon.name: "folder"
                text: modelData.split("/").filter(x => x !== "").pop() || modelData
                onClicked: Backend.openFolder(modelData)
                QQC2.ToolTip.text: modelData
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
        }
    }

    QQC2.ScrollView {
        visible: Backend.projectPath !== ""
        Layout.fillWidth: true
        Layout.fillHeight: true
        background: Rectangle {
            color: Kirigami.Theme.backgroundColor
        }

        ListView {
            id: files
            clip: true
            model: Backend.projectFiles
            keyNavigationEnabled: true
            currentIndex: -1
            Keys.onReturnPressed: if (currentItem) currentItem.activate()
            Keys.onEnterPressed: if (currentItem) currentItem.activate()

            delegate: QQC2.ItemDelegate {
                id: row

                required property int index
                required property string key
                required property string name
                required property string relPath
                required property int depth
                required property bool isDir
                required property bool expanded
                required property string kind
                required property bool modified
                required property bool current
                required property bool open
                required property string detail

                function activate() {
                    if (isDir)
                        Backend.toggleProjectDir(key)
                    else
                        applicationWindow().switchFile(key)
                }

                width: ListView.view.width
                highlighted: current || ListView.isCurrentItem
                leftPadding: Kirigami.Units.smallSpacing + depth * Kirigami.Units.gridUnit
                topPadding: Kirigami.Units.smallSpacing / 2
                bottomPadding: Kirigami.Units.smallSpacing / 2
                onClicked: activate()
                Accessible.name: name + (modified ? " " + qsTr("(modified)") : "")

                QQC2.ToolTip.text: relPath + (modified ? "\n" + qsTr("Unsaved changes") : "")
                QQC2.ToolTip.visible: hovered && !isDir
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay * 2

                contentItem: RowLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon {
                        source: row.isDir ? (row.expanded ? "go-down-symbolic" : "go-next-symbolic") : ""
                        implicitWidth: Kirigami.Units.iconSizes.small
                        implicitHeight: Kirigami.Units.iconSizes.small
                        opacity: 0.7
                    }
                    Kirigami.Icon {
                        source: row.isDir ? "folder" : (row.kind === "ui" ? "window" : "text-x-qml")
                        implicitWidth: Kirigami.Units.iconSizes.small
                        implicitHeight: Kirigami.Units.iconSizes.small
                    }
                    QQC2.Label {
                        Layout.fillWidth: row.detail === ""
                        text: row.name
                        elide: Text.ElideRight
                        font.bold: row.current
                        font.italic: row.open && !row.current
                        color: row.highlighted ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor
                    }
                    QQC2.Label {
                        visible: row.detail !== ""
                        Layout.fillWidth: true
                        text: row.detail
                        elide: Text.ElideMiddle
                        font: Kirigami.Theme.smallFont
                        color: row.highlighted ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.disabledTextColor
                    }
                    // unsaved changes, kept while other files are shown
                    Rectangle {
                        visible: row.modified
                        implicitWidth: Kirigami.Units.smallSpacing * 1.5
                        implicitHeight: implicitWidth
                        radius: width / 2
                        color: row.highlighted ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.neutralTextColor
                    }
                }
            }

            Kirigami.PlaceholderMessage {
                anchors.centerIn: parent
                width: parent.width - Kirigami.Units.largeSpacing * 4
                visible: files.count === 0
                icon.name: filter.text !== "" ? "search" : "folder-open"
                text: filter.text !== "" ? qsTr("No matching files") : qsTr("No .qml or .ui files in this folder")
            }
        }
    }
}
