import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import QtQuick.Dialogs
import org.kde.kirigami as Kirigami

Item {
    id: row

    required property string name
    required property string kind
    required property string value
    required property bool isSet
    required property string section
    required property string liveValue
    required property var enumKeys
    required property string typeName
    required property string raw

    property bool asExpression: false

    readonly property string editKind: asExpression ? "expression" : kind

    implicitHeight: layout.implicitHeight + Kirigami.Units.smallSpacing * 2

    function commit(k, v) {
        Backend.setProperty(name, k, v)
    }

    Rectangle {
        anchors.fill: parent
        color: Kirigami.Theme.highlightColor
        opacity: hover.hovered ? 0.08 : 0
    }
    HoverHandler {
        id: hover
    }

    RowLayout {
        id: layout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: Kirigami.Units.largeSpacing
        anchors.rightMargin: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        ColumnLayout {
            Layout.preferredWidth: row.width * 0.38
            Layout.maximumWidth: row.width * 0.38
            Layout.alignment: Qt.AlignTop
            Layout.topMargin: Kirigami.Units.smallSpacing
            spacing: 0

            QQC2.Label {
                Layout.fillWidth: true
                text: row.name
                elide: Text.ElideMiddle
                font.bold: row.isSet && row.section !== "All properties"
                opacity: row.isSet ? 1 : 0.6
                QQC2.ToolTip.text: row.name + (row.typeName ? " (" + row.typeName + ")" : "")
                QQC2.ToolTip.visible: nameHover.hovered && truncated
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                HoverHandler {
                    id: nameHover
                }
            }
            QQC2.Label {
                Layout.fillWidth: true
                visible: text !== ""
                text: row.typeName !== "" ? row.typeName : (row.isSet && row.liveValue !== "" && row.liveValue !== row.value ? "= " + row.liveValue : "")
                elide: Text.ElideRight
                font: Kirigami.Theme.smallFont
                color: Kirigami.Theme.disabledTextColor
            }
        }

        Loader {
            id: editorLoader
            Layout.fillWidth: true
            sourceComponent: {
                switch (row.editKind) {
                case "bool": return boolEditor
                case "enum": return row.enumKeys.length > 0 ? enumEditor : textEditor
                case "color": return colorEditor
                case "script": return scriptEditor
                case "object":
                case "list":
                case "readonly": return readonlyEditor
                default: return textEditor
                }
            }
        }

        QQC2.ToolButton {
            id: menuButton
            Layout.alignment: Qt.AlignTop
            icon.name: "overflow-menu"
            text: qsTr("More Options")
            display: QQC2.AbstractButton.IconOnly
            visible: row.kind !== "readonly"
            onClicked: menu.popup(menuButton, 0, menuButton.height)
            QQC2.ToolTip.text: text
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay

            QQC2.Menu {
                id: menu
                QQC2.MenuItem {
                    text: row.asExpression ? qsTr("Edit as Value") : qsTr("Edit as Expression")
                    icon.name: "code-context"
                    visible: Backend.docKind === "qml" && row.kind !== "script" && row.kind !== "object" && row.kind !== "list"
                    height: visible ? implicitHeight : 0
                    onTriggered: row.asExpression = !row.asExpression
                }
                QQC2.MenuItem {
                    text: qsTr("Copy Value")
                    icon.name: "edit-copy"
                    onTriggered: {
                        clipHelper.text = row.raw !== "" ? row.raw : row.value
                        clipHelper.selectAll()
                        clipHelper.copy()
                    }
                }
                QQC2.MenuItem {
                    text: qsTr("Remove")
                    icon.name: "edit-delete-remove"
                    enabled: row.isSet
                    onTriggered: Backend.removeProperty(row.name)
                }
            }
        }
    }

    TextEdit {
        id: clipHelper
        visible: false
    }

    // ------------------------------------------------------------ editors
    Component {
        id: textEditor
        QQC2.TextField {
            id: tf
            readonly property string original: row.asExpression ? (row.raw !== "" ? row.raw : row.value) : row.value
            text: original
            placeholderText: !row.isSet && row.liveValue !== "" ? row.liveValue : ""
            font.family: (row.editKind === "expression" || row.editKind === "unset") ? Kirigami.Theme.fixedWidthFont.family : Kirigami.Theme.defaultFont.family
            Accessible.name: row.name
            leftPadding: kindIcon.visible ? kindIcon.width + Kirigami.Units.smallSpacing * 2 : Kirigami.Units.smallSpacing * 2
            onEditingFinished: {
                if (text !== original && (row.isSet || text !== ""))
                    row.commit(row.editKind === "unset" ? "expression" : row.editKind, text)
            }
            onOriginalChanged: text = original
            Kirigami.Icon {
                id: kindIcon
                anchors.left: parent.left
                anchors.leftMargin: Kirigami.Units.smallSpacing
                anchors.verticalCenter: parent.verticalCenter
                width: Kirigami.Units.iconSizes.small
                height: width
                visible: source !== ""
                source: row.kind === "translated" ? "languages" : (row.editKind === "expression" ? "code-function" : "")
                QQC2.ToolTip.text: row.kind === "translated" ? qsTr("Translatable text") : qsTr("JavaScript expression")
                QQC2.ToolTip.visible: kindHover.hovered
                HoverHandler {
                    id: kindHover
                }
            }
        }
    }

    Component {
        id: boolEditor
        RowLayout {
            QQC2.Switch {
                checked: row.value === "true"
                text: checked ? "true" : "false"
                Accessible.name: row.name
                onToggled: row.commit("bool", checked ? "true" : "false")
            }
        }
    }

    Component {
        id: enumEditor
        QQC2.ComboBox {
            readonly property string shortValue: row.value.split(/::|\./).pop()
            model: row.enumKeys
            displayText: currentIndex >= 0 ? currentText.split("::").pop() : row.value
            currentIndex: {
                for (let i = 0; i < row.enumKeys.length; ++i) {
                    if (row.enumKeys[i] === row.value || row.enumKeys[i].split("::").pop() === shortValue)
                        return i
                }
                return -1
            }
            Accessible.name: row.name
            onActivated: index => row.commit("enum", row.enumKeys[index])
        }
    }

    Component {
        id: colorEditor
        RowLayout {
            spacing: Kirigami.Units.smallSpacing
            QQC2.Button {
                id: swatch
                Layout.preferredWidth: Kirigami.Units.gridUnit * 1.5
                Layout.preferredHeight: Layout.preferredWidth
                padding: Kirigami.Units.smallSpacing
                text: qsTr("Choose Colour")
                display: QQC2.AbstractButton.IconOnly
                contentItem: Rectangle {
                    radius: Kirigami.Units.cornerRadius / 2
                    color: row.value !== "" ? row.value : (row.liveValue !== "" ? row.liveValue : "transparent")
                    border.color: Kirigami.ColorUtils.linearInterpolation(Kirigami.Theme.backgroundColor, Kirigami.Theme.textColor, Kirigami.Theme.frameContrast)
                }
                onClicked: colorDialog.open()
                ColorDialog {
                    id: colorDialog
                    selectedColor: row.value !== "" ? row.value : (row.liveValue !== "" ? row.liveValue : "white")
                    onAccepted: row.commit("color", selectedColor.toString())
                }
            }
            QQC2.TextField {
                Layout.fillWidth: true
                text: row.value
                placeholderText: row.liveValue
                font.family: Kirigami.Theme.fixedWidthFont.family
                Accessible.name: row.name
                onEditingFinished: if (text !== row.value && text !== "") row.commit("color", text)
            }
        }
    }

    Component {
        id: scriptEditor
        QQC2.TextArea {
            property string original: row.raw !== "" ? row.raw : row.value
            text: original
            wrapMode: TextEdit.NoWrap
            font.family: Kirigami.Theme.fixedWidthFont.family
            font.pointSize: Kirigami.Theme.smallFont.pointSize
            Accessible.name: row.name
            onActiveFocusChanged: if (!activeFocus && text !== original) row.commit("script", text)
            onOriginalChanged: text = original
        }
    }

    Component {
        id: readonlyEditor
        QQC2.Label {
            text: row.kind === "object" ? row.value + " { … }" : row.value
            elide: Text.ElideRight
            color: Kirigami.Theme.disabledTextColor
            font.family: Kirigami.Theme.fixedWidthFont.family
            QQC2.ToolTip.text: row.kind === "readonly" ? qsTr("Edit this value in the source view") : qsTr("Select it in the outline to edit")
            QQC2.ToolTip.visible: roHover.hovered
            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            HoverHandler {
                id: roHover
            }
        }
    }
}
