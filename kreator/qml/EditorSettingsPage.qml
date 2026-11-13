import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import QtQuick.Dialogs
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page

    title: qsTr("Settings")

    property var cfg: JSON.parse(Backend.editorSettingsJson())
    readonly property string kateCommand: Backend.kateCommand()

    // Settings apply immediately, as is usual in KDE applications.
    function commit(reload) {
        Backend.setEditorSettingsJson(JSON.stringify(cfg))
        if (reload)
            cfg = JSON.parse(Backend.editorSettingsJson())
    }

    Connections {
        target: Backend
        function onEditorsChanged() {
            Qt.callLater(() => defaultBox.currentIndex = Math.max(0, defaultBox.indexOfValue(page.cfg["default"])))
        }
    }

    function addEditor(preset) {
        const c = cfg
        c.custom.push({ id: "", name: preset.name, command: preset.command, args: preset.args, icon: preset.icon })
        cfg = c
        commit(true)
    }

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing

        Kirigami.FormLayout {
            id: mainForm
            Layout.fillWidth: true

            QQC2.ComboBox {
                id: defaultBox
                Kirigami.FormData.label: qsTr("Open files with:")
                model: Backend.editorList
                textRole: "name"
                valueRole: "id"
                Component.onCompleted: currentIndex = Math.max(0, indexOfValue(page.cfg["default"]))
                onActivated: {
                    page.cfg["default"] = currentValue
                    page.commit(false)
                }
            }
            QQC2.CheckBox {
                Kirigami.FormData.label: qsTr("Changes on disk:")
                text: qsTr("Reload automatically when there are no unsaved changes")
                checked: page.cfg.autoReload
                onToggled: {
                    page.cfg.autoReload = checked
                    page.commit(false)
                }
            }
            QQC2.CheckBox {
                Kirigami.FormData.label: qsTr("On start:")
                text: qsTr("Reopen the last folder and documents")
                checked: page.cfg.restoreSession !== false
                onToggled: {
                    page.cfg.restoreSession = checked
                    page.commit(false)
                }
                QQC2.ToolTip.text: qsTr("A file opened from the command line is added to the reopened documents.")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.CheckBox {
                text: qsTr("Keep unsaved changes, new documents and undo history")
                enabled: page.cfg.restoreSession !== false
                checked: page.cfg.keepUnsaved !== false
                onToggled: {
                    page.cfg.keepUnsaved = checked
                    page.commit(false)
                }
                QQC2.ToolTip.text: qsTr("Quitting no longer asks to save; unsaved edits are there again on the next start")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            RowLayout {
                Kirigami.FormData.label: qsTr("Save session every:")
                spacing: Kirigami.Units.smallSpacing
                enabled: page.cfg.restoreSession !== false
                QQC2.SpinBox {
                    id: intervalBox
                    from: 0
                    to: 3600
                    stepSize: 5
                    editable: true
                    value: page.cfg.sessionInterval === undefined ? 15 : page.cfg.sessionInterval
                    textFromValue: (v, locale) => v === 0 ? qsTr("Only on quit") : qsTr("%1 s").arg(v)
                    valueFromText: (text, locale) => {
                        const n = parseInt(text)
                        return isNaN(n) ? 0 : n
                    }
                    onValueModified: {
                        page.cfg.sessionInterval = value
                        page.commit(false)
                    }
                    QQC2.ToolTip.text: qsTr("How often the open documents, unsaved changes included, are saved for the next start, so a crash loses at most this much. 0 saves only when quitting.")
                    QQC2.ToolTip.visible: hovered
                    QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                }
            }

            // ------------------------------------------------------------ language server
            Kirigami.Separator {
                Kirigami.FormData.isSection: true
                Kirigami.FormData.label: qsTr("QML Language Server")
            }
            QQC2.CheckBox {
                Kirigami.FormData.label: qsTr("Source view:")
                text: qsTr("Completion, diagnostics and go to definition with qmlls")
                checked: page.cfg.lsp.enabled
                onToggled: {
                    page.cfg.lsp.enabled = checked
                    page.commit(false)
                }
            }
            QQC2.CheckBox {
                text: qsTr("Semantic highlighting")
                enabled: page.cfg.lsp.enabled
                checked: page.cfg.lsp.semantic !== false
                onToggled: {
                    page.cfg.lsp.semantic = checked
                    page.commit(false)
                }
                QQC2.ToolTip.text: qsTr("Colour identifiers by what they are (ids, properties, methods, enum values…), as qmlls reports them")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            RowLayout {
                Kirigami.FormData.label: qsTr("Program:")
                spacing: Kirigami.Units.smallSpacing
                enabled: page.cfg.lsp.enabled
                QQC2.TextField {
                    id: qmllsField
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 16
                    text: page.cfg.lsp.command
                    placeholderText: Lsp.serverPath !== "" ? Lsp.serverPath : qsTr("qmlls (not found)")
                    font.family: Kirigami.Theme.fixedWidthFont.family
                    onEditingFinished: {
                        page.cfg.lsp.command = text.trim()
                        page.commit(false)
                    }
                }
                Kirigami.Icon {
                    source: Lsp.serverPath !== "" ? "checkmark" : "data-warning"
                    implicitWidth: Kirigami.Units.iconSizes.small
                    implicitHeight: Kirigami.Units.iconSizes.small
                }
            }
            QQC2.Label {
                Layout.maximumWidth: Kirigami.Units.gridUnit * 24
                wrapMode: Text.WordWrap
                font: Kirigami.Theme.smallFont
                opacity: 0.8
                text: qsTr("qmlls is part of Qt's declarative tools. It reads a project's .qmlls.ini (build directory, import paths), so app-specific modules are understood too. Leave the program empty to find it automatically.")
            }

            // ------------------------------------------------------------ Kate
            Kirigami.Separator {
                Kirigami.FormData.isSection: true
                Kirigami.FormData.label: qsTr("Kate")
            }
            RowLayout {
                Kirigami.FormData.label: qsTr("Program:")
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Icon {
                    source: page.kateCommand !== "" ? "kate" : "data-warning"
                    implicitWidth: Kirigami.Units.iconSizes.small
                    implicitHeight: Kirigami.Units.iconSizes.small
                }
                QQC2.Label {
                    text: page.kateCommand !== "" ? page.kateCommand : qsTr("Kate is not installed.")
                    font.family: page.kateCommand !== "" ? Kirigami.Theme.fixedWidthFont.family : Kirigami.Theme.defaultFont.family
                }
                Kirigami.UrlButton {
                    visible: page.kateCommand === ""
                    text: qsTr("Get Kate")
                    url: "https://apps.kde.org/kate/"
                }
            }
            QQC2.ComboBox {
                id: sessionBox
                Kirigami.FormData.label: qsTr("Session:")
                enabled: page.kateCommand !== ""
                editable: true
                Layout.preferredWidth: Kirigami.Units.gridUnit * 14
                model: [qsTr("No session")].concat(Backend.kateSessions())
                Component.onCompleted: {
                    const s = page.cfg.kate.session
                    if (s === "")
                        currentIndex = 0
                    else if (find(s) >= 0)
                        currentIndex = find(s)
                    else
                        editText = s
                }
                function store(text) {
                    page.cfg.kate.session = (text === qsTr("No session")) ? "" : text.trim()
                    page.commit(false)
                }
                onActivated: index => store(index === 0 ? "" : textAt(index))
                onAccepted: store(editText)
                QQC2.ToolTip.text: qsTr("Open the file in this Kate session, so it joins that project's window.")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.CheckBox {
                id: kateEditorBox
                Kirigami.FormData.label: qsTr("Source view:")
                text: qsTr("Use Kate's editor (needs a restart)")
                checked: page.cfg.useKateEditor !== false
                onToggled: {
                    page.cfg.useKateEditor = checked
                    page.commit(false)
                }
                QQC2.ToolTip.text: qsTr("The source view is Kate's own editor, from the installed Kate/KTextEditor: updates of Kate's editor apply here too, and its settings are shared with Kate.")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.Label {
                visible: kateEditorBox.checked && !Backend.kateEditorAvailable && Backend.kateEditorProblem !== ""
                Layout.maximumWidth: Kirigami.Units.gridUnit * 24
                wrapMode: Text.Wrap
                font: Kirigami.Theme.smallFont
                color: Kirigami.Theme.neutralTextColor
                text: qsTr("Not available: %1").arg(Backend.kateEditorProblem)
            }
            QQC2.CheckBox {
                text: Backend.kateEditorAvailable ? qsTr("Built-in editor: use Kate's colour theme, font and indentation")
                                                  : qsTr("Use Kate's colour theme, font and indentation")
                checked: page.cfg.useKateStyle
                onToggled: {
                    page.cfg.useKateStyle = checked
                    page.commit(false)
                }
                QQC2.ToolTip.text: qsTr("Kreator's source view highlights code with Kate's engine and follows the settings you chose in Kate.")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.CheckBox {
                Kirigami.FormData.label: qsTr("Window:")
                enabled: page.kateCommand !== ""
                text: qsTr("Always open a new Kate window")
                checked: page.cfg.kate.newWindow
                onToggled: {
                    page.cfg.kate.newWindow = checked
                    page.commit(false)
                }
            }
            QQC2.CheckBox {
                Kirigami.FormData.label: qsTr("Cursor:")
                enabled: page.kateCommand !== ""
                text: qsTr("Go to the selected object")
                checked: page.cfg.kate.gotoObject
                onToggled: {
                    page.cfg.kate.gotoObject = checked
                    page.commit(false)
                }
            }

            // ------------------------------------------------------------ other editors
            Kirigami.Separator {
                Kirigami.FormData.isSection: true
                Kirigami.FormData.label: qsTr("Other Editors")
            }
            QQC2.Label {
                Layout.maximumWidth: Kirigami.Units.gridUnit * 24
                wrapMode: Text.WordWrap
                text: qsTr("Add any editor by giving its program and the arguments to start it with. In the arguments, {file}, {line} and {column} are replaced with the file and the selected object's position.")
            }
            QQC2.Button {
                id: addButton
                text: qsTr("Add Editor…")
                icon.name: "list-add"
                onClicked: presetMenu.popup(addButton, 0, addButton.height)

                QQC2.Menu {
                    id: presetMenu
                    Repeater {
                        model: Backend.editorPresets()
                        delegate: QQC2.MenuItem {
                            required property var modelData
                            text: modelData.name
                            icon.name: modelData.icon
                            onTriggered: page.addEditor(modelData)
                        }
                    }
                }
            }
        }

        Repeater {
            model: page.cfg.custom
            delegate: Kirigami.FormLayout {
                id: editorForm

                required property var modelData
                required property int index
                readonly property string resolved: Backend.resolveCommand(commandField.text)

                Layout.fillWidth: true
                twinFormLayouts: [mainForm]

                function set(key, value) {
                    page.cfg.custom[index][key] = value
                    page.commit(false)
                }

                Kirigami.Separator {
                    Kirigami.FormData.isSection: true
                    Kirigami.FormData.label: nameField.text
                }
                QQC2.TextField {
                    id: nameField
                    Kirigami.FormData.label: qsTr("Name:")
                    text: editorForm.modelData.name
                    onEditingFinished: if (text.trim() !== "") editorForm.set("name", text.trim())
                }
                RowLayout {
                    Kirigami.FormData.label: qsTr("Program:")
                    Kirigami.FormData.buddyFor: commandField
                    spacing: Kirigami.Units.smallSpacing
                    QQC2.TextField {
                        id: commandField
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 16
                        text: editorForm.modelData.command
                        placeholderText: qsTr("e.g. /usr/bin/zed or flatpak run …")
                        font.family: Kirigami.Theme.fixedWidthFont.family
                        onEditingFinished: editorForm.set("command", text.trim())
                    }
                    QQC2.Button {
                        icon.name: "document-open"
                        text: qsTr("Browse…")
                        display: QQC2.AbstractButton.IconOnly
                        onClicked: programDialog.open()
                        QQC2.ToolTip.text: qsTr("Choose the program")
                        QQC2.ToolTip.visible: hovered
                        QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                        FileDialog {
                            id: programDialog
                            title: qsTr("Choose Editor Program")
                            currentFolder: "file:///usr/bin"
                            onAccepted: {
                                commandField.text = selectedFile.toString().replace(/^file:\/\//, "")
                                editorForm.set("command", commandField.text)
                            }
                        }
                    }
                    Kirigami.Icon {
                        source: editorForm.resolved !== "" ? "checkmark" : "data-warning"
                        implicitWidth: Kirigami.Units.iconSizes.small
                        implicitHeight: Kirigami.Units.iconSizes.small
                        QQC2.ToolTip.text: editorForm.resolved !== "" ? qsTr("Found: %1").arg(editorForm.resolved) : qsTr("This program was not found")
                        QQC2.ToolTip.visible: statusHover.hovered
                        HoverHandler {
                            id: statusHover
                        }
                    }
                }
                QQC2.TextField {
                    Kirigami.FormData.label: qsTr("Arguments:")
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 16
                    text: editorForm.modelData.args
                    placeholderText: "{file}"
                    font.family: Kirigami.Theme.fixedWidthFont.family
                    onEditingFinished: editorForm.set("args", text)
                }
                QQC2.Button {
                    text: qsTr("Remove Editor")
                    icon.name: "edit-delete-remove"
                    onClicked: {
                        const c = page.cfg
                        c.custom.splice(editorForm.index, 1)
                        page.cfg = c
                        page.commit(true)
                    }
                }
            }
        }
    }
}
