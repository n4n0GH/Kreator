import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: root
    signal saved(string path)

    function save() {
        backendDialog.open()
        root.saved("x")
    }

    QQC2.Button {
        text: qsTr("Save")
        onClicked: save()
    }
    QQC2.CheckBox {
        id: advanced
        text: "Advanced"
    }
    QQC2.TextField {
        id: field
        enabled: advanced.checked
        anchors.top: parent.top
        width: advanced.width
        onAccepted: {
            const t = field.text
            status.text = t
        }
    }
    QQC2.Label { id: status }
    QQC2.Dialog {
        id: backendDialog
        onAccepted: status.text = "ok"
    }
    Timer {
        id: timer
        Component.onCompleted: timer.triggered.connect(save)
    }
    Connections {
        target: Backend
        function onDocumentChanged() { status.text = "doc" }
        function onNotify(msg) { console.log(msg) }
    }
    function lonely() { console.log("nobody calls me") }
    property int leftover: 3
}
