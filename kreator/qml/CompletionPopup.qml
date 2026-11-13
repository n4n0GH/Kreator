import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// Code completion list for the source view, filled by the language server.
// The editor keeps the keyboard focus; SourcePane forwards navigation keys.
QQC2.Popup {
    id: popup

    required property Item editor
    required property Item pane

    property var items: []        // everything the server offered
    property var shown: []        // filtered by what has been typed
    property int wordStart: 0     // start of the word being completed
    property string prefix: ""

    padding: 1
    focus: false
    modal: false
    closePolicy: QQC2.Popup.CloseOnPressOutsideParent
    width: Kirigami.Units.gridUnit * 26
    height: Math.min(list.contentHeight, rowHeight * 10) + 2
    readonly property real rowHeight: Math.max(Kirigami.Units.iconSizes.small, fontMetrics.height) + Kirigami.Units.smallSpacing

    FontMetrics {
        id: fontMetrics
        font: popup.pane.editorFont
    }

    function show(all, start) {
        items = all
        wordStart = start
        refilter()
    }

    // case-insensitive: prefix matches first (exact case first), then
    // "contains" matches once two characters were typed
    function refilter() {
        prefix = editor.text.substring(wordStart, editor.cursorPosition)
        const p = prefix.toLowerCase()
        const starts = [], contains = []
        for (const it of items) {
            const f = it.filterText.toLowerCase()
            if (f.startsWith(p))
                starts.push(it)
            else if (p.length >= 2 && f.indexOf(p) > 0)
                contains.push(it)
        }
        const exactCase = it => it.filterText.startsWith(prefix) ? 0 : 1
        starts.sort((a, b) => exactCase(a) - exactCase(b) || a.sortText.localeCompare(b.sortText))
        contains.sort((a, b) => a.sortText.localeCompare(b.sortText))
        const result = starts.concat(contains).slice(0, 300)
        // nothing to offer, or exactly what was typed: get out of the way
        if (!result.length || (result.length === 1 && result[0].insertText === prefix)) {
            close()
            return
        }
        shown = result
        list.currentIndex = 0
        place()
        if (!opened)
            open()
    }

    // below the word, or above it when there is no room below
    function place() {
        const r = editor.positionToRectangle(wordStart)
        const flick = pane.flickable
        const below = r.y + r.height + height - flick.contentY <= flick.height
        x = r.x - Kirigami.Units.iconSizes.small - Kirigami.Units.smallSpacing * 2
        y = below ? r.y + r.height + 2 : r.y - height - 2
    }

    function move(delta) {
        if (!shown.length)
            return
        list.currentIndex = Math.max(0, Math.min(shown.length - 1, list.currentIndex + delta))
    }

    function accept() {
        const it = shown[list.currentIndex]
        close()
        if (!it)
            return
        pane.beginStep()
        editor.remove(wordStart, editor.cursorPosition)
        editor.insert(wordStart, it.insertText)
        pane.endStep()
        editor.cursorPosition = wordStart + it.insertText.length
    }

    background: Rectangle {
        color: popup.pane.bg
        border.color: Kirigami.ColorUtils.linearInterpolation(popup.pane.bg, popup.pane.textColor, 0.3)
        radius: Kirigami.Units.cornerRadius / 2
    }

    contentItem: ListView {
        id: list
        clip: true
        model: popup.shown
        boundsBehavior: Flickable.StopAtBounds
        highlightMoveDuration: 0
        QQC2.ScrollBar.vertical: QQC2.ScrollBar {}

        delegate: Rectangle {
            id: row
            required property var modelData
            required property int index
            width: ListView.view.width
            height: popup.rowHeight
            color: ListView.isCurrentItem ? popup.pane.selectionColor : "transparent"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Kirigami.Units.smallSpacing
                anchors.rightMargin: Kirigami.Units.smallSpacing
                spacing: Kirigami.Units.smallSpacing

                Kirigami.Icon {
                    source: row.modelData.icon
                    implicitWidth: Kirigami.Units.iconSizes.small
                    implicitHeight: Kirigami.Units.iconSizes.small
                }
                Text {
                    // the typed part in bold, like Kate
                    textFormat: Text.StyledText
                    text: {
                        const l = row.modelData.label
                        const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;")
                        const n = l.toLowerCase().startsWith(popup.prefix.toLowerCase()) ? popup.prefix.length : 0
                        return "<b>" + esc(l.substring(0, n)) + "</b>" + esc(l.substring(n))
                    }
                    font: popup.pane.editorFont
                    color: row.ListView.isCurrentItem ? popup.pane.selectedTextColor : popup.pane.textColor
                }
                Item {
                    Layout.fillWidth: true
                    implicitWidth: Kirigami.Units.largeSpacing
                }
                Text {
                    text: row.modelData.detail
                    font.family: popup.pane.editorFont.family
                    font.pointSize: Math.max(6, popup.pane.editorFont.pointSize - 1)
                    color: popup.pane.lineNumberColor
                    elide: Text.ElideRight
                    Layout.maximumWidth: Kirigami.Units.gridUnit * 12
                }
            }
            TapHandler {
                onTapped: {
                    list.currentIndex = row.index
                    popup.accept()
                }
            }
        }
    }
}
