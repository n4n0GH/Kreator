import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

QQC2.ScrollView {
    id: view

    property Kirigami.Action openAction

    contentWidth: availableWidth

    Kirigami.Theme.colorSet: Kirigami.Theme.View
    Kirigami.Theme.inherit: false
    background: Rectangle {
        color: Kirigami.Theme.backgroundColor
    }

    ColumnLayout {
        width: view.availableWidth
        spacing: Kirigami.Units.largeSpacing * 2

        Item {
            Layout.preferredHeight: Kirigami.Units.gridUnit * 3
        }

        Kirigami.PlaceholderMessage {
            Layout.alignment: Qt.AlignHCenter
            Layout.maximumWidth: Kirigami.Units.gridUnit * 28
            Layout.fillWidth: true
            icon.name: "document-preview"
            text: qsTr("Open a User Interface File")
            explanation: qsTr("View and edit Qt Quick and Kirigami (.qml) files or Qt Designer forms (.ui). You can also drop a file here.")
            helpfulAction: view.openAction
        }

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: Kirigami.Units.largeSpacing

            QQC2.Button {
                objectName: "newProjectButton"
                text: qsTr("New Project…")
                icon.name: "folder-new"
                onClicked: applicationWindow().newProject()
                QQC2.ToolTip.text: qsTr("Create a folder with a first user interface file, and start designing")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.Button {
                text: qsTr("Open Folder…")
                icon.name: "folder-open"
                onClicked: applicationWindow().openFolder()
                QQC2.ToolTip.text: qsTr("Work with all .qml and .ui files of a project and switch between them")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
        }

        Kirigami.Heading {
            Layout.alignment: Qt.AlignHCenter
            level: 4
            text: qsTr("Or start a single file from a template")
        }

        Flow {
            Layout.alignment: Qt.AlignHCenter
            Layout.maximumWidth: Kirigami.Units.gridUnit * 36
            Layout.preferredWidth: childrenRect.width
            spacing: Kirigami.Units.largeSpacing

            Repeater {
                model: [
                    { key: "kirigami-app", title: qsTr("Kirigami Application"), icon: "kde", sub: qsTr("Window with drawer and page") },
                    { key: "kirigami-page", title: qsTr("Kirigami Page"), icon: "document-new", sub: qsTr("Scrollable page with a form") },
                    { key: "qtquick", title: qsTr("Qt Quick Application"), icon: "text-x-qml", sub: qsTr("Plain Qt Quick Controls") },
                    { key: "widgets-form", title: qsTr("Qt Widgets Form"), icon: "window", sub: qsTr("Qt Designer .ui form") }
                ]
                delegate: Kirigami.AbstractCard {
                    id: card
                    required property var modelData
                    width: Kirigami.Units.gridUnit * 13
                    showClickFeedback: true
                    onClicked: applicationWindow().newDocument(modelData.key)
                    Accessible.name: modelData.title
                    contentItem: RowLayout {
                        spacing: Kirigami.Units.largeSpacing
                        Kirigami.Icon {
                            source: card.modelData.icon
                            implicitWidth: Kirigami.Units.iconSizes.medium
                            implicitHeight: Kirigami.Units.iconSizes.medium
                        }
                        ColumnLayout {
                            spacing: 0
                            Layout.fillWidth: true
                            QQC2.Label {
                                Layout.fillWidth: true
                                text: card.modelData.title
                                font.bold: true
                                elide: Text.ElideRight
                            }
                            QQC2.Label {
                                Layout.fillWidth: true
                                text: card.modelData.sub
                                elide: Text.ElideRight
                                opacity: 0.7
                                font: Kirigami.Theme.smallFont
                            }
                        }
                    }
                }
            }
        }

        ColumnLayout {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: Kirigami.Units.gridUnit * 28
            Layout.maximumWidth: view.availableWidth - Kirigami.Units.largeSpacing * 2
            visible: Backend.recentFiles.length > 0 || Backend.recentFolders.length > 0
            spacing: 0

            Kirigami.ListSectionHeader {
                Layout.fillWidth: true
                visible: Backend.recentFolders.length > 0
                text: qsTr("Recent Folders")
            }
            Repeater {
                model: Backend.recentFolders
                delegate: QQC2.ItemDelegate {
                    required property string modelData
                    Layout.fillWidth: true
                    icon.name: "folder"
                    text: modelData.split("/").pop()
                    QQC2.ToolTip.text: modelData
                    QQC2.ToolTip.visible: hovered
                    QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                    onClicked: Backend.openFolder(modelData)
                }
            }
            Kirigami.ListSectionHeader {
                Layout.fillWidth: true
                text: qsTr("Recent Files")
            }
            Repeater {
                model: Backend.recentFiles
                delegate: QQC2.ItemDelegate {
                    required property string modelData
                    Layout.fillWidth: true
                    icon.name: modelData.endsWith(".ui") ? "window" : "text-x-qml"
                    text: modelData.split("/").pop()
                    QQC2.ToolTip.text: modelData
                    QQC2.ToolTip.visible: hovered
                    QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                    onClicked: applicationWindow().switchFile(modelData)
                }
            }
        }

        Item {
            Layout.preferredHeight: Kirigami.Units.gridUnit
        }
    }
}
