import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: panel
    spacing: 0

    property bool showAll: false

    // `property int count`, `required property string title`: typed as the
    // name of a new property, this declares one (a value is optional then)
    function declares(name) {
        return Backend.docKind === "qml"
            && /^\s*((readonly|required|default|final)\s+)*property\s+[A-Za-z_][\w.<>]*\s+[A-Za-z_]\w*\s*$/.test(name)
    }

    Kirigami.Theme.colorSet: Kirigami.Theme.View
    Kirigami.Theme.inherit: false

    // ------------------------------------------------------------ header
    Rectangle {
        Layout.fillWidth: true
        implicitHeight: header.implicitHeight + Kirigami.Units.largeSpacing * 2
        color: Kirigami.Theme.alternateBackgroundColor

        ColumnLayout {
            id: header
            anchors.fill: parent
            anchors.margins: Kirigami.Units.largeSpacing
            spacing: Kirigami.Units.smallSpacing

            Kirigami.Heading {
                Layout.fillWidth: true
                level: 3
                elide: Text.ElideRight
                text: Backend.selectedType !== "" ? Backend.selectedType.split(".").pop() : qsTr("No Selection")
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: Kirigami.Units.smallSpacing
                rowSpacing: Kirigami.Units.smallSpacing
                visible: Backend.selectedType !== ""

                QQC2.Label {
                    text: qsTr("Type:")
                    Layout.alignment: Qt.AlignRight
                }
                QQC2.TextField {
                    id: typeField
                    Layout.fillWidth: true
                    text: Backend.selectedType
                    font.family: Kirigami.Theme.fixedWidthFont.family
                    Accessible.name: qsTr("Type")
                    onEditingFinished: if (text !== Backend.selectedType) Backend.setSelectedType(text)
                }
                QQC2.Label {
                    text: Backend.idLabel + ":"
                    Layout.alignment: Qt.AlignRight
                }
                QQC2.TextField {
                    id: idField
                    Layout.fillWidth: true
                    text: Backend.selectedId
                    placeholderText: Backend.idLabel === "id" ? qsTr("No id") : ""
                    font.family: Kirigami.Theme.fixedWidthFont.family
                    Accessible.name: Backend.idLabel
                    onEditingFinished: if (text !== Backend.selectedId) Backend.setSelectedId(text)
                }
            }
        }
    }

    Kirigami.Separator {
        Layout.fillWidth: true
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.margins: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        Kirigami.SearchField {
            // no window-wide Ctrl+F: the source view uses it for find
            focusSequences: []
            id: search
            Layout.fillWidth: true
            placeholderText: qsTr("Filter properties…")
            onTextChanged: Backend.setPropertyFilter(text)
        }
        QQC2.ToolButton {
            icon.name: "view-list-details"
            checkable: true
            checked: panel.showAll
            text: qsTr("Show All Properties")
            display: QQC2.AbstractButton.IconOnly
            onToggled: {
                panel.showAll = checked
                Backend.setShowAllProperties(checked)
            }
            QQC2.ToolTip.text: checked ? qsTr("Showing all properties of the live object") : qsTr("Show all properties of the live object")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
    }

    Kirigami.Separator {
        Layout.fillWidth: true
    }

    // ------------------------------------------------------------ list
    QQC2.ScrollView {
        Layout.fillWidth: true
        Layout.fillHeight: true
        background: Rectangle {
            color: Kirigami.Theme.backgroundColor
        }

        ListView {
            id: propView
            clip: true
            model: Backend.properties
            reuseItems: false
            section.property: "section"
            section.delegate: Kirigami.ListSectionHeader {
                required property string section
                width: ListView.view.width
                text: section
            }
            delegate: PropertyRow {
                width: ListView.view.width
            }

            Kirigami.PlaceholderMessage {
                anchors.centerIn: parent
                width: parent.width - Kirigami.Units.largeSpacing * 4
                visible: Backend.selectedType === ""
                icon.name: "edit-select"
                text: qsTr("Select an object")
                explanation: qsTr("Click an object in the preview or the outline to edit its properties.")
            }
        }
    }

    Kirigami.Separator {
        Layout.fillWidth: true
    }

    // ------------------------------------------------------------ add property
    GridLayout {
        Layout.fillWidth: true
        Layout.margins: Kirigami.Units.smallSpacing
        columns: 3
        columnSpacing: Kirigami.Units.smallSpacing
        visible: Backend.selectedType !== ""

        QQC2.TextField {
            id: newName
            objectName: "newPropertyName"
            Layout.fillWidth: true
            Layout.preferredWidth: 1
            placeholderText: qsTr("Property")
            font.family: Kirigami.Theme.fixedWidthFont.family
            Accessible.name: qsTr("New property name")
            onAccepted: newValue.forceActiveFocus()
            QQC2.ToolTip.text: Backend.docKind === "qml"
                ? qsTr("A property to set (“spacing”, “Layout.fillWidth”), a signal handler (“onClicked”), or a property to declare (“property int count”)")
                : qsTr("A property to set")
            QQC2.ToolTip.visible: hovered && !activeFocus
            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
        QQC2.TextField {
            id: newValue
            objectName: "newPropertyValue"
            Layout.fillWidth: true
            Layout.preferredWidth: 1
            placeholderText: Backend.docKind === "ui" ? qsTr("Text value") : qsTr("Value or expression")
            font.family: Kirigami.Theme.fixedWidthFont.family
            Accessible.name: qsTr("New property value")
            onAccepted: addButton.clicked()
        }
        QQC2.Button {
            id: addButton
            objectName: "addPropertyButton"
            icon.name: "list-add"
            text: qsTr("Add")
            display: QQC2.AbstractButton.IconOnly
            // (a declared property needs no value)
            enabled: newName.text.trim() !== "" && (newValue.text.trim() !== "" || panel.declares(newName.text))
            QQC2.ToolTip.text: panel.declares(newName.text) ? qsTr("Declare property") : qsTr("Add property")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            onClicked: {
                if (!enabled)
                    return
                Backend.setProperty(newName.text.trim(), "expression", newValue.text)
                newName.text = ""
                newValue.text = ""
                newName.forceActiveFocus()
            }
        }
    }
}
