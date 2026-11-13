import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import QtQuick.Dialogs
import org.kde.kirigami as Kirigami

// New Project…: a name, where to create it and what to start with. Creates
// the folder with its first user interface file and opens both (see
// Backend.createProject).
Kirigami.Dialog {
    id: dialog
    objectName: "newProjectDialog"

    // the project was created and is open
    signal created()

    readonly property string projectName: nameField.text.trim()
    readonly property string location: locationField.text.trim()
    readonly property string template: templateBox.currentValue || "kirigami-app"
    // why it can't be created ("" if it can); asked again whenever the dialog
    // opens: folders may have changed meanwhile
    property string problem: Backend.projectProblem(projectName, location)
    function checkProblem() {
        problem = Backend.projectProblem(projectName, location)
    }
    onProjectNameChanged: checkProblem()
    onLocationChanged: checkProblem()
    onOpened: checkProblem()
    readonly property string filePath: Backend.projectFilePath(projectName, location, template)

    function show() {
        nameField.text = ""
        locationField.text = Backend.defaultProjectLocation()
        templateBox.currentIndex = 0
        open()
        nameField.forceActiveFocus()
    }

    function create() {
        if (problem !== "")
            return
        if (Backend.createProject(projectName, location, template)) {
            close()
            created()
        }
    }

    title: qsTr("New Project")
    preferredWidth: Kirigami.Units.gridUnit * 30
    padding: Kirigami.Units.largeSpacing
    standardButtons: Kirigami.Dialog.NoButton
    customFooterActions: [
        Kirigami.Action {
            id: createAction
            objectName: "createProjectAction"
            text: qsTr("Create")
            icon.name: "folder-new"
            enabled: dialog.problem === ""
            onTriggered: dialog.create()
        },
        Kirigami.Action {
            text: qsTr("Cancel")
            icon.name: "dialog-cancel"
            onTriggered: dialog.close()
        }
    ]

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing

        Kirigami.FormLayout {
            Layout.fillWidth: true

            QQC2.TextField {
                id: nameField
                objectName: "projectNameField"
                Kirigami.FormData.label: qsTr("Name:")
                Layout.fillWidth: true
                placeholderText: qsTr("My Application")
                onAccepted: dialog.create()
            }
            RowLayout {
                Kirigami.FormData.label: qsTr("Create in:")
                Kirigami.FormData.buddyFor: locationField
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                QQC2.TextField {
                    id: locationField
                    objectName: "projectLocationField"
                    Layout.fillWidth: true
                    Accessible.name: qsTr("Folder to create the project in")
                    onAccepted: dialog.create()
                }
                QQC2.Button {
                    icon.name: "document-open-folder"
                    text: qsTr("Choose Folder…")
                    display: QQC2.AbstractButton.IconOnly
                    onClicked: {
                        if (dialog.location !== "")
                            locationDialog.currentFolder = "file://" + dialog.location
                        locationDialog.open()
                    }
                    QQC2.ToolTip.text: text
                    QQC2.ToolTip.visible: hovered
                    QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                }
            }
            QQC2.ComboBox {
                id: templateBox
                objectName: "projectTemplateBox"
                Kirigami.FormData.label: qsTr("Start with:")
                Layout.fillWidth: true
                model: Backend.projectTemplates()
                textRole: "title"
                valueRole: "key"
            }
            QQC2.Label {
                Layout.fillWidth: true
                visible: text !== ""
                text: templateBox.currentIndex >= 0 ? templateBox.model[templateBox.currentIndex].description : ""
                wrapMode: Text.WordWrap
                font: Kirigami.Theme.smallFont
                opacity: 0.7
            }
        }

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            // (not while nothing is typed yet)
            visible: dialog.problem !== "" && dialog.projectName !== ""
            type: Kirigami.MessageType.Error
            text: dialog.problem
        }

        QQC2.Label {
            Layout.fillWidth: true
            visible: dialog.problem === "" && dialog.filePath !== ""
            text: qsTr("Creates %1").arg(dialog.filePath)
            wrapMode: Text.WrapAnywhere
            font: Kirigami.Theme.smallFont
            opacity: 0.7
        }
    }

    FolderDialog {
        id: locationDialog
        title: qsTr("Create Project In")
        onAccepted: locationField.text = decodeURIComponent(selectedFolder.toString().replace(/^file:\/\//, ""))
    }
}
