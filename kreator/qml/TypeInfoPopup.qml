import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// A short description of a QML type implemented in C++ (Ctrl+click on one in
// the source view: there is no file to open). Its own properties, signals and
// methods; inherited ones are collapsed per base type.
QQC2.Popup {
    id: popup
    objectName: "typeInfoPopup"

    // from Backend.typeDescription()
    property var info: ({})
    signal closedByUser()

    function show(description, x, y) {
        info = description
        popup.x = x
        popup.y = y
        open()
    }

    width: Math.min(Kirigami.Units.gridUnit * 26, parent ? parent.width : Kirigami.Units.gridUnit * 26)
    height: Math.min(implicitHeight, Kirigami.Units.gridUnit * 22)
    margins: Kirigami.Units.smallSpacing
    padding: Kirigami.Units.largeSpacing
    focus: true
    closePolicy: QQC2.Popup.CloseOnEscape | QQC2.Popup.CloseOnPressOutside
    onClosed: closedByUser()

    component MemberList: ColumnLayout {
        id: list
        property var members: ({})
        spacing: Kirigami.Units.smallSpacing

        Repeater {
            model: [
                { title: qsTr("Properties"), items: list.members.properties || [], kind: "property" },
                { title: qsTr("Signals"), items: list.members.signals || [], kind: "signal" },
                { title: qsTr("Methods"), items: list.members.methods || [], kind: "method" }
            ].filter(g => g.items.length > 0)

            delegate: ColumnLayout {
                id: group
                required property var modelData
                Layout.fillWidth: true
                spacing: 0

                QQC2.Label {
                    text: group.modelData.title
                    font.bold: true
                    opacity: 0.8
                    Layout.topMargin: Kirigami.Units.smallSpacing
                }
                Repeater {
                    model: group.modelData.items
                    delegate: RowLayout {
                        id: row
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        QQC2.Label {
                            text: group.modelData.kind === "property" ? row.modelData.name
                                                                      : row.modelData.name + "(" + row.modelData.params + ")"
                            font.family: Kirigami.Theme.fixedWidthFont.family
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                            Layout.leftMargin: Kirigami.Units.smallSpacing
                        }
                        QQC2.Label {
                            text: group.modelData.kind === "property"
                                  ? (row.modelData.readonly ? qsTr("%1, read-only").arg(row.modelData.type) : row.modelData.type)
                                  : row.modelData.returns && row.modelData.returns !== "void" ? row.modelData.returns : ""
                            visible: text !== ""
                            font.family: Kirigami.Theme.fixedWidthFont.family
                            opacity: 0.7
                            elide: Text.ElideLeft
                            Layout.maximumWidth: Kirigami.Units.gridUnit * 10
                        }
                    }
                }
            }
        }
        QQC2.Label {
            visible: !(list.members.properties || []).length && !(list.members.signals || []).length
                     && !(list.members.methods || []).length
            text: qsTr("No members of its own")
            opacity: 0.7
        }
    }

    contentItem: ColumnLayout {
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Heading {
            level: 3
            text: popup.info.name || ""
            Layout.fillWidth: true
            elide: Text.ElideRight
        }
        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            opacity: 0.7
            text: {
                const parts = [popup.info.module || ""]
                if (popup.info.singleton)
                    parts.push(qsTr("singleton"))
                if ((popup.info.bases || []).length)
                    parts.push(qsTr("inherits %1").arg(popup.info.bases.map(b => b.name).join(" → ")))
                return parts.filter(p => p).join(" · ")
            }
        }
        Kirigami.Separator {
            Layout.fillWidth: true
        }

        QQC2.ScrollView {
            id: scroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: body.implicitHeight
            contentWidth: availableWidth

            ColumnLayout {
                id: body
                width: scroll.availableWidth
                spacing: Kirigami.Units.smallSpacing

                MemberList {
                    Layout.fillWidth: true
                    members: popup.info
                }

                Repeater {
                    model: popup.info.bases || []
                    delegate: ColumnLayout {
                        id: base
                        required property var modelData
                        property bool expanded: false
                        readonly property int count: base.modelData.properties.length + base.modelData.signals.length
                                                     + base.modelData.methods.length
                        Layout.fillWidth: true
                        spacing: 0
                        visible: count > 0

                        QQC2.ItemDelegate {
                            objectName: "inheritedFrom" + base.modelData.name
                            Layout.fillWidth: true
                            icon.name: base.expanded ? "arrow-down" : (Qt.application.layoutDirection === Qt.RightToLeft ? "arrow-left" : "arrow-right")
                            text: qsTr("Inherited from %1 (%2)").arg(base.modelData.name).arg(base.count)
                            onClicked: base.expanded = !base.expanded
                        }
                        MemberList {
                            visible: base.expanded
                            Layout.fillWidth: true
                            Layout.leftMargin: Kirigami.Units.largeSpacing
                            members: base.modelData
                        }
                    }
                }
            }
        }

        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: qsTr("Implemented in C++: there is no source file to open.")
        }
    }
}
