import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import QtCore

Kirigami.Page {
    id: page

    property bool sourceMode: false
    // the signal flow view (instead of the preview)
    property bool flowMode: false
    onSourceModeChanged: if (sourceMode) flowMode = false
    onFlowModeChanged: if (flowMode) sourceMode = false

    title: Backend.hasDocument ? Backend.fileName : qsTr("Welcome")
    padding: 0
    globalToolBarStyle: Kirigami.ApplicationHeaderStyle.ToolBar

    // Open, Save, Undo and Redo sit where the page title would be (the file
    // name is in the tabs and the window title already)
    Kirigami.Action {
        id: openAction
        text: qsTr("Open…")
        icon.name: "document-open"
        shortcut: StandardKey.Open
        onTriggered: applicationWindow().openFile()
    }
    Kirigami.Action {
        id: saveAction
        text: qsTr("Save")
        icon.name: "document-save"
        shortcut: StandardKey.Save
        enabled: Backend.hasDocument && (Backend.modified || Backend.filePath === "")
        onTriggered: applicationWindow().save()
    }
    Kirigami.Action {
        id: undoAction
        text: qsTr("Undo")
        icon.name: "edit-undo"
        // in Kate's source view, Ctrl+Z is Kate's own (text) undo
        shortcut: page.kateSource ? "" : StandardKey.Undo
        enabled: page.kateSource || Backend.canUndo
        onTriggered: page.kateSource ? page.sourcePane.editorUndo() : Backend.undo()
    }
    Kirigami.Action {
        id: redoAction
        text: qsTr("Redo")
        icon.name: "edit-redo"
        shortcut: page.kateSource ? "" : StandardKey.Redo
        enabled: page.kateSource || Backend.canRedo
        onTriggered: page.kateSource ? page.sourcePane.editorRedo() : Backend.redo()
    }
    titleDelegate: RowLayout {
        spacing: Kirigami.Units.smallSpacing
        QQC2.ToolButton {
            action: openAction
            display: QQC2.AbstractButton.TextBesideIcon
        }
        QQC2.ToolButton {
            action: saveAction
            display: QQC2.AbstractButton.TextBesideIcon
        }
        QQC2.ToolButton {
            action: undoAction
            display: QQC2.AbstractButton.IconOnly
            QQC2.ToolTip.text: qsTr("Undo")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
        QQC2.ToolButton {
            action: redoAction
            display: QQC2.AbstractButton.IconOnly
            QQC2.ToolTip.text: qsTr("Redo")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
    }

    // remembered between sessions
    Settings {
        id: uiSettings
        category: "window"
        property bool projectPanelShown: true   // the sidebar (F9)
        property int sidebarTab: 0
        property bool componentPreviews: true   // the Add tab shows what a component looks like
    }

    actions: [
        Kirigami.Action {
            text: qsTr("New Project…")
            icon.name: "folder-new"
            displayHint: Kirigami.DisplayHint.AlwaysHide
            tooltip: qsTr("Create a folder with a first user interface file")
            onTriggered: applicationWindow().newProject()
        },
        Kirigami.Action {
            text: qsTr("Open Folder…")
            icon.name: "folder-open"
            displayHint: Kirigami.DisplayHint.AlwaysHide
            onTriggered: applicationWindow().openFolder()
        },
        Kirigami.Action {
            text: qsTr("Quick Open…")
            icon.name: "quickopen"
            shortcut: "Ctrl+Alt+O"
            displayHint: Kirigami.DisplayHint.AlwaysHide
            tooltip: qsTr("Switch to a file of the project or a recent file")
            onTriggered: applicationWindow().quickOpen()
        },
        Kirigami.Action {
            text: qsTr("Go to Symbol…")
            icon.name: "code-class"
            shortcut: "Ctrl+Alt+P"
            displayHint: Kirigami.DisplayHint.AlwaysHide
            enabled: Backend.docKind === "qml" && Lsp.running
            onTriggered: page.goToSymbol()
        },
        Kirigami.Action {
            objectName: "runAction"
            text: Backend.running ? qsTr("Stop") : qsTr("Run")
            icon.name: Backend.running ? "media-playback-stop" : "media-playback-start"
            enabled: Backend.running || Backend.canRun
            shortcut: "Ctrl+Shift+R"
            tooltip: Backend.running ? qsTr("Stop %1, which Kreator started").arg(Backend.runName)
                     : Backend.runName !== "" ? qsTr("Save and run %1 as an application of its own (with qml6)").arg(Backend.runName)
                     : qsTr("Save and run the application (with qml6)")
            onTriggered: Backend.running ? Backend.stopRun() : applicationWindow().runApplication()
        },
        Kirigami.Action {
            text: page.sourceMode ? qsTr("Design") : qsTr("Source")
            icon.name: page.sourceMode ? "view-preview" : "code-context"
            checkable: false
            enabled: Backend.hasDocument
            shortcut: "Ctrl+Shift+E"
            tooltip: qsTr("Switch between the visual designer and the source code")
            onTriggered: {
                page.flowMode = false
                page.sourceMode = !page.sourceMode
            }
        },
        Kirigami.Action {
            text: qsTr("Signal Flow")
            icon.name: "distribute-graph-directed"
            checkable: true
            checked: page.flowMode
            enabled: Backend.hasDocument
            shortcut: "Ctrl+Shift+G"
            tooltip: qsTr("Show which objects make which others do something: signals, the code that handles them, and bindings")
            onTriggered: page.flowMode = !page.flowMode
        },
        Kirigami.Action {
            id: openWithAction
            text: qsTr("Open With")
            icon.name: "document-open-folder"
            displayHint: Kirigami.DisplayHint.AlwaysHide
            enabled: Backend.hasDocument
        },
        Kirigami.Action {
            text: qsTr("New")
            icon.name: "document-new"
            displayHint: Kirigami.DisplayHint.AlwaysHide

            Kirigami.Action {
                text: qsTr("Kirigami Application")
                icon.name: "kde"
                onTriggered: applicationWindow().newDocument("kirigami-app")
            }
            Kirigami.Action {
                text: qsTr("Kirigami Page")
                icon.name: "document-new"
                onTriggered: applicationWindow().newDocument("kirigami-page")
            }
            Kirigami.Action {
                text: qsTr("Qt Quick Application")
                icon.name: "text-x-qml"
                onTriggered: applicationWindow().newDocument("qtquick")
            }
            Kirigami.Action {
                text: qsTr("Qt Widgets Form")
                icon.name: "window"
                onTriggered: applicationWindow().newDocument("widgets-form")
            }
        },
        Kirigami.Action {
            text: qsTr("Run Output…")
            icon.name: "utilities-terminal"
            displayHint: Kirigami.DisplayHint.AlwaysHide
            enabled: Backend.runOutput !== ""
            tooltip: qsTr("What the application started with Run printed")
            onTriggered: applicationWindow().showRunOutput()
        },
        Kirigami.Action {
            id: recentAction
            text: qsTr("Open Recent")
            icon.name: "document-open-recent"
            displayHint: Kirigami.DisplayHint.AlwaysHide
            enabled: Backend.recentFiles.length > 0
        },
        Kirigami.Action {
            text: qsTr("Save As…")
            icon.name: "document-save-as"
            shortcut: StandardKey.SaveAs
            displayHint: Kirigami.DisplayHint.AlwaysHide
            enabled: Backend.hasDocument
            onTriggered: applicationWindow().saveAs()
        },
        Kirigami.Action {
            text: qsTr("Save All")
            icon.name: "document-save-all"
            shortcut: "Ctrl+L"
            displayHint: Kirigami.DisplayHint.AlwaysHide
            enabled: Backend.unsavedCount > 0
            onTriggered: {
                if (!page.commitSource())
                    return
                if (Backend.saveAll() > 0) {  // untitled documents need a name
                    Backend.switchTo(Backend.firstUntitledModified())
                    applicationWindow().saveAs()
                }
            }
        },
        Kirigami.Action {
            text: qsTr("Close Folder")
            icon.name: "dialog-close"
            displayHint: Kirigami.DisplayHint.AlwaysHide
            visible: Backend.projectPath !== ""
            onTriggered: applicationWindow().closeFolder()
        },
        Kirigami.Action {
            text: qsTr("Reload")
            icon.name: "view-refresh"
            shortcut: StandardKey.Refresh
            displayHint: Kirigami.DisplayHint.AlwaysHide
            enabled: Backend.filePath !== ""
            onTriggered: applicationWindow().confirmDiscard(() => Backend.reload())
        },
        Kirigami.Action {
            text: qsTr("Close")
            icon.name: "document-close"
            shortcut: StandardKey.Close
            displayHint: Kirigami.DisplayHint.AlwaysHide
            enabled: Backend.hasDocument
            onTriggered: applicationWindow().closeTab(Backend.currentKey)
        },
        Kirigami.Action {
            separator: true
            displayHint: Kirigami.DisplayHint.AlwaysHide
        },
        Kirigami.Action {
            text: qsTr("Configure Kreator…")
            icon.name: "configure"
            shortcut: StandardKey.Preferences
            displayHint: Kirigami.DisplayHint.AlwaysHide
            onTriggered: applicationWindow().configureEditors()
        },
        Kirigami.Action {
            text: qsTr("About Kreator")
            icon.name: "help-about"
            displayHint: Kirigami.DisplayHint.AlwaysHide
            onTriggered: aboutDialog.open()
        },
        Kirigami.Action {
            text: qsTr("Quit")
            icon.name: "application-exit"
            shortcut: StandardKey.Quit
            displayHint: Kirigami.DisplayHint.AlwaysHide
            onTriggered: applicationWindow().close()
        }
    ]

    // build "Open Recent" sub actions
    Component {
        id: recentItemComponent
        Kirigami.Action {
            property string path
            text: path.split("/").pop()
            tooltip: path
            onTriggered: applicationWindow().switchFile(path)
        }
    }
    Component {
        id: clearRecentComponent
        Kirigami.Action {
            text: qsTr("Clear List")
            icon.name: "edit-clear-history"
            onTriggered: Backend.clearRecent()
        }
    }
    Component {
        id: openWithItemComponent
        Kirigami.Action {
            property string editorId
            property bool available
            enabled: available
            onTriggered: applicationWindow().openInEditor(editorId)
        }
    }
    Component {
        id: configureEditorsComponent
        Kirigami.Action {
            text: qsTr("Configure External Editors…")
            icon.name: "configure"
            onTriggered: applicationWindow().configureEditors()
        }
    }
    function rebuildOpenWith() {
        const items = []
        for (const e of Backend.editorList)
            items.push(openWithItemComponent.createObject(openWithAction, {
                editorId: e.id, available: e.available, text: e.name, "icon.name": e.icon
            }))
        items.push(configureEditorsComponent.createObject(openWithAction))
        openWithAction.children = items
    }

    function rebuildRecent() {
        const items = []
        for (const p of Backend.recentFiles)
            items.push(recentItemComponent.createObject(recentAction, { path: p }))
        if (items.length > 0)
            items.push(clearRecentComponent.createObject(recentAction))
        recentAction.children = items
    }
    Connections {
        target: Backend
        function onRecentChanged() {
            page.rebuildRecent()
        }
        function onEditorsChanged() {
            page.rebuildOpenWith()
        }
        function onDocumentChanged() {
            // switching between files keeps the view (design or source)
            if (!Backend.hasDocument) {
                page.sourceMode = false
                page.flowMode = false
            }
            // restored source edits that were never applied
            if (Backend.hasPendingSource)
                page.sourceMode = true
        }
    }
    Component.onCompleted: {
        rebuildRecent()
        rebuildOpenWith()
    }

    // the file was changed by another program (e.g. saved in Kate)
    header: Kirigami.InlineMessage {
        position: Kirigami.InlineMessage.Position.Header
        type: Backend.externalError !== "" ? Kirigami.MessageType.Error : Kirigami.MessageType.Warning
        visible: Backend.externalChange || Backend.externalError !== ""
        text: Backend.externalError !== "" ? Backend.externalError
              : Backend.modified ? qsTr("%1 was changed by another program, and you have unsaved changes here.").arg(Backend.fileName)
              : qsTr("%1 was changed by another program.").arg(Backend.fileName)
        actions: [
            Kirigami.Action {
                text: qsTr("Load Their Version")
                icon.name: "view-refresh"
                visible: Backend.externalChange
                onTriggered: Backend.reloadFromDisk()
            },
            Kirigami.Action {
                text: qsTr("Keep Mine")
                icon.name: "dialog-ok"
                visible: Backend.externalChange
                onTriggered: Backend.keepMyVersion()
            }
        ]
    }

    // ---------------------------------------------------------------- content
    WelcomeView {
        anchors.fill: parent
        visible: !Backend.hasDocument && Backend.projectPath === ""
        openAction: openAction
    }

    PaneSplitView {
        id: split
        anchors.fill: parent
        visible: Backend.hasDocument || Backend.projectPath !== ""
        orientation: Qt.Horizontal

        SidePanel {
            id: sidePanel
            visible: uiSettings.projectPanelShown
            sourceMode: page.sourceMode
            currentTab: uiSettings.sidebarTab
            onCurrentTabChanged: uiSettings.sidebarTab = currentTab
            componentPreviews: uiSettings.componentPreviews
            onComponentPreviewsChanged: uiSettings.componentPreviews = componentPreviews
            QQC2.SplitView.preferredWidth: Kirigami.Units.gridUnit * 16
            QQC2.SplitView.minimumWidth: Kirigami.Units.gridUnit * 11
        }

        ColumnLayout {
            QQC2.SplitView.fillWidth: true
            spacing: 0

            DocumentTabs {
                Layout.fillWidth: true
                visible: Backend.openDocuments.length > 0 || Backend.projectPath !== ""
                projectPanelShown: uiSettings.projectPanelShown
                onToggleProjectPanel: uiSettings.projectPanelShown = !uiSettings.projectPanelShown
            }

            PaneSplitView {
                id: docSplit
                Layout.fillWidth: true
                Layout.fillHeight: true
                orientation: Qt.Horizontal

                Item {
                    QQC2.SplitView.fillWidth: true
                    QQC2.SplitView.minimumWidth: Kirigami.Units.gridUnit * 14

                    PreviewPane {
                        anchors.fill: parent
                        visible: Backend.hasDocument && !page.sourceMode && !page.flowMode
                    }
                    Binding {
                        target: Backend
                        property: "previewShown"
                        value: !page.sourceMode && !page.flowMode
                    }
                    FlowPane {
                        anchors.fill: parent
                        visible: active
                        active: Backend.hasDocument && page.flowMode
                        onJumpRequested: (line, column) => page.gotoSource(line - 1, column - 1)
                    }
                    // Kate's editor (KTextEditor) when its module is available,
                    // else Kreator's own source editor; both have the same API
                    // (Kate's pane by URL: it's only compiled when its module is there)
                    Loader {
                        id: sourceLoader
                        anchors.fill: parent
                        visible: Backend.hasDocument && page.sourceMode
                        Component.onCompleted: {
                            if (Backend.kateEditorAvailable)
                                setSource(Qt.resolvedUrl("KateSourcePane.qml"))
                            else
                                sourceComponent = plainSourceComponent
                        }
                        onLoaded: item.active = Qt.binding(() => Backend.hasDocument && page.sourceMode)
                    }
                    Component {
                        id: plainSourceComponent
                        SourcePane {}
                    }
                    Kirigami.PlaceholderMessage {
                        anchors.centerIn: parent
                        width: parent.width - Kirigami.Units.gridUnit * 4
                        visible: !Backend.hasDocument
                        icon.name: "folder-open"
                        text: qsTr("Choose a file")
                        explanation: qsTr("Pick a .qml or .ui file from %1, or press Ctrl+Alt+O to search for one.").arg(Backend.projectName)
                    }
                }

                PropertyPanel {
                    visible: Backend.hasDocument
                    QQC2.SplitView.preferredWidth: Kirigami.Units.gridUnit * 20
                    QQC2.SplitView.minimumWidth: Kirigami.Units.gridUnit * 14
                }
            }
        }
    }

    // sidebar (F9, like Dolphin's panels)
    Shortcut {
        sequence: "F9"
        onActivated: uiSettings.projectPanelShown = !uiSettings.projectPanelShown
    }
    // tabs (Ctrl+Tab cycles, like Kate)
    Shortcut {
        sequences: ["Ctrl+Tab", "Ctrl+PgDown"]
        enabled: Backend.openDocuments.length > 1
        onActivated: applicationWindow().nextTab(1)
    }
    Shortcut {
        sequences: ["Ctrl+Shift+Tab", "Ctrl+Backtab", "Ctrl+PgUp"]
        enabled: Backend.openDocuments.length > 1
        onActivated: applicationWindow().nextTab(-1)
    }

    // apply unapplied source edits before leaving the document; false if they
    // do not parse (the user fixes or reverts them first)
    readonly property Item sourcePane: sourceLoader.item
    // the source view is Kate's editor (its own undo, shortcuts and settings)
    readonly property bool kateSource: Backend.kateEditorAvailable && sourceMode && Backend.hasDocument
    readonly property int sourceLine: sourcePane ? sourcePane.currentLine - 1 : -1

    function commitSource() {
        return sourcePane.commitPending()
    }
    // open a file (or the shown one) in the source view at a position
    function openAt(path, line, character) {
        if (path === Backend.filePath) {
            gotoSource(line, character)
            return
        }
        sourcePane.pendingGoto = { line: line, character: character }
        if (!applicationWindow().switchFile(path)) {
            sourcePane.pendingGoto = null
            return
        }
        sourceMode = true
    }
    function showFilesTab() {
        sidePanel.showTab(0)
        uiSettings.projectPanelShown = true
    }
    // the design view with the components to add (a new project starts here)
    function showAddTab() {
        sourceMode = false
        flowMode = false
        sidePanel.showTab(2)
        uiSettings.projectPanelShown = true
    }
    function pendingSource() {
        return sourcePane.pendingText()
    }
    function gotoSource(line, character) {
        sourceMode = true
        Qt.callLater(() => sourcePane.gotoPosition(line, character))
    }

    // Go to Symbol (Ctrl+Alt+P), from qmlls' document symbols
    QuickPicker {
        id: symbolPicker
        placeholder: qsTr("Go to a symbol in %1…").arg(Backend.fileName)
        emptyText: Lsp.running ? qsTr("No matching symbols") : qsTr("Symbols need the QML language server (qmlls)")
        onPicked: item => page.gotoSource(item.line, item.character)
    }
    function goToSymbol() {
        if (Backend.docKind !== "qml")
            return
        Lsp.setWantSymbols(true)
        symbolPicker.show(Lsp.symbols.map(s => ({
            title: s.name, icon: s.icon, line: s.line, character: s.character, bold: s.isObject,
            subtitle: (s.detail ? s.detail + "   " : "") + qsTr("line %1").arg(s.line + 1)
        })))
    }
    Connections {
        target: Lsp
        function onSymbolsChanged() {
            if (symbolPicker.opened)
                page.goToSymbol()
        }
    }

    // structure editing shortcuts (text fields take precedence via ShortcutOverride)
    Shortcut {
        sequences: [StandardKey.Delete]
        enabled: !page.sourceMode && Backend.hasDocument && !Backend.isRootSelected
        onActivated: Backend.deleteSelected()
    }
    Shortcut {
        sequences: [StandardKey.Copy]
        enabled: !page.sourceMode && Backend.hasDocument
        onActivated: Backend.copySelected()
    }
    Shortcut {
        sequences: [StandardKey.Cut]
        enabled: !page.sourceMode && Backend.hasDocument && !Backend.isRootSelected
        onActivated: Backend.cutSelected()
    }
    Shortcut {
        sequences: [StandardKey.Paste]
        enabled: !page.sourceMode && Backend.hasDocument
        onActivated: Backend.paste()
    }
    // the external editor is opened from the source view and the outline menu;
    // the shortcut works everywhere
    Shortcut {
        sequence: "Ctrl+Shift+O"
        enabled: Backend.hasDocument
        onActivated: Backend.defaultEditorAvailable ? applicationWindow().openInEditor("") : applicationWindow().configureEditors()
    }
    Shortcut {
        sequence: "Ctrl+D"
        enabled: !page.sourceMode && Backend.hasDocument && !Backend.isRootSelected
        onActivated: Backend.duplicateSelected()
    }
    Shortcut {
        sequence: "Alt+Up"
        enabled: !page.sourceMode && Backend.hasDocument
        onActivated: Backend.moveSelected(-1)
    }
    Shortcut {
        sequence: "Alt+Down"
        enabled: !page.sourceMode && Backend.hasDocument
        onActivated: Backend.moveSelected(1)
    }
}
