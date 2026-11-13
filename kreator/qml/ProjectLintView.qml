import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// qmllint diagnostics of all project files, grouped by file (collected by
// qmlls while indexing; the shown file's list follows your edits live).
// Click one to open the file in the source view at that line.
ColumnLayout {
    id: view
    spacing: 0

    // a finding was clicked (its file is being opened)
    signal activated()

    property string filter: ""
    property bool showErrors: true
    property bool showWarnings: true
    property bool showInfo: true
    property var collapsed: ({})        // path -> true
    readonly property int total: Lsp.projectErrorCount + Lsp.projectWarningCount + Lsp.projectInfoCount

    readonly property var rows: {
        const f = filter.toLowerCase()
        const out = []
        for (const d of Lsp.projectDiagnostics) {
            if (d.severity === 1 ? !showErrors : d.severity === 2 ? !showWarnings : !showInfo)
                continue
            if (f !== "" && d.message.toLowerCase().indexOf(f) < 0 && d.file.toLowerCase().indexOf(f) < 0)
                continue
            out.push(d)
        }
        return out
    }
    // per file: [shown, errors] for the section headers
    readonly property var perFile: {
        const m = {}
        for (const d of rows) {
            const e = m[d.file] || (m[d.file] = { count: 0, errors: 0, auto: 0, path: d.path })
            e.count++
            if (d.autoFix)
                e.auto++
            if (d.severity === 1)
                e.errors++
        }
        return m
    }

    function toggle(path) {
        const c = Object.assign({}, collapsed)
        if (c[path])
            delete c[path]
        else
            c[path] = true
        collapsed = c
    }
    // safe (automatic) fixes among the shown findings
    readonly property int autoCount: rows.filter(d => d.autoFix).length

    // Fixes become unsaved changes (files that aren't open open as tabs), so
    // they can be reviewed, undone and saved with Save All.
    function prepare(path) {
        // unapplied source view edits first, or the fix would hit stale text
        return path !== Backend.filePath || applicationWindow().mainPage.commitSource()
    }
    function applyFix(d) {
        if (!prepare(d.path) || !Lsp.applyProjectFix(d.path, d.index))
            return
        if (d.path !== Backend.filePath)
            applicationWindow().showPassiveNotification(qsTr("Fixed in %1 (unsaved; Save All with Ctrl+L)").arg(d.file))
    }
    function applyAll(path) {
        if (!prepare(path === "" ? Backend.filePath : path))
            return
        const n = Lsp.applyProjectFixes(path)
        applicationWindow().showPassiveNotification(n > 0 ? qsTr("Applied %n fix(es) as unsaved changes", "", n)
                                                          : qsTr("No safe fixes could be applied"))
    }
    function openToFix(d) {
        view.activated()
        applicationWindow().mainPage.openAt(d.path, d.line, d.character)
        applicationWindow().showPassiveNotification(qsTr("This fix needs an id: press Alt+Return in the source view to choose it"))
    }

    function severityIcon(s) {
        return s === 1 ? "data-error" : s === 2 ? "data-warning" : "data-information"
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.margins: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        Kirigami.SearchField {
            Layout.fillWidth: true
            focusSequences: []
            placeholderText: qsTr("Filter…")
            onTextChanged: view.filter = text
        }
        component SeverityToggle: QQC2.ToolButton {
            property int count
            property string what
            checkable: true
            text: count
            display: QQC2.AbstractButton.TextBesideIcon
            QQC2.ToolTip.text: checked ? qsTr("Hide %1").arg(what) : qsTr("Show %1").arg(what)
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            Accessible.name: qsTr("%1: %2").arg(what).arg(count)
        }
        SeverityToggle {
            icon.name: "data-error"
            count: Lsp.projectErrorCount
            what: qsTr("errors")
            checked: view.showErrors
            onToggled: view.showErrors = checked
        }
        SeverityToggle {
            icon.name: "data-warning"
            count: Lsp.projectWarningCount
            what: qsTr("warnings")
            checked: view.showWarnings
            onToggled: view.showWarnings = checked
        }
        SeverityToggle {
            icon.name: "data-information"
            count: Lsp.projectInfoCount
            what: qsTr("notes")
            visible: count > 0
            checked: view.showInfo
            onToggled: view.showInfo = checked
        }
        QQC2.ToolButton {
            icon.name: "tools-wizard"
            text: qsTr("Fix All")
            display: QQC2.AbstractButton.IconOnly
            enabled: view.autoCount > 0
            onClicked: view.applyAll("")
            QQC2.ToolTip.text: qsTr("Apply all %n safe fix(es). Files become unsaved tabs you can review, undo and save.", "", view.autoCount)
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
            // collapsed files keep their header: one placeholder row each
            model: {
                const out = []
                const seen = {}
                for (const d of view.rows) {
                    if (view.collapsed[d.path]) {
                        if (!seen[d.path]) {
                            seen[d.path] = true
                            out.push({ path: d.path, file: d.file, placeholder: true })
                        }
                    } else {
                        out.push(d)
                    }
                }
                return out
            }
            reuseItems: true

            section.property: "file"
            section.criteria: ViewSection.FullString
            section.delegate: QQC2.ItemDelegate {
                id: header
                required property string section
                readonly property var info: view.perFile[section] || { count: 0, errors: 0, path: "" }
                readonly property bool isCollapsed: !!view.collapsed[info.path]
                objectName: "lintFile:" + section
                width: ListView.view.width
                topPadding: Kirigami.Units.smallSpacing
                bottomPadding: Kirigami.Units.smallSpacing
                onClicked: view.toggle(info.path)
                Accessible.name: section + ", " + qsTr("%n problem(s)", "", info.count)
                background: Rectangle {
                    color: header.hovered ? Kirigami.Theme.hoverColor : Kirigami.Theme.alternateBackgroundColor
                    opacity: header.hovered ? 0.3 : 1
                }
                contentItem: RowLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon {
                        source: header.isCollapsed ? "go-next-symbolic" : "go-down-symbolic"
                        implicitWidth: Kirigami.Units.iconSizes.small
                        implicitHeight: Kirigami.Units.iconSizes.small
                        opacity: 0.7
                    }
                    QQC2.Label {
                        Layout.fillWidth: true
                        text: header.section
                        elide: Text.ElideMiddle
                        font.bold: header.info.path === Backend.filePath
                    }
                    QQC2.ToolButton {
                        visible: header.info.auto > 0
                        icon.name: "tools-wizard"
                        text: qsTr("Fix %1").arg(header.info.auto)
                        display: QQC2.AbstractButton.TextBesideIcon
                        font: Kirigami.Theme.smallFont
                        padding: 0
                        onClicked: view.applyAll(header.info.path)
                        QQC2.ToolTip.text: qsTr("Apply the %n safe fix(es) in this file", "", header.info.auto)
                        QQC2.ToolTip.visible: hovered
                        QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                    }
                    QQC2.Label {
                        text: header.info.errors > 0 ? qsTr("%1 · %2 errors").arg(header.info.count).arg(header.info.errors)
                                                     : header.info.count
                        font: Kirigami.Theme.smallFont
                        color: header.info.errors > 0 ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.disabledTextColor
                    }
                }
            }

            delegate: QQC2.ItemDelegate {
                id: row
                required property var modelData
                required property int index
                readonly property bool placeholder: modelData.placeholder === true
                objectName: placeholder ? "" : "lint:" + modelData.file + ":" + (modelData.line + 1)
                width: ListView.view.width
                height: placeholder ? 0 : implicitHeight
                visible: !placeholder
                leftPadding: Kirigami.Units.gridUnit
                topPadding: Kirigami.Units.smallSpacing
                bottomPadding: Kirigami.Units.smallSpacing
                onClicked: {
                    view.activated()
                    applicationWindow().mainPage.openAt(modelData.path, modelData.line, modelData.character)
                }
                Accessible.name: placeholder ? "" : modelData.message
                QQC2.ToolTip.text: placeholder ? "" : modelData.message
                QQC2.ToolTip.visible: hovered && !placeholder && msg.truncated
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay

                contentItem: RowLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon {
                        Layout.alignment: Qt.AlignTop
                        source: row.placeholder ? "" : view.severityIcon(row.modelData.severity)
                        implicitWidth: Kirigami.Units.iconSizes.small
                        implicitHeight: Kirigami.Units.iconSizes.small
                    }
                    QQC2.Label {
                        id: msg
                        Layout.fillWidth: true
                        text: row.placeholder ? "" : row.modelData.message
                        wrapMode: Text.Wrap
                        maximumLineCount: 3
                        elide: Text.ElideRight
                        color: row.highlighted ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor
                    }
                    ColumnLayout {
                        Layout.alignment: Qt.AlignTop
                        spacing: 0
                        QQC2.Label {
                            Layout.alignment: Qt.AlignRight
                            text: row.placeholder ? "" : qsTr("line %1").arg(row.modelData.line + 1)
                            font: Kirigami.Theme.smallFont
                            color: Kirigami.Theme.disabledTextColor
                        }
                        QQC2.Button {
                            objectName: "lintFix"
                            visible: !row.placeholder && (row.modelData.fix !== "" || row.modelData.needsInput)
                            icon.name: "tools-wizard"
                            text: row.placeholder || !row.modelData.needsInput ? qsTr("Fix") : qsTr("Fix…")
                            onClicked: row.modelData.needsInput ? view.openToFix(row.modelData) : view.applyFix(row.modelData)
                            QQC2.ToolTip.text: row.placeholder ? "" : row.modelData.needsInput
                                               ? qsTr("Qualify with an id you choose (opens the source view)")
                                               : row.modelData.fix + (row.modelData.fixDetail !== "" && row.modelData.fixDetail !== row.modelData.fix
                                                                      ? "\n" + row.modelData.fixDetail : "")
                            QQC2.ToolTip.visible: hovered
                            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                        }
                    }
                }
            }

            Kirigami.PlaceholderMessage {
                anchors.centerIn: parent
                width: parent.width - Kirigami.Units.largeSpacing * 4
                visible: list.count === 0
                icon.name: Lsp.indexing ? "search" : (!Lsp.available || !Lsp.enabled ? "data-information" : "checkmark")
                text: !Lsp.enabled ? qsTr("qmllint needs the QML language server, which is switched off")
                      : !Lsp.available ? qsTr("qmllint needs the QML language server (qmlls)")
                      : Lsp.indexing ? qsTr("Checking the project…")
                      : view.total > 0 ? qsTr("Nothing matches")
                      : Backend.projectPath === "" && !Backend.hasDocument ? qsTr("Open a folder to check its files")
                      : qsTr("No problems found")
            }
        }
    }
}
