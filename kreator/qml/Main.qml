import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import QtQuick.Dialogs
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: root

    property var pendingAction: null
    readonly property Item mainPage: editorPage
    property bool closeAccepted: false

    title: (Backend.hasDocument ? (Backend.modified ? "• " : "") + Backend.fileName : "")
           + (Backend.projectName !== "" ? (Backend.hasDocument ? " — " : "") + Backend.projectName : "")
    width: Kirigami.Units.gridUnit * 84
    height: Kirigami.Units.gridUnit * 50
    minimumWidth: Kirigami.Units.gridUnit * 40
    minimumHeight: Kirigami.Units.gridUnit * 26

    pageStack.globalToolBar.style: Kirigami.ApplicationHeaderStyle.ToolBar
    pageStack.globalToolBar.showNavigationButtons: Kirigami.ApplicationHeaderStyle.NoNavigationButtons
    pageStack.columnView.columnResizeMode: Kirigami.ColumnView.SingleColumn
    pageStack.initialPage: EditorPage {
        id: editorPage
        objectName: "editorPage"
    }

    // ---------------------------------------------------------------- helpers
    function confirmDiscard(action) {
        if (Backend.hasDocument && Backend.modified) {
            pendingAction = action
            discardDialog.open()
        } else {
            action()
        }
    }

    function save(then) {
        if (!Backend.hasDocument)
            return
        if (Backend.filePath === "") {
            saveAs(then)
        } else if (Backend.save() && then) {
            then()
        }
    }

    function saveAs(then) {
        saveDialog.then = then || null
        saveDialog.selectedFile = Backend.suggestedFileName("")
        saveDialog.open()
    }

    // Open the document in an external editor (empty id = the default one).
    // The editor works on the file, so unsaved changes are saved first.
    function openInEditor(editorId) {
        if (!Backend.hasDocument)
            return
        const go = () => Backend.openInEditor(editorId || "")
        if (Backend.filePath === "")
            saveAs(go)
        else if (Backend.modified)
            save(go)
        else
            go()
    }

    function configureEditors() {
        if (pageStack.layers.depth === 1)
            pageStack.layers.push(Qt.resolvedUrl("EditorSettingsPage.qml"))
    }

    // Other documents keep their unsaved changes in memory, so opening or
    // switching never needs a "save changes?" question. Unapplied edits in the
    // source view are applied first.
    function switchFile(pathOrKey) {
        if (!editorPage.commitSource())
            return false
        return Backend.switchTo(pathOrKey)
    }

    function openFile() {
        openDialog.open()
    }

    // close a document tab; asks first if it has unsaved changes
    function closeTab(key) {
        const d = Backend.openDocuments.find(x => x.key === key)
        if (!d)
            return
        if (d.current) {
            confirmDiscard(() => Backend.closeDocument())
        } else if (d.modified) {
            if (switchFile(key))  // show it, then ask about it
                confirmDiscard(() => Backend.closeDocument())
        } else {
            Backend.closeBackgroundDocument(key)
        }
    }

    function nextTab(delta) {
        if (editorPage.commitSource())
            Backend.nextTab(delta)
    }

    function localPath(url) {
        return decodeURIComponent(url.toString().replace(/^file:\/\//, ""))
    }

    function newDocument(template) {
        if (editorPage.commitSource())
            Backend.newDocument(template)
    }

    function openFolder() {
        folderDialog.open()
    }

    // New Project…: a folder with a first file, opened in the design view
    // with the components to add
    function newProject() {
        if (editorPage.commitSource())
            newProjectDialog.show()
    }

    // Run: what runs is what is on disk, so the application's files are saved
    // first (and an untitled document gets a file)
    function runApplication() {
        if (!editorPage.commitSource())
            return
        if (Backend.hasDocument && Backend.docKind === "qml" && Backend.filePath === "")
            saveAs(() => Backend.run())
        else
            Backend.run()
    }

    function showRunOutput() {
        runOutputDialog.open()
    }

    function closeFolder() {
        whenAllSaved(() => {
            Backend.closeFolder()
            Backend.discardAll()
        }, qsTr("Close Folder"))
    }

    // Run `action` once no document has unsaved changes (asks to save or discard).
    function whenAllSaved(action, actionName) {
        if (!editorPage.commitSource())
            return
        if (Backend.unsavedCount === 0) {
            action()
            return
        }
        saveAllDialog.action = action
        saveAllDialog.actionName = actionName || ""
        saveAllDialog.open()
    }

    function quickOpen() {
        const items = []
        const seen = {}
        // the previously used document first (Enter switches back), the current one last
        const docs = Backend.openDocuments.slice().sort((a, b) => (a.current ? 1e6 : a.recency) - (b.current ? 1e6 : b.recency))
        for (const d of docs) {
            seen[d.key] = true
            items.push({ key: d.key, title: (d.modified ? "• " : "") + d.name, icon: d.name.endsWith(".ui") ? "window" : "text-x-qml",
                         subtitle: d.current ? qsTr("current") : (d.path ? d.path.replace(Backend.projectPath + "/", "") : qsTr("unsaved")),
                         bold: d.current })
        }
        for (const f of Backend.projectFileList) {
            if (!seen[f.key])
                items.push({ key: f.key, title: f.name, subtitle: f.relPath.substring(0, f.relPath.length - f.name.length),
                             icon: f.name.endsWith(".ui") ? "window" : "text-x-qml" })
        }
        for (const r of Backend.recentFiles) {
            if (!seen[r] && !(Backend.projectPath && r.startsWith(Backend.projectPath + "/")))
                items.push({ key: r, title: r.split("/").pop(), subtitle: r, icon: "document-open-recent" })
            seen[r] = true
        }
        filePicker.show(items)
    }

    function saveSession() {
        Backend.setPendingSource(editorPage.pendingSource())
        Backend.saveSession()
    }

    // periodic session saves, so a crash doesn't lose edits
    Timer {
        interval: Math.max(1, Backend.sessionInterval) * 1000
        running: Backend.sessionInterval > 0
        repeat: true
        onTriggered: root.saveSession()
    }

    onClosing: close => {
        if (closeAccepted)
            return
        if (Backend.keepsUnsaved) {
            // everything, unsaved changes included, comes back on the next start;
            // source edits that don't parse yet are kept as they are
            editorPage.commitSource()
            saveSession()
            return
        }
        // before saving / discarding changes closes anything
        Backend.saveSession()
        if (!editorPage.commitSource() || Backend.unsavedCount > 0) {
            close.accepted = false
            whenAllSaved(() => {
                closeAccepted = true
                root.close()
            }, qsTr("Quit"))
        }
    }

    Connections {
        target: Backend
        function onNotify(message) {
            root.showPassiveNotification(message)
        }
        function onErrorOccurred(message) {
            root.showPassiveNotification(message, "long")
        }
        // the running application complains (once per run), or ends badly
        function onRunProblem(line) {
            if (!runOutputDialog.opened)
                root.showPassiveNotification(qsTr("%1: %2").arg(Backend.runName).arg(line), "long",
                                             qsTr("Show Output"), () => root.showRunOutput())
        }
        function onRunFinished(name, code, failed) {
            if (failed && !runOutputDialog.opened)
                root.showPassiveNotification(code < 0 ? qsTr("%1 could not be started").arg(name)
                                             : qsTr("%1 ended with an error").arg(name), "long",
                                             qsTr("Show Output"), () => root.showRunOutput())
        }
    }

    // ---------------------------------------------------------------- dialogs
    FileDialog {
        id: openDialog
        title: qsTr("Open User Interface File")
        fileMode: FileDialog.OpenFile
        nameFilters: [qsTr("User interface files (*.qml *.ui)"), qsTr("Qt Quick files (*.qml)"),
            qsTr("Qt Designer forms (*.ui)"), qsTr("All files (*)")]
        onAccepted: root.switchFile(root.localPath(selectedFile))
    }

    FolderDialog {
        id: folderDialog
        title: qsTr("Open Folder")
        onAccepted: {
            if (Backend.openFolder(root.localPath(selectedFolder)))
                editorPage.showFilesTab()
        }
    }

    RunOutputDialog {
        id: runOutputDialog
    }

    NewProjectDialog {
        id: newProjectDialog
        onCreated: editorPage.showAddTab()
    }

    QuickPicker {
        id: filePicker
        placeholder: Backend.projectName !== "" ? qsTr("Open a file in %1…").arg(Backend.projectName) : qsTr("Open a file…")
        emptyText: qsTr("No matching files")
        onPicked: item => root.switchFile(item.key)
    }

    // several documents may have unsaved changes
    Kirigami.PromptDialog {
        id: saveAllDialog
        property var action: null
        property string actionName: ""
        title: Backend.unsavedCount === 1 ? qsTr("Save Changes?") : qsTr("Save Changes to %1 Files?").arg(Backend.unsavedCount)
        subtitle: qsTr("These files have unsaved changes:") + "\n" + Backend.unsavedNames.map(n => "• " + n).join("\n")
        standardButtons: Kirigami.Dialog.NoButton
        customFooterActions: [
            Kirigami.Action {
                text: Backend.unsavedCount === 1 ? qsTr("Save") : qsTr("Save All")
                icon.name: "document-save-all"
                onTriggered: {
                    saveAllDialog.close()
                    const act = saveAllDialog.action
                    if (Backend.saveAll() === 0) {
                        if (act)
                            act()
                        return
                    }
                    // an untitled document needs a file name first
                    Backend.switchTo(Backend.firstUntitledModified())
                    root.saveAs(() => root.whenAllSaved(act, saveAllDialog.actionName))
                }
            },
            Kirigami.Action {
                text: qsTr("Discard")
                icon.name: "edit-delete-remove"
                onTriggered: {
                    saveAllDialog.close()
                    Backend.discardAll()
                    if (saveAllDialog.action)
                        saveAllDialog.action()
                }
            },
            Kirigami.Action {
                text: qsTr("Cancel")
                icon.name: "dialog-cancel"
                onTriggered: saveAllDialog.close()
            }
        ]
    }

    FileDialog {
        id: saveDialog
        property var then: null
        title: qsTr("Save As")
        fileMode: FileDialog.SaveFile
        nameFilters: Backend.docKind === "ui" ? [qsTr("Qt Designer forms (*.ui)")] : [qsTr("Qt Quick files (*.qml)")]
        onAccepted: {
            if (Backend.saveAs(selectedFile.toString()) && then)
                then()
            then = null
        }
    }

    Kirigami.PromptDialog {
        id: discardDialog
        title: qsTr("Save Changes?")
        subtitle: qsTr("“%1” has unsaved changes. Do you want to save them before continuing?").arg(Backend.fileName)
        standardButtons: Kirigami.Dialog.NoButton
        customFooterActions: [
            Kirigami.Action {
                text: qsTr("Save")
                icon.name: "document-save"
                onTriggered: {
                    discardDialog.close()
                    const act = root.pendingAction
                    root.pendingAction = null
                    root.save(act)
                }
            },
            Kirigami.Action {
                text: qsTr("Discard")
                icon.name: "edit-delete-remove"
                onTriggered: {
                    discardDialog.close()
                    const act = root.pendingAction
                    root.pendingAction = null
                    if (act)
                        act()
                }
            },
            Kirigami.Action {
                text: qsTr("Cancel")
                icon.name: "dialog-cancel"
                onTriggered: {
                    root.pendingAction = null
                    discardDialog.close()
                }
            }
        ]
    }

    Kirigami.Dialog {
        id: aboutDialog
        title: qsTr("About Kreator")
        standardButtons: Kirigami.Dialog.Close
        padding: Kirigami.Units.largeSpacing
        preferredWidth: Kirigami.Units.gridUnit * 24

        ColumnLayout {
            spacing: Kirigami.Units.largeSpacing

            Kirigami.Icon {
                source: "document-preview"
                Layout.alignment: Qt.AlignHCenter
                implicitWidth: Kirigami.Units.iconSizes.huge
                implicitHeight: Kirigami.Units.iconSizes.huge
            }
            Kirigami.Heading {
                Layout.alignment: Qt.AlignHCenter
                text: qsTr("Kreator %1").arg(Qt.application.version)
            }
            QQC2.Label {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
                text: qsTr("View and edit Qt Quick, Kirigami and Qt Designer user interface files, and check them against the KDE Human Interface Guidelines.")
            }
            Kirigami.UrlButton {
                Layout.alignment: Qt.AlignHCenter
                url: "https://develop.kde.org/hig/"
                text: qsTr("KDE Human Interface Guidelines")
            }
        }
    }

    DropArea {
        anchors.fill: parent
        keys: ["text/uri-list"]
        onDropped: drop => {
            if (drop.hasUrls && drop.urls.length > 0) {
                const path = root.localPath(drop.urls[0])
                if (Backend.openFolder !== undefined && !/\.(qml|ui)$/i.test(path))
                    Backend.openFolder(path)
                else
                    root.switchFile(path)
                drop.accept()
            }
        }
    }
}
