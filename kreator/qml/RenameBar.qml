import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// Rename the symbol under the cursor with the language server (F2).
QQC2.ToolBar {
    id: bar

    required property Item editor
    required property Item pane

    property string oldName: ""
    property int startPos: 0          // where the rename was started
    property string error: ""

    position: QQC2.ToolBar.Footer
    visible: false

    function open(name, pos) {
        oldName = name
        startPos = pos
        error = ""
        field.text = name
        visible = true
        field.forceActiveFocus()
        field.selectAll()
    }
    function close() {
        visible = false
        editor.forceActiveFocus()
    }
    function accept() {
        const name = field.text.trim()
        if (!/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(name)) {
            error = qsTr("Not a valid name")
            return
        }
        if (name === oldName) {
            close()
            return
        }
        visible = false
        pane.requestRename(startPos, name)
    }

    RowLayout {
        anchors.fill: parent
        spacing: Kirigami.Units.smallSpacing

        QQC2.Label {
            text: qsTr("Rename “%1” to:").arg(bar.oldName)
        }
        QQC2.TextField {
            id: field
            Layout.preferredWidth: Kirigami.Units.gridUnit * 14
            font.family: bar.pane.editorFont.family
            Accessible.name: qsTr("New name")
            onTextChanged: bar.error = ""
            Keys.onPressed: event => {
                if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    bar.accept()
                    event.accepted = true
                } else if (event.key === Qt.Key_Escape) {
                    bar.close()
                    event.accepted = true
                }
            }
        }
        QQC2.Button {
            text: qsTr("Rename")
            icon.name: "edit-rename"
            enabled: field.text.trim() !== ""
            onClicked: bar.accept()
        }
        QQC2.Label {
            Layout.fillWidth: true
            text: bar.error
            color: Kirigami.Theme.negativeTextColor
            elide: Text.ElideRight
        }
        QQC2.ToolButton {
            icon.name: "dialog-close"
            text: qsTr("Close")
            display: QQC2.AbstractButton.IconOnly
            onClicked: bar.close()
            QQC2.ToolTip.text: qsTr("Close (Esc)")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
    }
}
