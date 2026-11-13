import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// What the application started with Run printed: its console.log() output
// and the QML engine's warnings and errors.
Kirigami.Dialog {
    id: dialog
    objectName: "runOutputDialog"

    title: Backend.running ? qsTr("Output of %1 (running)").arg(Backend.runName) : qsTr("Run Output")
    preferredWidth: Kirigami.Units.gridUnit * 44
    preferredHeight: Kirigami.Units.gridUnit * 24
    padding: 0
    standardButtons: Kirigami.Dialog.NoButton
    customFooterActions: [
        Kirigami.Action {
            text: Backend.running ? qsTr("Stop") : qsTr("Run Again")
            icon.name: Backend.running ? "media-playback-stop" : "media-playback-start"
            enabled: Backend.running || Backend.canRun
            onTriggered: Backend.running ? Backend.stopRun() : applicationWindow().runApplication()
        },
        Kirigami.Action {
            text: qsTr("Copy")
            icon.name: "edit-copy"
            enabled: output.text !== ""
            onTriggered: {
                output.selectAll()
                output.copy()
                output.deselect()
            }
        },
        Kirigami.Action {
            text: qsTr("Close")
            icon.name: "dialog-close"
            onTriggered: dialog.close()
        }
    ]

    QQC2.ScrollView {
        id: scroll

        QQC2.TextArea {
            id: output
            objectName: "runOutputText"
            readOnly: true
            text: Backend.runOutput
            wrapMode: TextEdit.Wrap
            font.family: Kirigami.Theme.fixedWidthFont.family
            background: Rectangle {
                Kirigami.Theme.colorSet: Kirigami.Theme.View
                Kirigami.Theme.inherit: false
                color: Kirigami.Theme.backgroundColor
            }
            Accessible.name: qsTr("Output of the application")
            // new output stays in view
            onTextChanged: cursorPosition = length
        }
    }
}
