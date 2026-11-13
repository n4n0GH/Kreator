import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// "Find References" results below the source view (Shift+F12), like Kate's
// LSP client: one row per reference, grouped by file; click to go there.
ColumnLayout {
    id: panel

    required property Item pane

    property string symbol: ""
    property var results: []
    readonly property int fileCount: {
        const files = {}
        for (const r of results)
            files[r.path] = true
        return Object.keys(files).length
    }

    spacing: 0
    visible: false

    function show(name, items) {
        symbol = name
        results = items
        visible = true
        list.currentIndex = -1
    }
    function close() {
        visible = false
        results = []
    }

    Kirigami.Separator {
        Layout.fillWidth: true
    }

    QQC2.ToolBar {
        Layout.fillWidth: true
        position: QQC2.ToolBar.Footer

        RowLayout {
            anchors.fill: parent
            spacing: Kirigami.Units.smallSpacing

            Kirigami.Icon {
                source: "edit-find"
                implicitWidth: Kirigami.Units.iconSizes.small
                implicitHeight: Kirigami.Units.iconSizes.small
            }
            QQC2.Label {
                Layout.fillWidth: true
                elide: Text.ElideRight
                text: panel.results.length === 0
                      ? qsTr("No references to “%1”").arg(panel.symbol)
                      : panel.fileCount > 1
                        ? qsTr("%n reference(s) to “%1” in %2 files", "", panel.results.length).arg(panel.symbol).arg(panel.fileCount)
                        : qsTr("%n reference(s) to “%1”", "", panel.results.length).arg(panel.symbol)
            }
            QQC2.ToolButton {
                icon.name: "edit-rename"
                text: qsTr("Rename…")
                enabled: panel.results.length > 0
                onClicked: panel.pane.startRename()
                QQC2.ToolTip.text: qsTr("Rename this symbol everywhere (F2)")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.ToolButton {
                icon.name: "dialog-close"
                text: qsTr("Close")
                display: QQC2.AbstractButton.IconOnly
                onClicked: panel.close()
                QQC2.ToolTip.text: qsTr("Close (Esc)")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
        }
    }

    QQC2.ScrollView {
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(list.contentHeight, Kirigami.Units.gridUnit * 9)
        visible: panel.results.length > 0

        Kirigami.Theme.colorSet: Kirigami.Theme.View
        Kirigami.Theme.inherit: false
        background: Rectangle {
            color: Kirigami.Theme.backgroundColor
        }

        ListView {
            id: list
            clip: true
            model: panel.results
            section.property: "fileName"
            section.delegate: Kirigami.ListSectionHeader {
                required property string section
                width: ListView.view.width
                text: section
            }
            delegate: QQC2.ItemDelegate {
                id: row
                required property var modelData
                required property int index
                width: ListView.view.width
                highlighted: ListView.isCurrentItem
                topPadding: Kirigami.Units.smallSpacing / 2
                bottomPadding: Kirigami.Units.smallSpacing / 2
                onClicked: {
                    list.currentIndex = index
                    panel.pane.gotoReference(modelData)
                }
                contentItem: RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    QQC2.Label {
                        Layout.minimumWidth: Kirigami.Units.gridUnit * 2.5
                        horizontalAlignment: Text.AlignRight
                        text: row.modelData.line + 1
                        font.family: panel.pane.editorFont.family
                        color: row.highlighted ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.disabledTextColor
                    }
                    QQC2.Label {
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        textFormat: Text.StyledText
                        font.family: panel.pane.editorFont.family
                        color: row.highlighted ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor
                        text: {
                            const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
                            const m = row.modelData
                            return esc(m.before) + "<b>" + esc(m.match) + "</b>" + esc(m.after)
                        }
                    }
                }
            }
        }
    }
}
