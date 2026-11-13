import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// Kate-style find / replace bar for the source view (Ctrl+F, Ctrl+R).
QQC2.ToolBar {
    id: bar

    required property Item editor   // the TextEdit
    required property Item pane     // the SourcePane

    property bool replaceMode: false
    property var matches: []        // [{ start, end }] in text order
    property int current: -1
    property string error: ""
    property string notice: ""      // "Continued from the top" etc.
    property int origin: 0          // where incremental search starts
    readonly property string query: findField.text
    readonly property bool active: visible

    position: QQC2.ToolBar.Footer
    visible: false

    // ------------------------------------------------------------ API
    function open(replace) {
        const sel = editor.selectedText
        if (sel !== "" && sel.indexOf("\n") < 0 && sel.indexOf(" ") < 0)
            findField.text = sel
        replaceMode = replace
        visible = true
        origin = editor.selectionStart
        if (replace && sel !== "" && findField.text === sel)
            replaceField.forceActiveFocus()
        else
            findField.forceActiveFocus()
        findField.selectAll()
        search(true)
    }
    function close() {
        visible = false
        matches = []
        current = -1
        notice = ""
        editor.forceActiveFocus()
    }

    function regex(global) {
        let src = findField.text
        if (src === "")
            return null
        if (!regexButton.checked)
            src = src.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
        if (wordButton.checked)
            src = "\\b(?:" + src + ")\\b"
        return new RegExp(src, (global ? "g" : "y") + (caseButton.checked ? "" : "i") + "m")
    }

    // find all matches; `fromOrigin` = incremental search while typing
    function search(fromOrigin) {
        error = ""
        let re
        try {
            re = regex(true)
        } catch (e) {
            error = qsTr("Invalid regular expression")
            matches = []
            current = -1
            return
        }
        if (re === null) {
            matches = []
            current = -1
            return
        }
        const t = editor.text
        const out = []
        let m
        while ((m = re.exec(t)) !== null && out.length < 10000) {
            if (m[0].length === 0) {  // empty match (e.g. ^): step over it
                re.lastIndex++
                continue
            }
            out.push({ start: m.index, end: m.index + m[0].length })
        }
        matches = out
        if (!out.length) {
            current = -1
            return
        }
        const from = fromOrigin ? origin : editor.selectionStart
        let i = out.findIndex(x => x.start >= from)
        if (i < 0)
            i = 0
        select(i)
    }
    function select(i) {
        current = i
        const m = matches[i]
        editor.select(m.start, m.end)  // moving the cursor also unfolds folded code
        Qt.callLater(pane.showWithContext, m.start)
    }
    function next() {
        if (!matches.length)
            return search(false)
        notice = ""
        // continue after the current selection, so typing in the editor in between works
        let i = matches.findIndex(x => x.start >= editor.selectionEnd && !(x.start === editor.selectionStart && x.end === editor.selectionEnd))
        if (i < 0) {
            i = 0
            notice = qsTr("Continued from the top")
        }
        select(i)
    }
    function previous() {
        if (!matches.length)
            return search(false)
        notice = ""
        let i = -1
        for (let k = matches.length - 1; k >= 0; --k) {
            if (matches[k].end <= editor.selectionStart) {
                i = k
                break
            }
        }
        if (i < 0) {
            i = matches.length - 1
            notice = qsTr("Continued from the bottom")
        }
        select(i)
    }

    // replacement text for a match: \1…\9 and \0 are groups, \n \t escapes
    function expand(m) {
        const rep = replaceField.text
        if (!regexButton.checked)
            return rep
        return rep.replace(/\\(\d|n|t|\\)/g, (all, c) => {
            if (c === "n") return "\n"
            if (c === "t") return "\t"
            if (c === "\\") return "\\"
            return m[Number(c)] !== undefined ? m[Number(c)] : ""
        })
    }
    function matchAt(start) {
        const re = regex(false)  // sticky: must match exactly at `start`
        re.lastIndex = start
        return re.exec(editor.text)
    }
    function replaceCurrent() {
        if (current < 0 || !matches.length)
            return search(false)
        const sel = matches[current]
        if (editor.selectionStart !== sel.start || editor.selectionEnd !== sel.end)
            return select(current)  // first show what would be replaced
        const m = matchAt(sel.start)
        if (!m)
            return search(false)
        const text = expand(m)
        pane.beginStep()
        editor.remove(sel.start, sel.end)
        editor.insert(sel.start, text)
        pane.endStep()
        editor.cursorPosition = sel.start + text.length
        search(false)
        if (matches.length)
            next()
    }
    function replaceAll() {
        if (!matches.length)
            search(false)
        const all = matches.slice()
        if (!all.length)
            return
        let count = 0
        pane.beginStep()  // one undo step for everything
        for (let k = all.length - 1; k >= 0; --k) {
            const m = matchAt(all[k].start)
            if (!m)
                continue
            const text = expand(m)
            editor.remove(all[k].start, all[k].start + m[0].length)
            editor.insert(all[k].start, text)
            ++count
        }
        pane.endStep()
        search(false)
        notice = qsTr("Replaced %n occurrence(s)", "", count)
    }

    // keep results up to date while the text changes
    Connections {
        target: bar.editor
        function onTextChanged() {
            if (bar.visible)
                researchTimer.restart()
        }
    }
    Timer {
        id: researchTimer
        interval: 150
        onTriggered: {
            const keep = bar.editor.selectionStart
            bar.error = ""
            try {
                const re = bar.regex(true)
                if (re === null)
                    return
                const t = bar.editor.text
                const out = []
                let m
                while ((m = re.exec(t)) !== null && out.length < 10000) {
                    if (m[0].length === 0) {
                        re.lastIndex++
                        continue
                    }
                    out.push({ start: m.index, end: m.index + m[0].length })
                }
                bar.matches = out
                bar.current = out.findIndex(x => x.start === keep)
            } catch (e) {
                bar.error = qsTr("Invalid regular expression")
            }
        }
    }

    // ------------------------------------------------------------ UI
    GridLayout {
        anchors.fill: parent
        columns: 2
        columnSpacing: Kirigami.Units.smallSpacing
        rowSpacing: Kirigami.Units.smallSpacing

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            Kirigami.SearchField {
                // no window-wide Ctrl+F: the source view uses it for find
                focusSequences: []
                id: findField
                Layout.fillWidth: true
                placeholderText: qsTr("Find…")
                font.family: bar.pane.editorFont.family
                autoAccept: false
                Accessible.name: qsTr("Find")
                // a red tint for invalid patterns or no results, like Kate
                color: (bar.error !== "" || (text !== "" && bar.matches.length === 0)) ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                onTextChanged: {
                    bar.notice = ""
                    bar.search(true)
                }
                Keys.onPressed: event => bar.handleKey(event, false)
            }
            QQC2.ToolButton {
                icon.name: "go-up"
                text: qsTr("Previous")
                display: QQC2.AbstractButton.IconOnly
                enabled: bar.matches.length > 0
                onClicked: bar.previous()
                QQC2.ToolTip.text: qsTr("Previous match (Shift+F3)")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.ToolButton {
                icon.name: "go-down"
                text: qsTr("Next")
                display: QQC2.AbstractButton.IconOnly
                enabled: bar.matches.length > 0
                onClicked: bar.next()
                QQC2.ToolTip.text: qsTr("Next match (F3)")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.ToolButton {
                id: caseButton
                text: "Aa"
                checkable: true
                onToggled: bar.search(false)
                Accessible.name: qsTr("Match case")
                QQC2.ToolTip.text: qsTr("Match case")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.ToolButton {
                id: wordButton
                text: "\\b"
                font.family: bar.pane.editorFont.family
                checkable: true
                onToggled: bar.search(false)
                Accessible.name: qsTr("Whole words")
                QQC2.ToolTip.text: qsTr("Whole words only")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.ToolButton {
                id: regexButton
                text: ".*"
                font.family: bar.pane.editorFont.family
                checkable: true
                onToggled: bar.search(false)
                Accessible.name: qsTr("Regular expression")
                QQC2.ToolTip.text: qsTr("Regular expression; use \\1, \\2 … in the replacement")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.Label {
                Layout.minimumWidth: Kirigami.Units.gridUnit * 5
                horizontalAlignment: Text.AlignHCenter
                text: bar.error !== "" ? bar.error
                    : bar.notice !== "" ? bar.notice
                    : bar.query === "" ? ""
                    : bar.matches.length === 0 ? qsTr("No matches")
                    : bar.current >= 0 ? qsTr("%1 of %2").arg(bar.current + 1).arg(bar.matches.length)
                    : qsTr("%n match(es)", "", bar.matches.length)
                color: bar.error !== "" || (bar.query !== "" && bar.matches.length === 0) ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                opacity: bar.notice !== "" ? 0.8 : 1
                elide: Text.ElideRight
            }
        }
        RowLayout {
            Layout.alignment: Qt.AlignRight | Qt.AlignTop
            spacing: 0
            QQC2.ToolButton {
                icon.name: "edit-find-replace"
                text: qsTr("Replace")
                display: QQC2.AbstractButton.IconOnly
                checkable: true
                checked: bar.replaceMode
                onToggled: {
                    bar.replaceMode = checked
                    if (checked)
                        replaceField.forceActiveFocus()
                }
                QQC2.ToolTip.text: qsTr("Show replace (Ctrl+R)")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
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

        RowLayout {
            Layout.fillWidth: true
            visible: bar.replaceMode
            spacing: Kirigami.Units.smallSpacing

            QQC2.TextField {
                id: replaceField
                Layout.fillWidth: true
                placeholderText: regexButton.checked ? qsTr("Replace with… (\\1 for the first group)") : qsTr("Replace with…")
                font.family: bar.pane.editorFont.family
                Accessible.name: qsTr("Replace with")
                Keys.onPressed: event => bar.handleKey(event, true)
            }
            QQC2.Button {
                text: qsTr("Replace")
                enabled: bar.matches.length > 0
                onClicked: bar.replaceCurrent()
            }
            QQC2.Button {
                text: qsTr("Replace All")
                enabled: bar.matches.length > 0
                onClicked: bar.replaceAll()
            }
        }
        Item {
            visible: bar.replaceMode
            implicitWidth: 1
        }
    }

    function handleKey(event, inReplace) {
        if (event.key === Qt.Key_Escape) {
            close()
            event.accepted = true
        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            if (inReplace && (event.modifiers & Qt.ControlModifier))
                replaceAll()
            else if (inReplace)
                replaceCurrent()
            else if (event.modifiers & Qt.ShiftModifier)
                previous()
            else
                next()
            event.accepted = true
        } else if (event.key === Qt.Key_F3) {
            if (event.modifiers & Qt.ShiftModifier)
                previous()
            else
                next()
            event.accepted = true
        } else if ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_R) {
            replaceMode = true
            replaceField.forceActiveFocus()
            event.accepted = true
        } else if ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_F) {
            findField.forceActiveFocus()
            findField.selectAll()
            event.accepted = true
        }
    }
}
