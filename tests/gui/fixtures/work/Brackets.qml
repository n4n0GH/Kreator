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
            onTriggered: console.log("a } tricky ( string") // comment with ) and }
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
