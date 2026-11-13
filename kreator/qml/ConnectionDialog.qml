import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// A Qt Designer form's signal/slot connection: new or edited. The signals
// and slots come from the widgets' classes; a slot list only has those that
// can take the chosen signal. Both fields also take a signature typed in
// (e.g. a slot of the form's class that's only in the C++ code).
Kirigami.Dialog {
    id: dialog
    objectName: "connectionDialog"

    // -1: a new connection
    property int index: -1
    property var connectables: []

    title: index < 0 ? qsTr("New Connection") : qsTr("Edit Connection")
    padding: Kirigami.Units.largeSpacing
    preferredWidth: Kirigami.Units.gridUnit * 26
    standardButtons: QQC2.Dialog.Ok | QQC2.Dialog.Cancel

    function openFor(idx, sender, signal, receiver, slot) {
        index = idx
        connectables = Backend.uiConnectables()
        const names = connectables.map(c => c.name)
        senderBox.model = connectables
        receiverBox.model = connectables
        senderBox.currentIndex = Math.max(0, names.indexOf(sender))
        receiverBox.currentIndex = receiver ? names.indexOf(receiver) : -1
        refreshSignals(signal || "")
        refreshSlots(slot || "")
        open()
        if (receiverBox.currentIndex < 0)
            receiverBox.forceActiveFocus()
        else
            signalBox.forceActiveFocus()
    }

    readonly property string senderName: senderBox.currentIndex >= 0 ? connectables[senderBox.currentIndex].name : ""
    readonly property string receiverName: receiverBox.currentIndex >= 0 ? connectables[receiverBox.currentIndex].name : ""
    readonly property string signalText: signalBox.editText.trim()
    readonly property string slotText: slotBox.editText.trim()
    readonly property bool valid: senderName !== "" && receiverName !== ""
                                  && /^\w+\([^()]*\)$/.test(signalText) && /^\w+\([^()]*\)$/.test(slotText)

    function refreshSignals(keep) {
        const list = senderName ? Backend.uiSignals(senderName) : []
        signalBox.model = list
        const i = list.indexOf(keep)
        signalBox.currentIndex = i
        signalBox.editText = keep
    }
    function refreshSlots(keep) {
        const list = receiverName ? Backend.uiSlots(receiverName, signalText) : []
        slotBox.model = list
        const i = list.indexOf(keep)
        slotBox.currentIndex = i
        slotBox.editText = keep
    }

    Component.onCompleted: {
        const ok = standardButton(QQC2.Dialog.Ok)
        ok.text = Qt.binding(() => dialog.index < 0 ? qsTr("Connect") : qsTr("Apply"))
        ok.icon.name = "format-connect-node"
        ok.enabled = Qt.binding(() => dialog.valid)
    }

    onAccepted: {
        if (index < 0)
            Backend.addConnection(senderName, signalText, receiverName, slotText)
        else
            Backend.updateConnection(index, senderName, signalText, receiverName, slotText)
    }

    Kirigami.FormLayout {
        QQC2.ComboBox {
            id: senderBox
            objectName: "connSender"
            Kirigami.FormData.label: qsTr("Sender:")
            Layout.fillWidth: true
            textRole: "name"
            displayText: currentIndex >= 0 ? qsTr("%1 (%2)").arg(currentText).arg(dialog.connectables[currentIndex].type) : ""
            onActivated: dialog.refreshSignals(signalBox.editText)
        }
        QQC2.ComboBox {
            id: signalBox
            objectName: "connSignal"
            Kirigami.FormData.label: qsTr("Signal:")
            Layout.fillWidth: true
            editable: true
            font.family: Kirigami.Theme.fixedWidthFont.family
            onActivated: dialog.refreshSlots(slotBox.editText)
            onAccepted: dialog.refreshSlots(slotBox.editText)
        }
        QQC2.ComboBox {
            id: receiverBox
            objectName: "connReceiver"
            Kirigami.FormData.label: qsTr("Receiver:")
            Layout.fillWidth: true
            textRole: "name"
            displayText: currentIndex >= 0 ? qsTr("%1 (%2)").arg(currentText).arg(dialog.connectables[currentIndex].type)
                                           : qsTr("Choose a widget…")
            onActivated: dialog.refreshSlots(slotBox.editText)
        }
        QQC2.ComboBox {
            id: slotBox
            objectName: "connSlot"
            Kirigami.FormData.label: qsTr("Slot:")
            Layout.fillWidth: true
            editable: true
            font.family: Kirigami.Theme.fixedWidthFont.family
        }
        QQC2.Label {
            Layout.fillWidth: true
            Layout.maximumWidth: Kirigami.Units.gridUnit * 22
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: slotBox.count === 0 && dialog.receiverName !== ""
                  ? qsTr("No slot of %1 can take this signal. You can type one in.").arg(dialog.receiverName)
                  : qsTr("Only slots that can take the signal's arguments are listed.")
        }
    }
}
