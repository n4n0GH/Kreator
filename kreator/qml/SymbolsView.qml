import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// Document outline from qmlls (textDocument/documentSymbol), like Kate's
// symbol view: objects (with their id), functions and signals; property
// bindings on request. Click to go there in the source view.
ColumnLayout {
    id: view
    spacing: 0

    property bool showBindings: false
    property string filter: ""
    // the symbol containing the cursor
    property int cursorLine: -1

    // (made only while shown: switching documents with another tab of the
    // side panel open needn't rebuild the list)
    readonly property var rows: {
        if (!visible)
            return []
        const f = filter.toLowerCase()
        const out = []
        for (const s of Lsp.symbols) {
            if (s.isBinding && !showBindings)
                continue
            if (f !== "" && s.name.toLowerCase().indexOf(f) < 0 && s.detail.toLowerCase().indexOf(f) < 0)
                continue
            out.push(s)
        }
        return out
    }
    readonly property int currentIndex: {
        // innermost symbol whose range contains the cursor line
        let best = -1
        for (let i = 0; i < rows.length; ++i) {
            const s = rows[i]
            if (s.line <= cursorLine && cursorLine <= s.endLine)
                best = i
        }
        return best
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.margins: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        Kirigami.SearchField {
            Layout.fillWidth: true
            placeholderText: qsTr("Filter symbols…")
            focusSequences: []
            onTextChanged: view.filter = text
        }
        QQC2.ToolButton {
            icon.name: "code-variable"
            text: qsTr("Show Property Bindings")
            display: QQC2.AbstractButton.IconOnly
            checkable: true
            checked: view.showBindings
            onToggled: view.showBindings = checked
            QQC2.ToolTip.text: text
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
    }

    Kirigami.Separator {
        Layout.fillWidth: true
    }

    QQC2.ScrollView {
        Layout.fillWidth: true
        Layout.fillHeight: true
        background: Rectangle {
            color: Kirigami.Theme.backgroundColor
        }

        ListView {
            id: list
            clip: true
            model: view.rows
            currentIndex: view.currentIndex
            highlightMoveDuration: 0
            onCurrentIndexChanged: if (currentIndex >= 0) positionViewAtIndex(currentIndex, ListView.Contain)

            // (a light row, not an ItemDelegate: another document's symbols
            // are many new rows at once, and each style delegate is slow to make)
            delegate: Item {
                id: row
                required property var modelData
                required property int index
                readonly property bool highlighted: ListView.isCurrentItem
                readonly property string shortName: !modelData.isObject ? modelData.name : modelData.name.split(".").pop()
                width: ListView.view.width
                implicitHeight: Math.max(Kirigami.Units.iconSizes.small, nameText.implicitHeight) + Kirigami.Units.smallSpacing * 2

                Accessible.role: Accessible.ListItem
                Accessible.name: modelData.name + (modelData.detail ? " " + modelData.detail : "")
                Accessible.onPressAction: tap.tapped(null, Qt.LeftButton)

                Rectangle {
                    anchors.fill: parent
                    color: row.highlighted ? Kirigami.Theme.highlightColor
                         : hover.hovered ? Qt.alpha(Kirigami.Theme.highlightColor, 0.25) : "transparent"
                }
                HoverHandler {
                    id: hover
                }
                TapHandler {
                    id: tap
                    onTapped: applicationWindow().mainPage.gotoSource(row.modelData.line, row.modelData.character)
                }
                QQC2.ToolTip.text: modelData.name + (modelData.detail ? ": " + modelData.detail : "") + "\n" + qsTr("Line %1").arg(modelData.line + 1)
                QQC2.ToolTip.visible: hover.hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay * 2

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Kirigami.Units.largeSpacing + row.modelData.depth * Kirigami.Units.gridUnit * 0.8
                    anchors.rightMargin: Kirigami.Units.largeSpacing
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon {
                        source: row.modelData.icon
                        implicitWidth: Kirigami.Units.iconSizes.small
                        implicitHeight: Kirigami.Units.iconSizes.small
                    }
                    Text {
                        id: nameText
                        text: row.shortName
                        font.family: Kirigami.Theme.defaultFont.family
                        font.pointSize: Kirigami.Theme.defaultFont.pointSize
                        font.bold: row.modelData.isObject && row.modelData.depth === 0
                        elide: Text.ElideRight
                        Layout.fillWidth: row.modelData.detail === ""
                        color: row.highlighted ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor
                    }
                    Text {
                        visible: row.modelData.detail !== ""
                        Layout.fillWidth: true
                        text: row.modelData.detail
                        elide: Text.ElideRight
                        font: row.modelData.isObject ? Kirigami.Theme.fixedWidthFont : Kirigami.Theme.defaultFont
                        color: row.highlighted ? Kirigami.Theme.highlightedTextColor
                                               : (row.modelData.isObject ? Kirigami.Theme.linkColor : Kirigami.Theme.disabledTextColor)
                    }
                }
            }

            Kirigami.PlaceholderMessage {
                anchors.centerIn: parent
                width: parent.width - Kirigami.Units.largeSpacing * 4
                visible: list.count === 0
                icon.name: Lsp.running ? "search" : "code-class"
                text: Lsp.indexing && view.filter === "" ? qsTr("Indexing…")
                      : !Lsp.running ? qsTr("Symbols need the QML language server (qmlls)")
                      : view.filter !== "" ? qsTr("No matching symbols") : qsTr("No symbols")
            }
        }
    }
}
