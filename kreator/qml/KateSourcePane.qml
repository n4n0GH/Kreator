import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kreator.kate

// The source view with Kate's editor (KTextEditor, from the system: updates
// of Kate's editor apply to Kreator too). Editing, search (Ctrl+F), go to line
// (Ctrl+G), folding, completion of words, vi mode etc. are Kate's; its
// settings are shared with Kate ("Configure Editor…"). With Kate's LSP client
// plugin (installed with Kate), qmlls' completion, diagnostics, hover, go to
// definition, find references, rename… are Kate's too; its panels (references,
// diagnostics) are shown below the editor.
//
// Same interface as SourcePane.qml: active, currentLine, pendingGoto,
// load(), commitPending(), pendingText(), gotoPosition().
ColumnLayout {
    id: pane
    spacing: 0

    property bool active: false
    property bool dirty: false
    property bool loading: false
    property var pendingGoto: null      // {line, character} after opening another file
    property bool panelsShown: false    // Kate's panels (references, diagnostics)
    readonly property int currentLine: editor.cursorLine + 1

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

    function apply() {
        if (Backend.applySource(editor.text))
            dirty = false
    }

    // (re)load the document's text; on a new document (or when asked) put the
    // cursor at the selected object. keepPlace: a tab shown here before keeps
    // its cursor and scroll position (its Kate document and view were kept)
    function load(gotoSelection, keepPlace) {
        loading = true
        editor.documentKey = Backend.currentKey
        editor.mode = Backend.docKind === "ui" ? "XML" : "QML"
        editor.fileName = Backend.filePath
        editor.text = Backend.sourceText
        loading = false
        dirty = false
        // unapplied edits from the last session
        const pending = Backend.takePendingSource()
        if (pending !== "") {
            loading = true
            editor.text = pending
            loading = false
            dirty = true
        }
        Lsp.openDocument(Backend.filePath, editor.text, Backend.docKind === "qml")
        if (pendingGoto) {
            const g = pendingGoto
            pendingGoto = null
            gotoPosition(g.line, g.character)
            return
        }
        if (gotoSelection && !(keepPlace && editor.documentReused)) {
            const line = Backend.lineOfSelected("")
            if (line > 0)
                editor.setCursorPosition(line - 1, 0)
        }
    }

    function gotoPosition(line, character) {
        editor.setCursorPosition(line, character)
        editor.focusEditor()
    }

    // Kate's own undo, for the toolbar's Undo/Redo in this view
    function editorUndo() {
        editor.undo()
    }
    function editorRedo() {
        editor.redo()
    }

    onActiveChanged: {
        Lsp.setWantSymbols(active)
        if (active) {
            load(true)
            editor.focusEditor()
        } else if (dirty) {
            Backend.applySource(editor.text)
            dirty = false
        }
    }

    Connections {
        target: Backend
        // another document, or changes from elsewhere (design view, undo, quick
        // fixes): show them unless there are unapplied edits here
        function onDocumentChanged() {
            if (pane.active)
                pane.load(true, true)
        }
        function onContentChanged() {
            if (pane.active && !pane.dirty && editor.text !== Backend.sourceText)
                pane.load(false)
        }
    }

    // The editor and its panels are native windows drawn above everything in
    // their area: while a popup (menu, dialog, picker) is open, they show a
    // snapshot instead...
    function overlayBusy() {
        const ov = applicationWindow().QQC2.Overlay.overlay
        if (!ov)
            return false
        for (const c of ov.children) {
            if (c.visible && !String(c).startsWith("PassiveNotificationsManager"))
                return true
        }
        return false
    }
    // ...and leave room at the bottom for notifications
    function notificationInset(item) {
        const ov = applicationWindow().QQC2.Overlay.overlay
        if (!ov || !item.visible)
            return 0
        for (const c of ov.children) {
            if (!String(c).startsWith("PassiveNotificationsManager"))
                continue
            const list = c.children.find(x => String(x).startsWith("QQuickListView"))
            if (!list || list.count === 0)
                return 0
            const top = ov.height - list.count * Kirigami.Units.gridUnit * 2.5 - Kirigami.Units.gridUnit
            const bottom = item.mapToItem(ov, 0, item.height).y
            return Math.max(0, bottom - top)
        }
        return 0
    }

    // The type name (with its qualifier, "Kirigami.Icon") at a position, up to
    // the end of the clicked part; "" if it isn't one (types start uppercase)
    function typeNameAt(line, column) {
        const l = editor.text.split("\n")[line] || ""
        let start = column, end = column
        while (start > 0 && /[\w.]/.test(l[start - 1]))
            start--
        while (end < l.length && /\w/.test(l[end]))
            end++
        const word = l.slice(start, end).replace(/^\.+|\.+$/g, "")
        const last = word.split(".").pop()
        return /^[A-Z]/.test(last) ? word : ""
    }

    // Kreator's keys while typing in Kate (the rest are Kate's)
    Shortcut {
        sequences: ["Ctrl+Return", "Ctrl+Enter"]
        enabled: pane.active && pane.dirty
        onActivated: pane.apply()
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
                                 : qsTr("Source of %1 · Kate's editor %2").arg(Backend.fileName).arg(editor.frameworkVersion)
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
                enabled: Lsp.running && Lsp.errorCount + Lsp.warningCount > 0
                onClicked: {
                    // the next problem after the cursor
                    const ds = Lsp.diagnostics
                    const cur = editor.cursorLine
                    const next = ds.find(d => d.line > cur) || ds[0]
                    if (next)
                        pane.gotoPosition(next.line, next.character)
                }
                QQC2.ToolTip.text: qsTr("Diagnostics from qmlls: click for the next one. All files: Guidelines tab, qmllint")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.ToolButton {
                text: qsTr("Panels")
                icon.name: "view-split-top-bottom"
                checkable: true
                checked: pane.panelsShown
                visible: toolArea.count > 0
                onToggled: pane.panelsShown = checked
                QQC2.ToolTip.text: qsTr("Kate's panels: references, diagnostics")
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
                text: qsTr("Configure Editor…")
                icon.name: "configure"
                display: QQC2.AbstractButton.IconOnly
                onClicked: editor.configureEditor()
                QQC2.ToolTip.text: editor.languageFeatures ? qsTr("Kate's editor and LSP client settings (shared with Kate)")
                                                           : qsTr("Kate's editor settings (shared with Kate)")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.ToolButton {
                text: qsTr("Revert")
                icon.name: "edit-undo"
                enabled: pane.dirty
                onClicked: pane.load(false)
            }
            QQC2.Button {
                text: qsTr("Apply")
                icon.name: "dialog-ok-apply"
                enabled: pane.dirty
                onClicked: pane.apply()
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

    PaneSplitView {
        Layout.fillWidth: true
        Layout.fillHeight: true
        orientation: Qt.Vertical

        KateEditor {
            id: editor
            objectName: "kateEditor"
            QQC2.SplitView.fillHeight: true

            // Kreator owns files and the app; Kate owns text editing
            releasedShortcuts: ["Ctrl+S", "Ctrl+Shift+S", "F5", "Ctrl+Return", "Ctrl+Enter", "Ctrl+Shift+O", "Ctrl+Shift+E", "Ctrl+Alt+P", "Ctrl+Shift+G", "Ctrl+Shift+R"]
            disabledActions: ["file_save", "file_save_as", "file_reload"]

            // Kate's LSP client, sharing Kreator's qmlls (through lspbridge.py;
            // off with the language server)
            languageServer: Lsp.kateServerCommand
            projectRoot: Backend.projectPath
            // a Kate document per open tab (closed tabs' are dropped)
            openKeys: Backend.openDocumentKeys

            frozen: pane.overlayBusy()
            bottomInset: toolPanel.visible ? 0 : pane.notificationInset(editor)

            onTextEdited: {
                if (pane.loading)
                    return
                pane.dirty = text !== Backend.sourceText
                Lsp.changeDocument(text)
            }
            // go to definition / a reference in another file: Kreator opens it
            onOpenFileRequested: path => {
                if (!/\.(qml|ui)$/i.test(path)) {
                    applicationWindow().showPassiveNotification(qsTr("%1 is not a QML or UI file").arg(path.split("/").pop()), "short")
                    return
                }
                applicationWindow().switchFile(path)
            }
            // a rename / code action also changed other files: unsaved changes
            // there, like the quick fixes of the Guidelines tab
            onFileEditRequested: (path, basis, text) => {
                if (Backend.applyFileEdit(path, basis, text))
                    applicationWindow().showPassiveNotification(qsTr("Also changed %1 (not saved yet)").arg(path.split("/").pop()), "short")
            }
            // go to definition of a type implemented in C++: nothing to open
            // (qmlls has no file for it), so describe it instead
            onDefinitionRequested: (line, column) => {
                const word = pane.typeNameAt(line, column)
                if (!word)
                    return
                const info = Backend.typeDescription(word)
                if (!info.name)
                    return
                const p = editor.positionBelow(line, column)
                typePopup.show(info, p.x, p.y)
            }
            onMessage: (text, type) => {
                if (type === "Error")
                    applicationWindow().showPassiveNotification(text, "long")
            }

            TypeInfoPopup {
                id: typePopup
                onClosedByUser: editor.focusEditor()
            }
        }

        ColumnLayout {
            id: toolPanel
            visible: pane.panelsShown && toolArea.count > 0
            QQC2.SplitView.preferredHeight: Kirigami.Units.gridUnit * 12
            QQC2.SplitView.minimumHeight: Kirigami.Units.gridUnit * 5
            spacing: 0

            QQC2.ToolBar {
                Layout.fillWidth: true
                position: QQC2.ToolBar.Header
                RowLayout {
                    anchors.fill: parent
                    Kirigami.Heading {
                        Layout.fillWidth: true
                        Layout.leftMargin: Kirigami.Units.smallSpacing
                        level: 5
                        text: qsTr("Kate's panels")
                        elide: Text.ElideRight
                    }
                    QQC2.ToolButton {
                        icon.name: "window-close-symbolic"
                        text: qsTr("Hide Panels")
                        display: QQC2.AbstractButton.IconOnly
                        onClicked: pane.panelsShown = false
                        QQC2.ToolTip.text: text
                        QQC2.ToolTip.visible: hovered
                        QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                    }
                }
            }
            KateToolArea {
                id: toolArea
                objectName: "kateToolArea"
                Layout.fillWidth: true
                Layout.fillHeight: true
                frozen: pane.overlayBusy()
                bottomInset: pane.notificationInset(toolArea)
                // Kate shows a panel (find references) / hides it (Escape)
                onShowRequested: show => pane.panelsShown = show
            }
        }
    }
}
