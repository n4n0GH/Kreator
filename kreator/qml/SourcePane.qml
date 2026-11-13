import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.syntaxhighlighting

ColumnLayout {
    id: pane
    spacing: 0

    property bool active: false
    property bool dirty: false

    // Kate's look and editing settings (katerc), unless turned off
    readonly property var ks: Backend.kateStyle
    readonly property bool kate: ks.enabled === true && ks.background !== ""
    readonly property color bg: kate ? ks.background : Kirigami.Theme.backgroundColor
    readonly property color textColor: kate && ks.text ? ks.text : Kirigami.Theme.textColor
    readonly property color selectionColor: kate && ks.selection ? ks.selection : Kirigami.Theme.highlightColor
    readonly property color selectedTextColor: kate && ks.selectedText ? ks.selectedText : Kirigami.Theme.highlightedTextColor
    readonly property color currentLineColor: kate && ks.currentLine ? ks.currentLine : Qt.rgba(Kirigami.Theme.highlightColor.r, Kirigami.Theme.highlightColor.g, Kirigami.Theme.highlightColor.b, 0.08)
    readonly property color gutterBg: kate && ks.border ? ks.border : Kirigami.Theme.alternateBackgroundColor
    readonly property color lineNumberColor: kate && ks.lineNumbers ? ks.lineNumbers : Kirigami.Theme.disabledTextColor
    readonly property color currentLineNumberColor: kate && ks.currentLineNumber ? ks.currentLineNumber : Kirigami.Theme.textColor
    readonly property color bracketColor: kate && ks.bracketMatching ? ks.bracketMatching : Qt.rgba(Kirigami.Theme.highlightColor.r, Kirigami.Theme.highlightColor.g, Kirigami.Theme.highlightColor.b, 0.3)
    readonly property color searchColor: kate && ks.searchHighlight ? ks.searchHighlight : Qt.rgba(Kirigami.Theme.neutralTextColor.r, Kirigami.Theme.neutralTextColor.g, Kirigami.Theme.neutralTextColor.b, 0.35)
    readonly property color separatorColor: kate && ks.separator ? ks.separator : Kirigami.ColorUtils.linearInterpolation(Kirigami.Theme.backgroundColor, Kirigami.Theme.textColor, Kirigami.Theme.frameContrast)
    readonly property font editorFont: kate ? Qt.font({ family: ks.fontFamily, pointSize: ks.fontPointSize }) : Kirigami.Theme.fixedWidthFont
    readonly property int indentWidth: kate ? ks.indentWidth : 4
    readonly property string indentUnit: (!kate || ks.replaceTabs) ? " ".repeat(indentWidth) : "\t"
    readonly property bool autoBrackets: kate ? ks.autoBrackets : true
    readonly property bool lineNumbers: kate ? ks.lineNumbersShown : true
    // dynamic word wrap: Kate's setting, toggled here with F10 like in Kate
    property real unwrappedWidth: 0
    readonly property Item flickable: flick
    readonly property color errorColor: Kirigami.Theme.negativeTextColor
    readonly property color warningColor: Kirigami.Theme.neutralTextColor
    property bool followCursor: false  // set by caret moves and typing
    readonly property real foldColumn: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
    // wrapped rows line up with the line's indentation, up to this share of the view
    readonly property int alignIndentPercent: kate && ks.wrapAlignIndent !== undefined ? ks.wrapAlignIndent : 80

    // ------------------------------------------------------------ undo history
    // The editor keeps its own history of text snapshots: the document's undo
    // stack is off, so the hanging-indent formatting never becomes an undo step.
    property var undoStack: []
    property var redoStack: []
    property string shadowText: ""   // text before the current change
    property int shadowCursor: 0
    property double lastEditTime: 0
    property bool forceBoundary: true
    property bool loading: false
    property bool restoring: false
    property bool compound: false        // inside one key press: a single step
    property bool compoundPushed: false

    function resetHistory() {
        undoStack = []
        redoStack = []
        shadowText = editor.text
        shadowCursor = editor.cursorPosition
        forceBoundary = true
    }
    // ------------------------------------------------------------ language server
    property int completionRequest: -1
    property int definitionRequest: -1
    property int formatRequest: -1
    property string formatText: ""
    property var pendingGoto: null      // {line, character} after opening another file
    property string lastTyped: ""

    function isWordText(s) {
        return /^[A-Za-z0-9_$]*$/.test(s)
    }
    function wordStartAt(pos) {
        const t = editor.text
        let i = pos
        while (i > 0 && /[A-Za-z0-9_$]/.test(t[i - 1]))
            --i
        return i
    }
    // computed from the current text, so a pending relayout cannot skew it
    function lspPosition(pos) {
        const t = editor.text
        let line = 0
        for (let i = t.indexOf("\n"); i >= 0 && i < pos; i = t.indexOf("\n", i + 1))
            ++line
        return { line: line, character: pos - (t.lastIndexOf("\n", pos - 1) + 1) }
    }
    property bool completionPending: false
    function requestCompletion() {
        if (Backend.docKind !== "qml" || !Lsp.running)
            return
        const ws = wordStartAt(editor.cursorPosition)
        // one request per word: the answer is filtered by whatever was typed
        // by the time it arrives
        if (completionPending && ws === completion.wordStart)
            return
        const p = lspPosition(editor.cursorPosition)
        completion.wordStart = ws
        completionPending = true
        completionRequest = Lsp.complete(p.line, p.character)
    }
    // after each typed character: refine an open list, or open one after "."
    // or after three characters of a word, like Kate's auto-completion
    function afterTyping() {
        const typed = lastTyped
        lastTyped = ""
        if (typed === "" || Backend.docKind !== "qml")
            return
        if (completion.opened) {
            if (typed === ".")
                requestCompletion()
            else if (isWordText(typed))
                completion.refilter()
            else
                completion.close()
            return
        }
        if (typed === ".") {
            requestCompletion()
        } else if (/^[A-Za-z_$]$/.test(typed) || /^[0-9]$/.test(typed)) {
            const ws = wordStartAt(editor.cursorPosition)
            if (editor.cursorPosition - ws >= 3 && /[A-Za-z_$]/.test(editor.text[ws]))
                requestCompletion()
        }
    }
    Connections {
        target: Lsp
        function onCompletionReady(rid, items) {
            if (rid !== pane.completionRequest || !pane.active)
                return
            pane.completionPending = false
            const ws = completion.wordStart
            if (editor.cursorPosition < ws || !pane.isWordText(editor.text.substring(ws, editor.cursorPosition)))
                return
            completion.show(items, ws)
        }
        function onDefinitionReady(rid, path, line, character) {
            if (rid !== pane.definitionRequest)
                return
            if (line === -2)
                return  // the server explained why (requestFailed)
            if (!path || line < 0) {
                applicationWindow().showPassiveNotification(qsTr("No definition found"))
                return
            }
            if (path === Backend.filePath) {
                pane.gotoPosition(line, character)
                return
            }
            // in another file: open it in Kreator at the definition
            pane.pendingGoto = { line: line, character: character }
            if (!applicationWindow().switchFile(path))
                pane.pendingGoto = null
        }
        function onReferencesReady(rid, items) {
            if (rid !== pane.referencesRequest)
                return
            searchBar.visible = false
            gotoBar.visible = false
            refsPanel.show(pane.referencesSymbol, items)
        }
        function onRenameReady(rid, here, others) {
            if (rid !== pane.renameRequest)
                return
            if (!here.length && !others.length)
                return  // the server explained why (requestFailed)
            if (editor.text !== pane.renameText) {
                Lsp.discardRename(rid)
                applicationWindow().showPassiveNotification(qsTr("The text changed while renaming; try again"))
                return
            }
            if (others.length) {
                renameConfirm.rid = rid
                renameConfirm.here = here
                renameConfirm.others = others
                renameConfirm.newName = pane.renameNewName
                renameConfirm.open()
                return
            }
            Lsp.discardRename(rid)
            pane.applyServerEdits(here, pane.renameText)
            applicationWindow().showPassiveNotification(qsTr("Renamed %n occurrence(s)", "", here.length))
            pane.afterRename()
        }
        function onRequestFailed(message) {
            if (message)
                applicationWindow().showPassiveNotification(qsTr("qmlls: %1").arg(message), "long")
        }
        function onFormattingReady(rid, edits) {
            if (rid !== pane.formatRequest)
                return
            if (editor.text !== pane.formatText) {
                applicationWindow().showPassiveNotification(qsTr("The text changed while formatting; try again"))
                return
            }
            if (!edits.length) {
                applicationWindow().showPassiveNotification(qsTr("Already formatted"))
                return
            }
            pane.applyServerEdits(edits, pane.formatText)
        }
    }
    // apply edits from the server to the current text (one undo step);
    // `expected` is the text the request was made for
    function applyServerEdits(edits, expected) {
        if (editor.text !== expected) {
            applicationWindow().showPassiveNotification(qsTr("The text changed in the meantime; try again"))
            return false
        }
        relayout()
        const starts = lineStarts
        const off = (l, c) => (l < starts.length ? starts[l] : editor.length) + c
        const sorted = edits.slice().sort((a, b) => off(b.startLine, b.startChar) - off(a.startLine, a.startChar))
        const keep = lspPosition(editor.cursorPosition)
        beginStep()
        for (const e of sorted) {
            const a = off(e.startLine, e.startChar), b = off(e.endLine, e.endChar)
            editor.remove(a, b)
            editor.insert(a, e.text)
        }
        endStep()
        relayout()
        gotoPosition(keep.line, keep.character)
        return true
    }

    // ---- references & rename
    property int referencesRequest: -1
    property string referencesSymbol: ""
    property int renameRequest: -1
    property string renameText: ""
    property string renameNewName: ""

    function wordAt(pos) {
        const t = editor.text
        const a = wordStartAt(pos)
        let b = pos
        while (b < t.length && /[A-Za-z0-9_$]/.test(t[b]))
            ++b
        return { start: a, end: b, text: t.substring(a, b) }
    }
    function findReferences() {
        if (!Lsp.running || Backend.docKind !== "qml")
            return
        const w = wordAt(editor.cursorPosition)
        if (w.text === "") {
            applicationWindow().showPassiveNotification(qsTr("Place the cursor on a name"))
            return
        }
        referencesSymbol = w.text
        const p = lspPosition(w.start)
        referencesRequest = Lsp.references(p.line, p.character)
    }
    function startRename() {
        if (!Lsp.running || Backend.docKind !== "qml")
            return
        const w = wordAt(editor.cursorPosition)
        if (w.text === "" || !/^[A-Za-z_$]/.test(w.text)) {
            applicationWindow().showPassiveNotification(qsTr("Place the cursor on a name"))
            return
        }
        searchBar.visible = false
        gotoBar.visible = false
        renameBar.open(w.text, w.start)
    }
    function requestRename(pos, name) {
        relayout()
        renameText = editor.text
        renameNewName = name
        const p = lspPosition(pos)
        renameRequest = Lsp.rename(p.line, p.character, name)
    }
    function afterRename() {
        // show where the new name is used now
        if (refsPanel.visible) {
            editor.cursorPosition = renameBar.startPos
            Qt.callLater(findReferences)
        }
    }
    function gotoReference(ref) {
        if (ref.current) {
            gotoPosition(ref.line, ref.character)
            editor.select(editor.cursorPosition, editor.cursorPosition + ref.match.length)
            return
        }
        pendingGoto = { line: ref.line, character: ref.character }
        if (!applicationWindow().switchFile(ref.path))
            pendingGoto = null
    }
    readonly property var referenceMarks: {
        layoutRevision
        if (!refsPanel.visible)
            return []
        const starts = lineStarts
        const top = flick.contentY - 50, bottom = flick.contentY + flick.height + 50
        const out = []
        for (const r of refsPanel.results) {
            if (!r.current || hiddenLines[r.line] || starts[r.line] === undefined || lineTops[r.line] < top || lineTops[r.line] > bottom)
                continue
            const a = starts[r.line] + r.character
            const ra = editor.positionToRectangle(a), rb = editor.positionToRectangle(a + r.match.length)
            out.push({ x: ra.x, y: ra.y, h: ra.height, w: Math.max(2, Math.abs(ra.y - rb.y) < 1 ? rb.x - ra.x : 8) })
        }
        return out
    }

    function gotoPosition(line, character) {
        relayout()
        const starts = lineStarts
        const l = Math.max(0, Math.min(starts.length - 1, line))
        const end = l + 1 < starts.length ? starts[l + 1] - 1 : editor.length
        editor.cursorPosition = Math.min(end, starts[l] + character)
        showWithContext(editor.cursorPosition)
        editor.forceActiveFocus()
    }
    function gotoDefinition() {
        if (!Lsp.running || Backend.docKind !== "qml")
            return
        const p = lspPosition(editor.cursorPosition)
        definitionRequest = Lsp.definition(p.line, p.character)
    }
    function formatDocument() {
        if (!Lsp.running)
            return
        relayout()
        formatText = editor.text
        formatRequest = Lsp.format(indentWidth)
    }

    // diagnostics as text offsets; one per line for the gutter (the worst)
    readonly property var diagnosticLines: {
        const out = {}
        for (const d of Lsp.diagnostics) {
            const cur = out[d.line]
            const hasFix = (d.fixes && d.fixes.length > 0) || (cur && cur.hasFix)
            if (!cur || d.severity < cur.severity)
                out[d.line] = { severity: d.severity, message: d.message, hasFix: hasFix }
            else
                cur.hasFix = hasFix
        }
        return out
    }

    // ---- quick fixes (qmllint suggestions offered by qmlls as code actions)
    function fixesForLine(line) {
        const out = []
        const titles = {}
        for (const d of Lsp.diagnostics) {
            if (d.line !== line || !d.fixes)
                continue
            for (const f of d.fixes) {
                if (titles[f.title + f.edits[0].startChar])
                    continue
                titles[f.title + f.edits[0].startChar] = true
                out.push(f)
            }
        }
        return out
    }
    readonly property var safeFixes: {
        const out = []
        for (const d of Lsp.diagnostics) {
            const f = (d.fixes || []).find(x => x.auto)
            if (f)
                out.push(f)
        }
        return out
    }
    function openFixMenu(line, at) {
        const fixes = fixesForLine(line)
        if (!fixes.length) {
            applicationWindow().showPassiveNotification(qsTr("No quick fixes here"))
            return
        }
        fixMenu.fixes = fixes
        fixMenu.popup(editor, at.x, at.y)
    }
    function quickFixAtCursor() {
        if (Backend.docKind !== "qml")
            return
        const line = lspPosition(editor.cursorPosition).line
        const r = editor.cursorRectangle
        openFixMenu(line, Qt.point(r.x, r.y + r.height))
    }
    function fixesAreCurrent() {
        if (Lsp.isFixTextCurrent(editor.text))
            return true
        applicationWindow().showPassiveNotification(qsTr("The fixes are being updated; try again in a moment"))
        return false
    }
    function applyFix(fix) {
        if (!fixesAreCurrent())
            return
        relayout()
        const e = fix.edits[0]
        const start = lineStarts[e.startLine] + e.startChar
        if (!applyServerEdits(fix.edits, editor.text))
            return
        if (fix.placeholder !== "") {  // e.g. "<id>." — select "<id>" to type over it
            const i = editor.text.indexOf(fix.placeholder, start)
            if (i >= 0)
                editor.select(i, i + fix.placeholder.length)
        }
    }
    function applyAllSafeFixes() {
        const fixes = safeFixes
        if (!fixes.length || !fixesAreCurrent())
            return
        // all edits in one undo step; skip any that would overlap
        const edits = []
        const key = e => e.startLine * 1e6 + e.startChar
        for (const f of fixes)
            for (const e of f.edits)
                if (!edits.some(x => key(x) <= key(e) && key(e) < key(x) + Math.max(1, x.endChar - x.startChar) && x.startLine === e.startLine))
                    edits.push(e)
        if (applyServerEdits(edits, editor.text))
            applicationWindow().showPassiveNotification(qsTr("Applied %n fix(es)", "", fixes.length))
    }
    function diagnosticAt(pos) {
        const starts = lineStarts
        for (const d of Lsp.diagnostics) {
            const a = starts[d.line] + d.character
            let b = (starts[d.endLine] !== undefined ? starts[d.endLine] : a) + d.endCharacter
            if (b <= a)
                b = a + 1
            if (pos >= a && pos <= b)
                return d
        }
        return null
    }
    readonly property var diagnosticMarks: {
        layoutRevision
        const ds = Lsp.diagnostics
        if (!ds.length || Backend.docKind !== "qml")
            return []
        const starts = lineStarts
        const top = flick.contentY - 50, bottom = flick.contentY + flick.height + 50
        const out = []
        for (const d of ds) {
            if (hiddenLines[d.line] || starts[d.line] === undefined || lineTops[d.line] < top || lineTops[d.line] > bottom)
                continue
            const a = starts[d.line] + d.character
            let b = (starts[d.endLine] !== undefined ? starts[d.endLine] : a) + d.endCharacter
            if (b <= a) {  // empty range: mark the word there
                b = a
                while (b < editor.length && /[A-Za-z0-9_$.]/.test(editor.text[b]))
                    ++b
                if (b === a)
                    b = a + 1
            }
            const ra = editor.positionToRectangle(a), rb = editor.positionToRectangle(b)
            const sameRow = Math.abs(ra.y - rb.y) < 1
            out.push({ x: ra.x, y: ra.y, h: ra.height, severity: d.severity,
                       w: Math.max(4, sameRow ? rb.x - ra.x : editor.width - editor.rightPadding - ra.x) })
        }
        return out
    }
    function nextDiagnostic(dir) {
        const ds = Lsp.diagnostics
        if (!ds.length)
            return
        relayout()
        const starts = lineStarts
        const pos = editor.cursorPosition
        const offs = ds.map(d => starts[d.line] + d.character)
        let i = dir > 0 ? offs.findIndex(o => o > pos) : offs.map((o, k) => o < pos ? k : -1).filter(k => k >= 0).pop()
        if (i === undefined || i < 0)
            i = dir > 0 ? 0 : ds.length - 1
        editor.cursorPosition = offs[i]
        showWithContext(offs[i])
        diagTip.text = ds[i].message
        const r = editor.positionToRectangle(offs[i])
        diagTip.x = r.x
        diagTip.y = r.y + r.height + 2
        diagTip.visible = true
        diagTipHide.restart()
    }
    Timer {
        id: diagTipHide
        interval: 4000
        onTriggered: diagTip.visible = false
    }

    // scroll so `pos` is comfortably visible (a third from the top), like
    // Kate does for search results; no scrolling if it already is
    function showWithContext(pos) {
        const r = editor.positionToRectangle(pos)
        const margin = r.height * 3
        if (r.y >= flick.contentY + margin && r.y + r.height <= flick.contentY + flick.height - margin)
            return
        followCursor = false
        flick.contentY = Math.max(0, Math.min(flick.contentHeight - flick.height, r.y - flick.height / 3))
    }

    function beginStep() {  // several edits that undo as one (replace all, …)
        checkpoint()
        compound = true
        compoundPushed = false
    }
    function endStep() {
        if (compoundPushed)
            forceBoundary = true
        compound = false
    }
    function checkpoint() {  // the next change starts a new undo step
        forceBoundary = true
    }
    function recordEdit() {
        if (loading || restoring) {
            shadowText = editor.text
            return
        }
        const now = Date.now()
        // like Kate, typing is grouped; a pause, a new line or a bigger
        // operation (checkpoint) starts a new step
        const newLine = editor.text.split("\n").length !== shadowText.split("\n").length
        const merge = compound && compoundPushed
        if (!merge && (forceBoundary || newLine || now - lastEditTime > 1000 || undoStack.length === 0)) {
            const u = undoStack.slice(-199)
            u.push({ text: shadowText, cursor: shadowCursor })
            undoStack = u
            if (compound)
                compoundPushed = true
        }
        if (redoStack.length)
            redoStack = []
        forceBoundary = newLine
        lastEditTime = now
        shadowText = editor.text
        shadowCursor = editor.cursorPosition
    }
    function restore(state) {
        restoring = true
        editor.text = state.text
        editor.cursorPosition = Math.min(state.cursor, editor.length)
        restoring = false
        shadowText = editor.text
        shadowCursor = editor.cursorPosition
        forceBoundary = true
        scheduleLayout()
    }
    function undo() {
        if (!undoStack.length)
            return
        const u = undoStack.slice()
        const state = u.pop()
        redoStack = redoStack.concat([{ text: editor.text, cursor: editor.cursorPosition }])
        undoStack = u
        restore(state)
    }
    function redo() {
        if (!redoStack.length)
            return
        const r = redoStack.slice()
        const state = r.pop()
        undoStack = undoStack.concat([{ text: editor.text, cursor: editor.cursorPosition }])
        redoStack = r
        restore(state)
    }
    property bool wrapOverride: false
    property bool wrapOverridden: false
    readonly property bool wrap: wrapOverridden ? wrapOverride : (kate ? ks.dynamicWordWrap === true : false)
    function toggleWrap() {
        const on = !wrap  // read before overriding, which changes `wrap`
        wrapOverride = on
        wrapOverridden = true
    }

    // apply unapplied edits (before switching documents); false if they don't parse
    // edits not applied to the document yet ("" if none)
    function pendingText() {
        return active && dirty ? editor.text : ""
    }

    function commitPending() {
        if (!active || !dirty)
            return true
        if (Backend.applySource(editor.text)) {
            dirty = false
            return true
        }
        applicationWindow().showPassiveNotification(qsTr("The source has errors: fix them or press Revert first"), "long")
        return false
    }

    function load() {
        loading = true
        editor.text = Backend.sourceText
        loading = false
        resetHistory()
        dirty = false
        // unapplied edits from the last session
        const pending = Backend.takePendingSource()
        if (pending !== "") {
            loading = true
            editor.text = pending
            loading = false
            resetHistory()
            dirty = true
        }
        completion.close()
        Lsp.openDocument(Backend.filePath, editor.text, Backend.docKind === "qml")
        if (pendingGoto) {
            const g = pendingGoto
            pendingGoto = null
            Qt.callLater(() => gotoPosition(g.line, g.character))
            return
        }
        const line = Backend.lineOfSelected("")
        if (line > 0) {
            let pos = 0
            const lines = editor.text.split("\n")
            for (let i = 0; i < line - 1 && i < lines.length; ++i)
                pos += lines[i].length + 1
            editor.cursorPosition = pos
            Qt.callLater(() => {
                const r = editor.positionToRectangle(pos)
                flick.contentY = Math.max(0, r.y - flick.height / 3)
            })
        }
    }

    onActiveChanged: {
        Lsp.setWantSymbols(active)
        if (active) {
            load()
            editor.forceActiveFocus()
        } else if (dirty) {
            Backend.applySource(editor.text)
            dirty = false
        }
    }

    Connections {
        target: Backend
        function onContentChanged() {
            if (pane.active && !pane.dirty)
                pane.load()
        }
    }

    QQC2.ToolBar {
        Layout.fillWidth: true
        position: QQC2.ToolBar.Header

        RowLayout {
            anchors.fill: parent
            spacing: Kirigami.Units.smallSpacing

            QQC2.Label {
                Layout.fillWidth: true
                Layout.leftMargin: Kirigami.Units.smallSpacing
                elide: Text.ElideRight
                text: pane.dirty ? qsTr("Edited — apply to update the designer (Ctrl+Return)")
                                 : (pane.kate ? qsTr("Source of %1 · Kate style, %2").arg(Backend.fileName).arg(pane.ks.theme)
                                              : qsTr("Source of %1").arg(Backend.fileName))
                opacity: 0.8
            }
            QQC2.ToolButton {
                visible: Backend.docKind === "qml" && Lsp.enabled
                icon.name: !Lsp.running ? "dialog-information" : Lsp.errorCount ? "data-error" : Lsp.warningCount ? "data-warning" : "checkmark"
                text: !Lsp.running ? (Lsp.status || qsTr("No language server"))
                    : Lsp.errorCount + Lsp.warningCount === 0 ? qsTr("No problems")
                    : (Lsp.errorCount ? qsTr("%n error(s)", "", Lsp.errorCount) : "")
                      + (Lsp.errorCount && Lsp.warningCount ? ", " : "")
                      + (Lsp.warningCount ? qsTr("%n warning(s)", "", Lsp.warningCount) : "")
                enabled: Lsp.running && Lsp.errorCount + Lsp.warningCount > 0 || !Lsp.available
                onClicked: Lsp.available ? pane.nextDiagnostic(1) : applicationWindow().configureEditors()
                QQC2.ToolTip.text: !Lsp.available ? qsTr("Install qmlls (Qt's QML language server) for completion and diagnostics")
                                                  : qsTr("Diagnostics from qmlls. Next problem: F8, previous: Shift+F8")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.ToolButton {
                text: qsTr("Open in %1").arg(Backend.defaultEditorName)
                icon.name: Backend.defaultEditorIcon
                enabled: !pane.dirty
                onClicked: Backend.defaultEditorAvailable ? applicationWindow().openInEditor("") : applicationWindow().configureEditors()
                QQC2.ToolTip.text: pane.dirty ? qsTr("Apply or revert your edits first") : qsTr("Continue in %1 at the selected object (Ctrl+Shift+O)").arg(Backend.defaultEditorName)
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.ToolButton {
                text: qsTr("Word Wrap")
                icon.name: "text-wrap"
                display: QQC2.AbstractButton.IconOnly
                checkable: true
                checked: pane.wrap
                onToggled: {
                    pane.wrapOverridden = true
                    pane.wrapOverride = checked
                }
                QQC2.ToolTip.text: qsTr("Dynamic word wrap (F10)")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.ToolButton {
                text: qsTr("Revert")
                icon.name: "edit-undo"
                enabled: pane.dirty
                onClicked: pane.load()
            }
            QQC2.Button {
                text: qsTr("Apply")
                icon.name: "dialog-ok-apply"
                enabled: pane.dirty
                onClicked: {
                    if (Backend.applySource(editor.text))
                        pane.dirty = false
                }
                QQC2.ToolTip.text: qsTr("Apply (Ctrl+Return)")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
        }
    }

    Kirigami.InlineMessage {
        Layout.fillWidth: true
        Layout.margins: Kirigami.Units.smallSpacing
        type: Kirigami.MessageType.Error
        visible: Backend.sourceError !== ""
        text: Backend.sourceError
    }

    QQC2.ScrollView {
        id: scroll
        Layout.fillWidth: true
        Layout.fillHeight: true

        Kirigami.Theme.colorSet: Kirigami.Theme.View
        Kirigami.Theme.inherit: false
        // a scrollbar that comes and goes would change the width available for
        // wrapping, which changes the height, which shows/hides the scrollbar…
        QQC2.ScrollBar.vertical.policy: QQC2.ScrollBar.AlwaysOn

        background: Rectangle {
            color: pane.bg
        }

        Flickable {
            id: flick
            contentWidth: pane.wrap ? width : Math.max(width, row.implicitWidth)
            contentHeight: Math.max(height, editor.implicitHeight)
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            // With a mouse, dragging selects text (in any direction); only touch
            // drags scroll. The style's WheelHandler scrolls for wheels/touchpads.
            interactive: Kirigami.Settings.hasTransientTouchInput

            Row {
                id: row
                height: parent.height

                // line numbers, coloured like Kate's icon border
                Rectangle {
                    id: gutterBox
                    visible: pane.lineNumbers
                    width: visible ? gutterMetrics.advanceWidth(String(pane.lineTops.length || 1)) + Kirigami.Units.largeSpacing * 2 + pane.foldColumn : 0
                    height: Math.max(flick.height, editor.implicitHeight)
                    color: pane.gutterBg

                    FontMetrics {
                        id: gutterMetrics
                        font: editor.font
                    }
                    // only the numbers of visible lines are created; each sits at
                    // the top of its (possibly wrapped) line
                    Repeater {
                        model: pane.visibleLines
                        delegate: QQC2.Label {
                            required property var modelData
                            readonly property bool current: modelData.n === pane.currentLine
                            anchors.right: parent.right
                            anchors.rightMargin: Kirigami.Units.largeSpacing - Kirigami.Units.smallSpacing + pane.foldColumn
                            y: modelData.y
                            font: editor.font
                            color: current ? pane.currentLineNumberColor : pane.lineNumberColor
                            text: modelData.n
                        }
                    }
                    // diagnostics in the gutter
                    Repeater {
                        model: pane.visibleLines.filter(l => pane.diagnosticLines[l.n - 1] !== undefined)
                        delegate: Rectangle {
                            id: dot
                            required property var modelData
                            readonly property var diag: pane.diagnosticLines[modelData.n - 1]
                            x: Kirigami.Units.smallSpacing / 2
                            y: modelData.y + (fontMetrics.lineSpacing - height) / 2
                            width: Kirigami.Units.smallSpacing * 1.5
                            height: width
                            radius: width / 2
                            color: !diag || diag.hasFix ? "transparent" : (diag.severity === 1 ? pane.errorColor : pane.warningColor)
                            // a quick fix is available: lightbulb, click for the fixes
                            Kirigami.Icon {
                                visible: !!(dot.diag && dot.diag.hasFix)
                                anchors.centerIn: parent
                                width: Math.min(Kirigami.Units.iconSizes.small, fontMetrics.lineSpacing)
                                height: width
                                source: "games-hint"  // Breeze's lightbulb
                                color: dot.diag && dot.diag.severity === 1 ? pane.errorColor : pane.warningColor
                                isMask: true
                            }
                            HoverHandler {
                                id: dotHover
                                cursorShape: dot.diag && dot.diag.hasFix ? Qt.PointingHandCursor : Qt.ArrowCursor
                            }
                            TapHandler {
                                enabled: !!(dot.diag && dot.diag.hasFix)
                                onTapped: {
                                    const p = dot.mapToItem(editor, 0, dot.height)
                                    pane.openFixMenu(dot.modelData.n - 1, Qt.point(Math.max(0, p.x), p.y + Kirigami.Units.smallSpacing))
                                }
                            }
                            QQC2.ToolTip.text: !dot.diag ? "" : dot.diag.message + (dot.diag.hasFix ? "\n" + qsTr("Click or press Alt+Return for a quick fix") : "")
                            QQC2.ToolTip.visible: dotHover.hovered
                            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                        }
                    }
                    // folding markers
                    Repeater {
                        model: pane.visibleLines.filter(l => l.foldable)
                        delegate: Item {
                            id: marker
                            required property var modelData
                            anchors.right: parent.right
                            anchors.rightMargin: 1
                            y: modelData.y
                            width: pane.foldColumn
                            height: fontMetrics.lineSpacing
                            Kirigami.Icon {
                                anchors.centerIn: parent
                                width: Math.min(Kirigami.Units.iconSizes.small, parent.height)
                                height: width
                                source: marker.modelData.folded ? "go-next-symbolic" : "go-down-symbolic"
                                color: pane.lineNumberColor
                                isMask: true
                                opacity: marker.modelData.folded || markerHover.hovered || gutterHover.hovered ? 1 : 0.35
                            }
                            HoverHandler {
                                id: markerHover
                                cursorShape: Qt.PointingHandCursor
                            }
                            TapHandler {
                                onTapped: pane.toggleFold(marker.modelData.n - 1)
                            }
                            QQC2.ToolTip.text: marker.modelData.folded ? qsTr("Unfold (Ctrl++)") : qsTr("Fold (Ctrl+-)")
                            QQC2.ToolTip.visible: markerHover.hovered
                            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                        }
                    }
                    HoverHandler {
                        id: gutterHover
                    }
                    Rectangle {
                        anchors.right: parent.right
                        width: 1
                        height: parent.height
                        color: pane.separatorColor
                    }
                }

                // A plain TextEdit: QQC2.TextArea ignores purely vertical mouse
                // drags (in every style), so selecting lines by dragging down
                // would not work with it.
                TextEdit {
                    id: editor
                    width: pane.wrap ? flick.width - x : Math.max(flick.width - x, pane.unwrappedWidth)
                    // cached, not bound: while wrapping is switched, contentWidth
                    // briefly depends on width
                    onContentWidthChanged: if (wrapMode === TextEdit.NoWrap) pane.unwrappedWidth = contentWidth + leftPadding + rightPadding
                    onWrapModeChanged: if (wrapMode === TextEdit.NoWrap) pane.unwrappedWidth = contentWidth + leftPadding + rightPadding
                    height: Math.max(flick.height, implicitHeight)
                    font: pane.editorFont
                    color: pane.textColor
                    selectionColor: pane.selectionColor
                    selectedTextColor: pane.selectedTextColor
                    wrapMode: pane.wrap ? TextEdit.Wrap : TextEdit.NoWrap
                    textFormat: TextEdit.PlainText
                    selectByMouse: true
                    persistentSelection: true
                    tabStopDistance: pane.indentWidth * fontMetrics.advanceWidth(" ")
                    leftPadding: Kirigami.Units.smallSpacing * 2
                    rightPadding: Kirigami.Units.smallSpacing * 2
                    topPadding: Kirigami.Units.smallSpacing
                    bottomPadding: Kirigami.Units.smallSpacing
                    activeFocusOnPress: true
                    activeFocusOnTab: true
                    Rectangle {  // background
                        z: -1
                        anchors.fill: parent
                        color: pane.bg
                        Rectangle {  // current line, all of its wrapped parts
                            y: pane.currentLineTop
                            width: parent.width
                            height: pane.currentLineHeight
                            color: pane.currentLineColor
                        }
                        // references (Find References) in this file
                        Repeater {
                            model: pane.referenceMarks
                            delegate: Rectangle {
                                required property var modelData
                                x: modelData.x
                                y: modelData.y
                                width: modelData.w
                                height: modelData.h
                                color: Qt.rgba(pane.selectionColor.r, pane.selectionColor.g, pane.selectionColor.b, 0.45)
                                border.width: 1
                                border.color: pane.selectionColor
                                radius: 2
                            }
                        }
                        // search matches on screen
                        Repeater {
                            model: pane.searchHighlights
                            delegate: Rectangle {
                                required property var modelData
                                x: modelData.x
                                y: modelData.y
                                width: modelData.w
                                height: modelData.h
                                color: pane.searchColor
                                radius: 2
                            }
                        }
                        // matching brackets around the cursor
                        Repeater {
                            model: pane.matchedBrackets
                            delegate: Rectangle {
                                required property int modelData
                                readonly property rect r: { pane.layoutRevision; return editor.positionToRectangle(modelData) }
                                readonly property rect next: { pane.layoutRevision; return editor.positionToRectangle(modelData + 1) }
                                x: r.x
                                y: r.y
                                width: Math.abs(next.y - r.y) < 1 && next.x > r.x ? next.x - r.x : fontMetrics.advanceWidth(editor.text[modelData] || " ")
                                height: r.height
                                color: pane.bracketColor
                                border.width: 1
                                border.color: Qt.rgba(pane.textColor.r, pane.textColor.g, pane.textColor.b, 0.35)
                                radius: 2
                            }
                        }
                    }
                    HoverHandler {
                        cursorShape: Qt.IBeamCursor
                    }
                    QQC2.Menu {
                        id: fixMenu
                        property var fixes: []
                        Instantiator {
                            model: fixMenu.fixes
                            delegate: QQC2.MenuItem {
                                required property var modelData
                                text: modelData.title
                                icon.name: modelData.auto ? "tools-wizard" : "games-hint"
                                QQC2.ToolTip.text: modelData.detail
                                QQC2.ToolTip.visible: hovered && modelData.detail !== modelData.title
                                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                                onTriggered: pane.applyFix(modelData)
                            }
                            onObjectAdded: (index, object) => fixMenu.insertItem(index, object)
                            onObjectRemoved: (index, object) => fixMenu.removeItem(object)
                        }
                        QQC2.MenuSeparator {
                            visible: pane.safeFixes.length > 1
                        }
                        QQC2.MenuItem {
                            visible: pane.safeFixes.length > 1
                            height: visible ? implicitHeight : 0
                            text: qsTr("Apply All Safe Fixes (%1)").arg(pane.safeFixes.length)
                            icon.name: "tools-wizard"
                            onTriggered: pane.applyAllSafeFixes()
                        }
                    }
                    CompletionPopup {
                        id: completion
                        editor: editor
                        pane: pane
                    }
                    // go to definition with Ctrl+click
                    TapHandler {
                        acceptedModifiers: Qt.ControlModifier
                        onTapped: eventPoint => {
                            editor.cursorPosition = editor.positionAt(eventPoint.position.x, eventPoint.position.y)
                            pane.gotoDefinition()
                        }
                    }
                    // language server messages under the mouse
                    HoverHandler {
                        id: textHover
                        onPointChanged: diagTipTimer.restart()
                        onHoveredChanged: if (!hovered) diagTip.visible = false
                    }
                    Timer {
                        id: diagTipTimer
                        interval: 400
                        onTriggered: {
                            const p = textHover.point.position
                            const d = pane.diagnosticAt(editor.positionAt(p.x, p.y))
                            if (d) {
                                diagTip.text = d.message + (d.fixes && d.fixes.length ? "\n" + qsTr("Alt+Return: quick fix") : "")
                                diagTip.x = p.x
                                diagTip.y = p.y + fontMetrics.height
                                diagTip.visible = true
                            } else {
                                diagTip.visible = false
                            }
                        }
                    }
                    QQC2.ToolTip {
                        id: diagTip
                    }
                    // diagnostics: underlines (errors red, warnings in the neutral colour)
                    Repeater {
                        model: pane.diagnosticMarks
                        delegate: Rectangle {
                            required property var modelData
                            z: 1
                            x: modelData.x
                            y: modelData.y + modelData.h - 2
                            width: modelData.w
                            height: 2
                            radius: 1
                            color: modelData.severity === 1 ? pane.errorColor : pane.warningColor
                        }
                    }
                    // "… }" after a folded line; click to unfold
                    Repeater {
                        model: pane.foldBadges
                        delegate: Rectangle {
                            id: badge
                            required property var modelData
                            z: 2
                            x: modelData.rect.x + fontMetrics.advanceWidth(" ")
                            y: modelData.rect.y + 1
                            width: badgeLabel.implicitWidth + Kirigami.Units.smallSpacing * 4
                            height: modelData.rect.height - 2
                            radius: 3
                            color: badgeHover.hovered ? Qt.rgba(pane.textColor.r, pane.textColor.g, pane.textColor.b, 0.18)
                                                      : Qt.rgba(pane.textColor.r, pane.textColor.g, pane.textColor.b, 0.08)
                            border.width: 1
                            border.color: Qt.rgba(pane.textColor.r, pane.textColor.g, pane.textColor.b, 0.3)
                            Text {
                                id: badgeLabel
                                anchors.centerIn: parent
                                text: badge.modelData.text
                                font: editor.font
                                color: pane.lineNumberColor
                            }
                            HoverHandler {
                                id: badgeHover
                                cursorShape: Qt.PointingHandCursor
                            }
                            TapHandler {
                                onTapped: pane.toggleFold(badge.modelData.line)
                            }
                        }
                    }
                    TapHandler {
                        acceptedButtons: Qt.RightButton
                        onTapped: eventPoint => {
                            editor.forceActiveFocus()
                            contextMenu.popup()
                        }
                    }
                    QQC2.Menu {
                        id: contextMenu
                        QQC2.MenuItem {
                            text: qsTr("Undo")
                            icon.name: "edit-undo"
                            enabled: pane.undoStack.length > 0
                            onTriggered: pane.undo()
                        }
                        QQC2.MenuItem {
                            text: qsTr("Redo")
                            icon.name: "edit-redo"
                            enabled: pane.redoStack.length > 0
                            onTriggered: pane.redo()
                        }
                        QQC2.MenuSeparator {}
                        QQC2.MenuItem {
                            text: qsTr("Cut")
                            icon.name: "edit-cut"
                            enabled: editor.selectedText !== ""
                            onTriggered: {
                                pane.checkpoint()
                                editor.cut()
                            }
                        }
                        QQC2.MenuItem {
                            text: qsTr("Copy")
                            icon.name: "edit-copy"
                            enabled: editor.selectedText !== ""
                            onTriggered: editor.copy()
                        }
                        QQC2.MenuItem {
                            text: qsTr("Paste")
                            icon.name: "edit-paste"
                            enabled: editor.canPaste
                            onTriggered: {
                                pane.checkpoint()
                                editor.paste()
                            }
                        }
                        QQC2.MenuSeparator {}
                        QQC2.MenuItem {
                            text: qsTr("Select All")
                            icon.name: "edit-select-all"
                            onTriggered: editor.selectAll()
                        }
                        QQC2.MenuSeparator {
                            visible: Lsp.running && Backend.docKind === "qml"
                        }
                        QQC2.MenuItem {
                            text: qsTr("Go to Definition")
                            icon.name: "go-jump-definition"
                            visible: Lsp.running && Backend.docKind === "qml"
                            height: visible ? implicitHeight : 0
                            onTriggered: pane.gotoDefinition()
                        }
                        QQC2.MenuItem {
                            text: qsTr("Quick Fix…")
                            icon.name: "games-hint"
                            visible: Lsp.running && Backend.docKind === "qml" && pane.fixesForLine(pane.lspPosition(editor.cursorPosition).line).length > 0
                            height: visible ? implicitHeight : 0
                            onTriggered: pane.quickFixAtCursor()
                        }
                        QQC2.MenuItem {
                            text: qsTr("Apply All Safe Fixes (%1)").arg(pane.safeFixes.length)
                            icon.name: "tools-wizard"
                            visible: Lsp.running && Backend.docKind === "qml" && pane.safeFixes.length > 0
                            height: visible ? implicitHeight : 0
                            onTriggered: pane.applyAllSafeFixes()
                        }
                        QQC2.MenuItem {
                            text: qsTr("Find References")
                            icon.name: "edit-find"
                            visible: Lsp.running && Backend.docKind === "qml"
                            height: visible ? implicitHeight : 0
                            onTriggered: pane.findReferences()
                        }
                        QQC2.MenuItem {
                            text: qsTr("Rename…")
                            icon.name: "edit-rename"
                            visible: Lsp.running && Backend.docKind === "qml"
                            height: visible ? implicitHeight : 0
                            onTriggered: pane.startRename()
                        }
                        QQC2.MenuItem {
                            text: qsTr("Format Document")
                            icon.name: "format-indent-more"
                            visible: Lsp.running && Backend.docKind === "qml"
                            height: visible ? implicitHeight : 0
                            onTriggered: pane.formatDocument()
                        }
                        QQC2.MenuSeparator {}
                        QQC2.MenuItem {
                            text: qsTr("Fold Top-Level Blocks")
                            icon.name: "collapse-all"
                            onTriggered: pane.foldTopLevel(true)
                        }
                        QQC2.MenuItem {
                            text: qsTr("Unfold All")
                            icon.name: "expand-all"
                            enabled: pane.folds.length > 0
                            onTriggered: pane.unfoldAll()
                        }
                        QQC2.MenuItem {
                            text: pane.wrap ? qsTr("Turn Off Word Wrap") : qsTr("Turn On Word Wrap")
                            icon.name: "text-wrap"
                            onTriggered: pane.toggleWrap()
                        }
                    }
                    Accessible.name: qsTr("Source code")
                    onTextChanged: {
                        if (text === pane.shadowText)
                            return  // formatting only (hanging indents, folding)
                        pane.followCursor = true
                        if (activeFocus || text !== Backend.sourceText)
                            pane.dirty = text !== Backend.sourceText
                        if (pane.loading)
                            pane.folds = []
                        else
                            pane.mapFolds(pane.shadowText, text)
                        pane.recordEdit()
                        pane.scheduleLayout()
                        if (!pane.loading)  // loading reopens the document; undo/redo are changes
                            Lsp.changeDocument(text)
                        Qt.callLater(pane.afterTyping)
                    }
                    onCursorPositionChanged: {
                        pane.followCursor = true
                        if (completion.opened && (cursorPosition < completion.wordStart || !pane.isWordText(text.substring(completion.wordStart, cursorPosition))))
                            completion.close()
                        if (text === pane.shadowText)
                            pane.shadowCursor = cursorPosition
                        if (!pane.loading)
                            Qt.callLater(pane.revealCursor)
                    }
                    Component.onCompleted: {
                        TextLayout.disableUndo(textDocument)
                        Lsp.attachDocument(textDocument)  // semantic highlighting
                        Lsp.setSemanticTheme(pane.themeName)
                    }

                    // Kate's "Animate bracket matching": the matching bracket
                    // appears enlarged and shrinks into place
                    Item {
                        id: bracketPulse
                        z: 3
                        visible: false
                        property int pos: -1
                        property rect r
                        x: r.x
                        y: r.y
                        width: Math.max(r.width, fontMetrics.advanceWidth(editor.text[pos] || " "))
                        height: r.height
                        transformOrigin: Item.Center
                        Rectangle {
                            anchors.centerIn: parent
                            width: parent.width + 2
                            height: parent.height
                            radius: 2
                            color: pane.bracketColor
                            border.width: 1
                            border.color: Qt.rgba(pane.textColor.r, pane.textColor.g, pane.textColor.b, 0.5)
                        }
                        Text {
                            anchors.centerIn: parent
                            text: editor.text[bracketPulse.pos] || ""
                            font.family: editor.font.family
                            font.pointSize: editor.font.pointSize
                            font.bold: true
                            color: pane.textColor
                        }
                        SequentialAnimation {
                            id: pulseAnimation
                            ParallelAnimation {
                                NumberAnimation { target: bracketPulse; property: "scale"; from: 2.0; to: 1.0; duration: 220; easing.type: Easing.OutCubic }
                                NumberAnimation { target: bracketPulse; property: "opacity"; from: 0.6; to: 1.0; duration: 120 }
                            }
                            NumberAnimation { target: bracketPulse; property: "opacity"; to: 0; duration: 140 }
                            PropertyAction { target: bracketPulse; property: "visible"; value: false }
                        }
                        function play(position) {
                            pulseAnimation.stop()
                            pos = position
                            r = editor.positionToRectangle(position)
                            scale = 2.0
                            opacity = 0.6
                            visible = true
                            pulseAnimation.start()
                        }
                    }
                    onWidthChanged: pane.scheduleLayout()
                    onFontChanged: pane.scheduleLayout()
                    Keys.onPressed: event => pane.handleKey(event)
                    // Follow the caret only when it moved or text was typed — not when
                    // the layout changes (folding, wrapping, resizing), which also
                    // reports a new cursor rectangle and would make the view jump.
                    onCursorRectangleChanged: {
                        if (!pane.followCursor)
                            return
                        pane.followCursor = false
                        const r = cursorRectangle
                        if (r.y < flick.contentY)
                            flick.contentY = r.y
                        else if (r.y + r.height > flick.contentY + flick.height)
                            flick.contentY = r.y + r.height - flick.height
                    }
                    FontMetrics {
                        id: fontMetrics
                        font: editor.font
                    }

                    // keep selecting while the mouse is held beyond the top or
                    // bottom edge, scrolling the view like Kate does
                    PointHandler {
                        id: selectPoint
                        objectName: "selectPoint"
                        acceptedButtons: Qt.LeftButton
                        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                    }
                    Timer {
                        interval: 30
                        repeat: true
                        running: selectPoint.active
                        onTriggered: {
                            // scene position: the editor itself moves while scrolling
                            const p = flick.mapFromItem(null, selectPoint.point.scenePosition.x, selectPoint.point.scenePosition.y)
                            let dy = 0
                            if (p.y < 0)
                                dy = Math.max(-40, p.y / 2)
                            else if (p.y > flick.height)
                                dy = Math.min(40, (p.y - flick.height) / 2)
                            if (dy === 0)
                                return
                            flick.contentY = Math.max(0, Math.min(flick.contentHeight - flick.height, flick.contentY + dy))
                            const ep = flick.mapToItem(editor, p.x, Math.max(0, Math.min(flick.height - 1, p.y)))
                            editor.moveCursorSelection(editor.positionAt(ep.x, ep.y), TextEdit.SelectCharacters)
                        }
                    }
                }
            }
        }
    }

    SearchBar {
        id: searchBar
        Layout.fillWidth: true
        editor: editor
        pane: pane
    }
    GotoLineBar {
        id: gotoBar
        Layout.fillWidth: true
        editor: editor
        pane: pane
    }
    RenameBar {
        id: renameBar
        Layout.fillWidth: true
        editor: editor
        pane: pane
    }
    ReferencesPanel {
        id: refsPanel
        Layout.fillWidth: true
        pane: pane
    }

    // a rename that changes other files too: ask first, they are written to disk
    Kirigami.PromptDialog {
        id: renameConfirm
        property int rid: -1
        property var here: []
        property var others: []
        property string newName: ""
        title: qsTr("Rename in Other Files?")
        subtitle: qsTr("Renaming to “%1” also changes these files, which are saved right away:\n\n%2")
                  .arg(newName).arg(others.map(o => "• " + o.fileName + " (" + o.count + ")").join("\n"))
        standardButtons: Kirigami.Dialog.NoButton
        customFooterActions: [
            Kirigami.Action {
                objectName: "confirmRenameAction"
                text: qsTr("Rename")
                icon.name: "edit-rename"
                onTriggered: {
                    renameConfirm.close()
                    const err = Lsp.applyRenameToFiles(renameConfirm.rid)
                    if (err !== "")
                        applicationWindow().showPassiveNotification(qsTr("Could not rename in %1").arg(err), "long")
                    pane.applyServerEdits(renameConfirm.here, pane.renameText)
                    applicationWindow().showPassiveNotification(qsTr("Renamed in %n other file(s)", "", renameConfirm.others.length))
                    pane.afterRename()
                }
            },
            Kirigami.Action {
                text: qsTr("Cancel")
                icon.name: "dialog-cancel"
                onTriggered: {
                    Lsp.discardRename(renameConfirm.rid)
                    renameConfirm.close()
                }
            }
        ]
    }

    // ------------------------------------------------------------ line layout
    // Top of every logical line (they differ from visual lines when wrapping).
    property var lineTops: []
    property var lineStarts: []

    function scheduleLayout() {
        layoutTimer.restart()
    }
    Timer {
        id: layoutTimer
        interval: 0
        onTriggered: pane.relayout()
    }
    // ------------------------------------------------------------ bracket matching
    // Pairs of (), [] and {} — ignoring brackets in strings and comments, as
    // Kate does — computed once per text change; the cursor only looks them up.
    property var bracketPairs: ({})
    property string bracketText: ""
    property int layoutRevision: 0

    function computeBrackets(t) {
        const pairs = {}
        const stack = []
        const xml = Backend.docKind === "ui"
        const open = { "(": ")", "[": "]", "{": "}" }
        const n = t.length
        let i = 0
        while (i < n) {
            const c = t[i]
            if (xml) {
                if (t.startsWith("<!--", i)) {
                    const e = t.indexOf("-->", i + 4)
                    i = e < 0 ? n : e + 3
                    continue
                }
                if (c === '"') {
                    const e = t.indexOf('"', i + 1)
                    i = e < 0 ? n : e + 1
                    continue
                }
            } else {
                if (c === "/" && t[i + 1] === "/") {
                    const e = t.indexOf("\n", i)
                    i = e < 0 ? n : e
                    continue
                }
                if (c === "/" && t[i + 1] === "*") {
                    const e = t.indexOf("*/", i + 2)
                    i = e < 0 ? n : e + 2
                    continue
                }
                if (c === '"' || c === "'" || c === "`") {
                    let j = i + 1
                    while (j < n && t[j] !== c && (c === "`" || t[j] !== "\n"))
                        j += t[j] === "\\" ? 2 : 1
                    i = j + 1
                    continue
                }
            }
            if (open[c] !== undefined) {
                stack.push(i)
            } else if (c === ")" || c === "]" || c === "}") {
                // pop to the nearest matching opener (tolerates stray brackets)
                for (let k = stack.length - 1; k >= 0; --k) {
                    if (open[t[stack[k]]] === c) {
                        pairs[stack[k]] = i
                        pairs[i] = stack[k]
                        stack.length = k
                        break
                    }
                }
            }
            ++i
        }
        return pairs
    }

    // theme for semantic highlighting: the same one the syntax highlighter uses
    readonly property string themeName: kate ? ks.theme
        : (Kirigami.ColorUtils.brightnessForColor(Kirigami.Theme.backgroundColor) === Kirigami.ColorUtils.Dark ? "Breeze Dark" : "Breeze Light")
    onThemeNameChanged: Lsp.setSemanticTheme(themeName)

    readonly property bool animateBrackets: kate ? ks.animateBrackets === true : true
    property string lastBracketPair: ""
    onMatchedBracketsChanged: {
        const m = matchedBrackets
        const key = m.length === 2 ? m[0] + "-" + m[1] : ""
        if (key === lastBracketPair)
            return
        lastBracketPair = key
        if (key === "" || !animateBrackets || !active)
            return
        // animate the other end, if it is on screen
        const r = editor.positionToRectangle(m[1])
        if (r.y >= flick.contentY && r.y + r.height <= flick.contentY + flick.height)
            bracketPulse.play(m[1])
    }

    readonly property var matchedBrackets: {
        const p = editor.cursorPosition
        const pairs = bracketPairs
        if (editor.selectionStart !== editor.selectionEnd)
            return []
        let pair = []
        if (pairs[p] !== undefined)  // bracket after the cursor first, like Kate
            pair = [p, pairs[p]]
        else if (p > 0 && pairs[p - 1] !== undefined)
            pair = [p - 1, pairs[p - 1]]
        const hidden = hiddenLines
        return pair.filter(pos => !hidden[lineIndexAt(pos)])  // not inside folded code
    }

    function relayout() {
        const t = editor.text
        const starts = [0]
        for (let i = t.indexOf("\n"); i >= 0; i = t.indexOf("\n", i + 1))
            starts.push(i + 1)
        lineStarts = starts
        if (t !== bracketText) {
            bracketPairs = computeBrackets(t)
            foldRegions = computeFoldRegions(t)
            bracketText = t
            validateFolds()
        }
        const hidden = hiddenLineSet()
        TextLayout.setHiddenLines(editor.textDocument, Object.keys(hidden))
        TextLayout.applyHangingIndent(editor.textDocument, indentWidth, alignIndentPercent, wrap)

        // top of every visible logical line; -1 for folded-away lines
        const tops = new Array(starts.length)
        if (wrap) {
            for (let i = 0; i < starts.length; ++i)
                tops[i] = hidden[i] ? -1 : editor.positionToRectangle(starts[i]).y
        } else {
            const first = editor.positionToRectangle(0)
            const h = fontMetrics.lineSpacing
            let row = 0
            for (let i = 0; i < starts.length; ++i)
                tops[i] = hidden[i] ? -1 : first.y + (row++) * h
        }
        hiddenLines = hidden
        lineTops = tops
        layoutRevision++
    }

    // ------------------------------------------------------------ code folding
    // Regions: {…} and […] spanning lines (QML/JS) or elements (XML), keyed by
    // their first line. A folded region hides its following lines up to and
    // including the closing line; a badge "… }" stands in for them.
    property var foldRegions: ({})   // startLine -> { open, close, startLine, endLine, closing }
    property var folds: []           // folded regions: { open, close } offsets
    property var hiddenLines: ({})

    function computeFoldRegions(t) {
        const regions = {}
        const add = (open, close, closing) => {
            const sl = lineIndexAt(open), el = lineIndexAt(close)
            if (el <= sl)
                return
            const r = regions[sl]
            if (!r || close > r.close)  // outermost region of a line wins
                regions[sl] = { open: open, close: close, startLine: sl, endLine: el, closing: closing }
        }
        if (Backend.docKind === "ui") {
            const re = /<(\/?)([A-Za-z_][\w:.-]*)[^>]*?(\/?)>|<!--[\s\S]*?-->|<\?[\s\S]*?\?>/g
            const stack = []
            let m
            while ((m = re.exec(t)) !== null) {
                if (!m[2] || m[3] === "/")
                    continue
                if (m[1] === "") {
                    stack.push({ name: m[2], pos: m.index })
                } else {
                    for (let k = stack.length - 1; k >= 0; --k) {
                        if (stack[k].name === m[2]) {
                            add(stack[k].pos, m.index, "</" + m[2] + ">")
                            stack.length = k
                            break
                        }
                    }
                }
            }
        } else {
            const pairs = bracketPairs
            for (const k in pairs) {
                const open = Number(k), close = pairs[k]
                const c = t[open]
                if (close > open && (c === "{" || c === "["))
                    add(open, close, t[close])
            }
        }
        // what the badge shows: the rest of the closing line, e.g. "}" or "},"
        for (const k in regions) {
            const r = regions[k]
            const lineEndPos = t.indexOf("\n", r.close)
            r.closing = t.substring(r.close, lineEndPos < 0 ? t.length : lineEndPos).trim()
        }
        return regions
    }

    function hiddenLineSet() {
        const hidden = {}
        for (const f of folds) {
            const r = foldRegions[lineIndexAt(f.open)]
            if (!r)
                continue
            for (let l = r.startLine + 1; l <= r.endLine; ++l)
                hidden[l] = true
        }
        return hidden
    }
    function isFolded(line) {
        const r = foldRegions[line]
        return !!r && folds.some(f => f.open === r.open)
    }
    function toggleFold(line) {
        followCursor = false  // folding must not scroll to the caret
        const r = foldRegions[line]
        if (!r)
            return
        if (isFolded(line)) {
            folds = folds.filter(f => f.open !== r.open)
        } else {
            folds = folds.concat([{ open: r.open, close: r.close }])
            // keep the cursor out of the hidden lines
            const cl = lineIndexAt(editor.cursorPosition)
            if (cl > r.startLine && cl <= r.endLine)
                editor.cursorPosition = lineEnd(r.open)
        }
        relayout()
    }
    // region the cursor is in (innermost), for Ctrl+- / Ctrl++
    function regionAtCursor() {
        const pos = editor.cursorPosition
        let best = null
        for (const k in foldRegions) {
            const r = foldRegions[k]
            if (r.open <= pos && pos <= r.close + 1 && (!best || r.open > best.open))
                best = r
        }
        return best
    }
    function foldCurrent(fold) {
        const r = regionAtCursor()
        if (r && fold !== isFolded(r.startLine))
            toggleFold(r.startLine)
    }
    function topLevelRegions() {
        // regions directly inside the outermost one (the root object's children)
        const all = Object.values(foldRegions).sort((a, b) => a.open - b.open)
        if (!all.length)
            return []
        const root = all.reduce((a, b) => (b.close - b.open > a.close - a.open ? b : a))
        const out = []
        let lastClose = -1
        for (const r of all) {
            if (r === root || r.open <= lastClose || r.open < root.open || r.close > root.close)
                continue
            out.push(r)
            lastClose = r.close
        }
        return out
    }
    function foldTopLevel(fold) {
        followCursor = false  // folding must not scroll to the caret
        const top = topLevelRegions()
        if (fold) {
            const keep = folds.filter(f => !top.some(r => r.open === f.open))
            folds = keep.concat(top.map(r => ({ open: r.open, close: r.close })))
            const cl = lineIndexAt(editor.cursorPosition)
            for (const r of top)
                if (cl > r.startLine && cl <= r.endLine)
                    editor.cursorPosition = lineEnd(r.open)
        } else {
            folds = folds.filter(f => !top.some(r => r.open === f.open))
        }
        relayout()
    }
    function unfoldAll() {
        followCursor = false  // folding must not scroll to the caret
        folds = []
        relayout()
    }
    // keep folds attached to their code when text changes before them; drop
    // folds whose code was edited
    function mapFolds(oldText, newText) {
        if (!folds.length)
            return
        let p = 0
        const minLen = Math.min(oldText.length, newText.length)
        while (p < minLen && oldText[p] === newText[p])
            ++p
        let sfx = 0
        while (sfx < minLen - p && oldText[oldText.length - 1 - sfx] === newText[newText.length - 1 - sfx])
            ++sfx
        const oldEnd = oldText.length - sfx
        const delta = newText.length - oldText.length
        const out = []
        for (const f of folds) {
            if (f.close < p)
                out.push(f)
            else if (f.open >= oldEnd)
                out.push({ open: f.open + delta, close: f.close + delta })
            // else: the edit touched the folded code — unfold it
        }
        folds = out
    }
    function validateFolds() {
        folds = folds.filter(f => {
            const r = foldRegions[lineIndexAt(f.open)]
            return r && r.open === f.open && r.close === f.close
        })
    }
    // the cursor never stays inside folded code: unfold around it (like Kate)
    function revealCursor() {
        const line = lineIndexAt(editor.cursorPosition)
        if (!hiddenLines[line])
            return
        folds = folds.filter(f => {
            const r = foldRegions[lineIndexAt(f.open)]
            return !(r && line > r.startLine && line <= r.endLine)
        })
        relayout()
    }

    function lineIndexAt(pos) {  // binary search in lineStarts
        let lo = 0, hi = lineStarts.length - 1
        while (lo < hi) {
            const mid = (lo + hi + 1) >> 1
            if (lineStarts[mid] <= pos)
                lo = mid
            else
                hi = mid - 1
        }
        return lo
    }
    readonly property int currentLine: lineStarts.length ? lineIndexAt(editor.cursorPosition) + 1 : 1
    readonly property real currentLineTop: lineTops.length >= currentLine && lineTops[currentLine - 1] >= 0 ? lineTops[currentLine - 1] : editor.cursorRectangle.y
    readonly property real currentLineHeight: {
        for (let j = currentLine; j < lineTops.length; ++j)  // next visible line
            if (lineTops[j] >= 0)
                return lineTops[j] - currentLineTop
        return Math.max(editor.cursorRectangle.height, editor.contentHeight + editor.topPadding - currentLineTop)
    }
    readonly property var visibleLines: {
        const tops = lineTops
        const regions = foldRegions
        const folded = folds
        if (!tops.length)
            return []
        const top = flick.contentY - 100, bottom = flick.contentY + flick.height + 100
        // binary search on visible lines (hidden ones have top -1)
        let lo = 0, hi = tops.length - 1
        while (lo < hi) {
            const mid = (lo + hi + 1) >> 1
            let m = mid
            while (m > lo && tops[m] < 0)
                --m
            if (tops[m] <= top)
                lo = mid
            else
                hi = mid - 1
        }
        while (lo > 0 && tops[lo] < 0)
            --lo
        const out = []
        for (let i = lo; i < tops.length; ++i) {
            if (tops[i] < 0)
                continue
            if (tops[i] > bottom)
                break
            const r = regions[i]
            out.push({ n: i + 1, y: tops[i], foldable: !!r, folded: !!r && folded.some(f => f.open === r.open) })
        }
        return out
    }
    // search matches inside the visible area (not in folded code)
    readonly property var searchHighlights: {
        layoutRevision
        const ms = searchBar.matches
        if (!searchBar.visible || !ms.length)
            return []
        const from = editor.positionAt(0, flick.contentY)
        const to = editor.positionAt(editor.width, flick.contentY + flick.height)
        let lo = 0, hi = ms.length
        while (lo < hi) {  // first match ending after `from`
            const mid = (lo + hi) >> 1
            if (ms[mid].end < from)
                lo = mid + 1
            else
                hi = mid
        }
        const out = []
        for (let i = lo; i < ms.length && ms[i].start <= to && out.length < 500; ++i) {
            const m = ms[i]
            if (hiddenLines[lineIndexAt(m.start)])
                continue
            const a = editor.positionToRectangle(m.start)
            const b = editor.positionToRectangle(m.end)
            const sameRow = Math.abs(a.y - b.y) < 1
            out.push({ x: a.x, y: a.y, h: a.height, w: Math.max(2, sameRow ? b.x - a.x : editor.width - editor.rightPadding - a.x) })
        }
        return out
    }

    // badges for folded regions that are on screen
    readonly property var foldBadges: {
        layoutRevision
        const out = []
        for (const f of folds) {
            const line = lineIndexAt(f.open)
            const r = foldRegions[line]
            if (!r || lineTops[line] < 0)
                continue
            const endPos = lineStarts[line + 1] !== undefined ? lineStarts[line + 1] - 1 : editor.length
            // plain dots: monospace fonts (e.g. Hack) often lack "…", and the fallback
            // glyph is wider than measured
            out.push({ line: line, rect: editor.positionToRectangle(endPos), text: "... " + r.closing })
        }
        return out
    }
    onWrapChanged: scheduleLayout()

    // Kate's syntax highlighting engine and colour theme
    // Kate's highlighting engine — unless Kreator's own highlighter is active
    // (QML with semantic highlighting from qmlls, which needs one highlighter
    // for both layers; see semantic.py)
    Instantiator {
        active: !Lsp.ownHighlighting
        delegate: SyntaxHighlighter {
            textEdit: editor
            definition: Repository.definitionForName(Backend.docKind === "ui" ? "XML" : "QML")
            theme: pane.kate ? Repository.theme(pane.ks.theme)
                             : Repository.defaultTheme(Kirigami.ColorUtils.brightnessForColor(Kirigami.Theme.backgroundColor) === Kirigami.ColorUtils.Dark
                                                       ? Repository.DarkTheme : Repository.LightTheme)
        }
        // a removed highlighter clears every format: let ours paint again
        onObjectRemoved: Qt.callLater(Lsp.rehighlight)
    }

    // ------------------------------------------------------------ Kate-like editing
    function lineStart(pos) {
        return editor.text.lastIndexOf("\n", pos - 1) + 1
    }
    function lineEnd(pos) {
        const i = editor.text.indexOf("\n", pos)
        return i < 0 ? editor.text.length : i
    }
    function leadingWs(line) {
        return line.match(/^[ \t]*/)[0]
    }
    function wsWidth(ws) {
        let w = 0
        for (const c of ws)
            w = c === "\t" ? (Math.floor(w / indentWidth) + 1) * indentWidth : w + 1
        return w
    }
    function makeWs(width) {
        if (indentUnit === "\t")
            return "\t".repeat(Math.floor(width / indentWidth)) + " ".repeat(width % indentWidth)
        return " ".repeat(Math.max(0, width))
    }
    // replace the text of whole lines [from, to) keeping a sensible selection
    function editLines(fn) {
        const selStart = editor.selectionStart, selEnd = editor.selectionEnd
        const from = lineStart(selStart)
        const to = lineEnd(selEnd > selStart && editor.text[selEnd - 1] === "\n" ? selEnd - 1 : selEnd)
        const lines = editor.text.substring(from, to).split("\n")
        const out = lines.map(fn).join("\n")
        editor.remove(from, to)
        editor.insert(from, out)
        editor.select(from, from + out.length)
    }

    function handleKey(event) {
        compound = true
        compoundPushed = false
        try {
            handleKeyInner(event)
        } finally {
            if (compoundPushed)
                forceBoundary = true  // typing after an operation is a new step
            compound = false
        }
    }

    function handleKeyInner(event) {
        // completion list open: it gets the navigation keys
        if (completion.opened) {
            switch (event.key) {
            case Qt.Key_Up: completion.move(-1); event.accepted = true; return
            case Qt.Key_Down: completion.move(1); event.accepted = true; return
            case Qt.Key_PageUp: completion.move(-9); event.accepted = true; return
            case Qt.Key_PageDown: completion.move(9); event.accepted = true; return
            case Qt.Key_Return:
            case Qt.Key_Enter:
            case Qt.Key_Tab: completion.accept(); event.accepted = true; return
            case Qt.Key_Escape: completion.close(); event.accepted = true; return
            }
        }
        if (((event.modifiers & Qt.AltModifier) && (event.key === Qt.Key_Return || event.key === Qt.Key_Enter))
                || ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_Period)) {
            quickFixAtCursor()
            event.accepted = true
            return
        }
        if ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_Space) {
            requestCompletion()
            event.accepted = true
            return
        }
        if (event.key === Qt.Key_F8) {
            nextDiagnostic((event.modifiers & Qt.ShiftModifier) ? -1 : 1)
            event.accepted = true
            return
        }
        if (event.key === Qt.Key_F12 && (event.modifiers & Qt.ShiftModifier)) {
            findReferences()
            event.accepted = true
            return
        }
        if (event.key === Qt.Key_F2) {
            startRename()
            event.accepted = true
            return
        }
        if (event.key === Qt.Key_Escape && refsPanel.visible && !searchBar.visible && !gotoBar.visible) {
            refsPanel.close()
            event.accepted = true
            return
        }
        if (event.key === Qt.Key_F12) {
            gotoDefinition()
            event.accepted = true
            return
        }
        if (event.text !== "" && !(event.modifiers & Qt.ControlModifier))
            lastTyped = event.text
        if (event.matches(StandardKey.Undo)) {
            undo()
            event.accepted = true
            return
        }
        if (event.matches(StandardKey.Redo) || ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_Y)) {
            redo()
            event.accepted = true
            return
        }
        if (event.matches(StandardKey.Paste) || event.matches(StandardKey.Cut) || event.key === Qt.Key_Tab
                || event.key === Qt.Key_Backtab || event.key === Qt.Key_Return || event.key === Qt.Key_Enter
                || ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_Slash)
                || ((event.key === Qt.Key_Delete || event.key === Qt.Key_Backspace) && editor.selectedText !== ""))
            checkpoint()
        // search & replace, with Kate's shortcuts
        if ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_G) {  // Kate's go to line
            searchBar.visible = false
            gotoBar.open()
            event.accepted = true
            return
        }
        if (event.matches(StandardKey.Find)) {
            gotoBar.visible = false
            searchBar.open(false)
            event.accepted = true
            return
        }
        if (((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_R) || event.matches(StandardKey.Replace)) {
            gotoBar.visible = false
            searchBar.open(true)
            event.accepted = true
            return
        }
        if (event.key === Qt.Key_F3 && searchBar.query !== "") {
            if (event.modifiers & Qt.ShiftModifier)
                searchBar.previous()
            else
                searchBar.next()
            event.accepted = true
            return
        }
        if (event.key === Qt.Key_Escape && gotoBar.visible) {
            gotoBar.close()
            event.accepted = true
            return
        }
        if (event.key === Qt.Key_Escape && searchBar.visible) {
            searchBar.close()
            event.accepted = true
            return
        }
        // folding, with Kate's shortcuts
        if ((event.modifiers & Qt.ControlModifier) && (event.key === Qt.Key_Minus || event.key === Qt.Key_Underscore)) {
            if (event.modifiers & Qt.ShiftModifier)
                foldTopLevel(true)
            else
                foldCurrent(true)
            event.accepted = true
            return
        }
        if ((event.modifiers & Qt.ControlModifier) && (event.key === Qt.Key_Plus || event.key === Qt.Key_Equal)) {
            if (event.modifiers & Qt.ShiftModifier)
                foldTopLevel(false)
            else
                foldCurrent(false)
            event.accepted = true
            return
        }
        if (event.key === Qt.Key_F10) {
            toggleWrap()
            event.accepted = true
            return
        }
        const ctrl = event.modifiers & Qt.ControlModifier
        const pos = editor.cursorPosition
        const hasSel = editor.selectionStart !== editor.selectionEnd
        const text = editor.text

        if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && ctrl) {
            if (Backend.applySource(editor.text))
                pane.dirty = false
            event.accepted = true
            return
        }
        if (ctrl && (event.key === Qt.Key_Slash || event.key === Qt.Key_NumberSign) && Backend.docKind !== "ui") {
            // toggle // comments, like Kate's Ctrl+/
            const from = lineStart(editor.selectionStart)
            const block = text.substring(from, lineEnd(editor.selectionEnd)).split("\n")
            const commented = block.filter(l => l.trim() !== "").every(l => l.trim().startsWith("//"))
            const minWs = Math.min(...block.filter(l => l.trim() !== "").map(l => leadingWs(l).length))
            editLines(l => {
                if (l.trim() === "")
                    return l
                if (commented)
                    return l.replace(/^([ \t]*)\/\/ ?/, "$1")
                return l.substring(0, minWs) + "// " + l.substring(minWs)
            })
            event.accepted = true
            return
        }
        if (event.key === Qt.Key_Tab && !ctrl) {
            if (hasSel && text.substring(editor.selectionStart, editor.selectionEnd).indexOf("\n") >= 0) {
                editLines(l => l.trim() === "" ? l : indentUnit + l)
            } else {
                const col = wsWidth(text.substring(lineStart(pos), pos).replace(/[^\t]/g, " "))
                editor.insert(pos, indentUnit === "\t" ? "\t" : " ".repeat(indentWidth - col % indentWidth))
            }
            event.accepted = true
            return
        }
        if (event.key === Qt.Key_Backtab) {
            editLines(l => {
                const ws = leadingWs(l)
                return makeWs(Math.max(0, wsWidth(ws) - indentWidth)) + l.substring(ws.length)
            })
            event.accepted = true
            return
        }
        if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && !hasSel) {
            // keep the indentation; indent after an opening bracket
            const ls = lineStart(pos)
            const before = text.substring(ls, pos)
            let ws = leadingWs(text.substring(ls, lineEnd(pos)))
            if (ws.length > before.length)
                ws = before
            const opens = /[{[(]\s*$/.test(before)
            const closer = text[pos]
            let insert = "\n" + ws + (opens ? indentUnit : "")
            let caret = insert.length
            if (opens && (closer === "}" || closer === "]" || closer === ")"))
                insert += "\n" + ws
            editor.insert(pos, insert)
            editor.cursorPosition = pos + caret
            event.accepted = true
            return
        }
        const ch = event.text
        if (ch === "}" || ch === "]" || ch === ")") {
            if (autoBrackets && !hasSel && text[pos] === ch) {  // type over the auto-inserted closer
                editor.cursorPosition = pos + 1
                event.accepted = true
                return
            }
            const ls = lineStart(pos)
            if (!hasSel && /^[ \t]+$/.test(text.substring(ls, pos))) {  // dedent a lone closer
                const ws = makeWs(Math.max(0, wsWidth(text.substring(ls, pos)) - indentWidth))
                editor.remove(ls, pos)
                editor.insert(ls, ws + ch)
                editor.cursorPosition = ls + ws.length + 1
                event.accepted = true
            }
            return
        }
        if (autoBrackets && (ch === "{" || ch === "[" || ch === "(" || ch === "\"")) {
            const close = { "{": "}", "[": "]", "(": ")", "\"": "\"" }[ch]
            if (hasSel) {  // wrap the selection
                const a = editor.selectionStart, b = editor.selectionEnd
                const inner = editor.selectedText
                editor.remove(a, b)
                editor.insert(a, ch + inner + close)
                editor.select(a + 1, a + 1 + inner.length)
                event.accepted = true
            } else if (ch === "\"" && text[pos] === "\"") {
                editor.cursorPosition = pos + 1
                event.accepted = true
            } else if (pos >= text.length || /[\s)\]};,]/.test(text[pos])) {
                editor.insert(pos, ch + close)
                editor.cursorPosition = pos + 1
                event.accepted = true
            }
            return
        }
    }
}
