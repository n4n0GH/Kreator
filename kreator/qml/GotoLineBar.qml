import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// Kate-style "Go to line" bar (Ctrl+G). Accepts `42`, `42:7` (line:column)
// and relative `+10` / `-10`.
QQC2.ToolBar {
    id: bar

    required property Item editor
    required property Item pane

    property string error: ""

    position: QQC2.ToolBar.Footer
    visible: false

    function open() {
        error = ""
        visible = true
        field.text = String(pane.currentLine)
        field.forceActiveFocus()
        field.selectAll()
    }
    function close() {
        visible = false
        editor.forceActiveFocus()
    }

    // returns { line, column } (1-based) or null
    function parse(text) {
        const m = text.trim().match(/^([+-]?)(\d+)(?:\s*[:,]\s*(\d+))?$/)
        if (!m)
            return null
        let line = Number(m[2])
        if (m[1] === "+")
            line = pane.currentLine + line
        else if (m[1] === "-")
            line = pane.currentLine - line
        return { line: line, column: m[3] !== undefined ? Number(m[3]) : 1 }
    }

    function go() {
        const target = parse(field.text)
        const count = pane.lineStarts.length
        if (!target) {
            error = qsTr("Enter a line number, line:column, +N or -N")
            return
        }
        const line = Math.max(1, Math.min(count, target.line))
        const start = pane.lineStarts[line - 1]
        const end = line < count ? pane.lineStarts[line] - 1 : editor.length
        editor.cursorPosition = Math.min(end, start + Math.max(0, target.column - 1))
        pane.showWithContext(editor.cursorPosition)  // folded code is unfolded by the cursor move
        close()
    }

    RowLayout {
        anchors.fill: parent
        spacing: Kirigami.Units.smallSpacing

        QQC2.Label {
            text: qsTr("Go to line:")
        }
        QQC2.TextField {
            id: field
            Layout.preferredWidth: Kirigami.Units.gridUnit * 8
            font.family: bar.pane.editorFont.family
            inputMethodHints: Qt.ImhPreferNumbers
            Accessible.name: qsTr("Line number")
            onTextChanged: bar.error = ""
            Keys.onPressed: event => {
                if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    bar.go()
                    event.accepted = true
                } else if (event.key === Qt.Key_Escape) {
                    bar.close()
                    event.accepted = true
                } else if (event.key === Qt.Key_Up || event.key === Qt.Key_Down) {
                    const t = bar.parse(text)
                    if (t)
                        text = String(Math.max(1, Math.min(bar.pane.lineStarts.length, t.line + (event.key === Qt.Key_Up ? -1 : 1))))
                    event.accepted = true
                }
            }
        }
        QQC2.Button {
            text: qsTr("Go")
            icon.name: "go-jump"
            onClicked: bar.go()
        }
        QQC2.Label {
            Layout.fillWidth: true
            text: bar.error !== "" ? bar.error : qsTr("of %1").arg(bar.pane.lineStarts.length)
            color: bar.error !== "" ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.disabledTextColor
            elide: Text.ElideRight
        }
        QQC2.ToolButton {
            icon.name: "dialog-close"
            text: qsTr("Close")
            display: QQC2.AbstractButton.IconOnly
            onClicked: bar.close()
            QQC2.ToolTip.text: qsTr("Close (Esc)")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
    }
}
