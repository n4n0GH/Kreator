// Example Kirigami page with a few guideline issues to try QViewer's checks.
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page

    title: i18n("Settings")
    actions: [
        Kirigami.Action {
            icon.name: "document-save"
            text: i18n("apply changes")
            onTriggered: console.log("apply")
        }
    ]

    ColumnLayout {
        spacing: 10

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            type: Kirigami.MessageType.Information
            text: i18n("Changes are applied when you press Apply.")
            visible: true
        }

        Kirigami.FormLayout {
            Layout.fillWidth: true

            QQC2.TextField {
                id: nameField
                Kirigami.FormData.label: i18n("Name")
                placeholderText: "Your name"
            }
            QQC2.ComboBox {
                id: themeBox
                Kirigami.FormData.label: i18n("Theme:")
                model: [i18n("Breeze"), i18n("Breeze Dark")]
            }
            QQC2.Switch {
                id: notifySwitch
                Kirigami.FormData.label: i18n("Notifications:")
                text: i18n("Show notifications")
            }
        }

        Text {
            text: i18n("Some plain text")
            color: "#ff0000"
            font.pixelSize: 14
        }

        QQC2.Label {
            id: label0
            text: i18n("Row 0")
        }
        QQC2.Label {
            id: label1
            text: i18n("Row 1")
        }
        QQC2.Label {
            id: label2
            text: i18n("Row 2")
        }
        QQC2.Label {
            id: label3
            text: i18n("Row 3")
        }
        QQC2.Label {
            id: label4
            text: i18n("Row 4")
        }
        QQC2.Label {
            id: label5
            text: i18n("Row 5")
        }
        QQC2.Label {
            id: label6
            text: i18n("Row 6")
        }
        QQC2.Label {
            id: label7
            text: i18n("Row 7")
        }
        QQC2.Label {
            id: label8
            text: i18n("Row 8")
        }
        QQC2.Label {
            id: label9
            text: i18n("Row 9")
        }
        QQC2.Label {
            id: label10
            text: i18n("Row 10")
        }
        QQC2.Label {
            id: label11
            text: i18n("Row 11")
        }
        QQC2.Label {
            id: label12
            text: i18n("Row 12")
        }
        QQC2.Label {
            id: label13
            text: i18n("Row 13")
        }
        QQC2.Label {
            id: label14
            text: i18n("Row 14")
        }
        QQC2.Label {
            id: label15
            text: i18n("Row 15")
        }
        QQC2.Label {
            id: label16
            text: i18n("Row 16")
        }
        QQC2.Label {
            id: label17
            text: i18n("Row 17")
        }
        QQC2.Label {
            id: label18
            text: i18n("Row 18")
        }
        QQC2.Label {
            id: label19
            text: i18n("Row 19")
        }
        QQC2.Label {
            id: label20
            text: i18n("Row 20")
        }
        QQC2.Label {
            id: label21
            text: i18n("Row 21")
        }
        QQC2.Label {
            id: label22
            text: i18n("Row 22")
        }
        QQC2.Label {
            id: label23
            text: i18n("Row 23")
        }
        QQC2.Label {
            id: label24
            text: i18n("Row 24")
        }
        QQC2.Label {
            id: label25
            text: i18n("Row 25")
        }
        QQC2.Label {
            id: label26
            text: i18n("Row 26")
        }
        QQC2.Label {
            id: label27
            text: i18n("Row 27")
        }
        QQC2.Label {
            id: label28
            text: i18n("Row 28")
        }
        QQC2.Label {
            id: label29
            text: i18n("Row 29")
        }
        QQC2.Label {
            id: label30
            text: i18n("Row 30")
        }
        QQC2.Label {
            id: label31
            text: i18n("Row 31")
        }
        QQC2.Label {
            id: label32
            text: i18n("Row 32")
        }
        QQC2.Label {
            id: label33
            text: i18n("Row 33")
        }
        QQC2.Label {
            id: label34
            text: i18n("Row 34")
        }
        QQC2.Label {
            id: label35
            text: i18n("Row 35")
        }
        QQC2.Label {
            id: label36
            text: i18n("Row 36")
        }
        QQC2.Label {
            id: label37
            text: i18n("Row 37")
        }
        QQC2.Label {
            id: label38
            text: i18n("Row 38")
        }
        QQC2.Label {
            id: label39
            text: i18n("Row 39")
        }
        QQC2.Button {
            icon.name: "configure"
            text: i18n("Configure...")
            onClicked: {
                // multi-line handler
                console.log("configure")
                nameField.text = ""
            }
        }
    }
}
