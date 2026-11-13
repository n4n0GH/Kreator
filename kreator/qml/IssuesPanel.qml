import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// Guidelines: the KDE HIG checks of the current document, and qmllint's
// diagnostics (from qmlls, the same as in the source view) for every file
// of the project.
ColumnLayout {
    id: panel
    spacing: 0

    // "hig" or "lint"; without a document only the project's lint makes sense
    property string mode: "hig"
    readonly property string shownMode: Backend.hasDocument ? mode : "lint"

    RowLayout {
        Layout.fillWidth: true
        Layout.margins: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        QQC2.ButtonGroup {
            id: modeGroup
        }
        QQC2.ToolButton {
            Layout.fillWidth: true
            enabled: Backend.hasDocument
            checkable: true
            checked: panel.shownMode === "hig"
            QQC2.ButtonGroup.group: modeGroup
            icon.name: "kde"
            text: Backend.issueCount > 0 ? qsTr("KDE HIG (%1)").arg(Backend.issueCount) : qsTr("KDE HIG")
            onClicked: panel.mode = "hig"
            QQC2.ToolTip.text: qsTr("Checks of this document based on the KDE Human Interface Guidelines")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
        QQC2.ToolButton {
            Layout.fillWidth: true
            checkable: true
            checked: panel.shownMode === "lint"
            QQC2.ButtonGroup.group: modeGroup
            icon.name: Lsp.projectErrorCount > 0 ? "data-error" : (Lsp.projectWarningCount > 0 ? "data-warning" : "checkmark")
            readonly property int count: Lsp.projectErrorCount + Lsp.projectWarningCount
            text: count > 0 ? qsTr("qmllint (%1)").arg(count) : qsTr("qmllint")
            onClicked: panel.mode = "lint"
            QQC2.ToolTip.text: qsTr("qmllint's findings in all files of the project")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
    }

    Kirigami.Separator {
        Layout.fillWidth: true
    }

    ProjectLintView {
        id: lintView
        // stay on this list while working through its findings
        onActivated: panel.mode = "lint"
        visible: panel.shownMode === "lint"
        Layout.fillWidth: true
        Layout.fillHeight: true
    }

    RowLayout {
        visible: panel.shownMode === "hig"
        Layout.fillWidth: true
        Layout.margins: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        QQC2.Label {
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.smallSpacing
            wrapMode: Text.WordWrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: qsTr("Checks based on the KDE Human Interface Guidelines.")
        }
        QQC2.Button {
            text: qsTr("Fix All")
            icon.name: "tools-wizard"
            enabled: Backend.issueCount > 0
            onClicked: Backend.applyAllFixes()
            QQC2.ToolTip.text: qsTr("Apply every automatic fix")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
    }

    Kirigami.Separator {
        visible: panel.shownMode === "hig"
        Layout.fillWidth: true
    }

    QQC2.ScrollView {
        visible: panel.shownMode === "hig"
        Layout.fillWidth: true
        Layout.fillHeight: true
        background: Rectangle {
            color: Kirigami.Theme.backgroundColor
        }

        ListView {
            id: issueView
            clip: true
            model: Backend.issueModel

            delegate: QQC2.ItemDelegate {
                id: issue

                required property int index
                required property int uid
                required property string severity
                required property string title
                required property string detail
                required property bool fixable
                required property string nodeLabel

                width: ListView.view.width
                highlighted: uid === Backend.selectedUid
                onClicked: Backend.select(uid)
                Accessible.name: title

                contentItem: RowLayout {
                    spacing: Kirigami.Units.largeSpacing

                    Kirigami.Icon {
                        Layout.alignment: Qt.AlignTop
                        source: issue.severity === "warning" ? "data-warning" : "data-information"
                        implicitWidth: Kirigami.Units.iconSizes.smallMedium
                        implicitHeight: Kirigami.Units.iconSizes.smallMedium
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing / 2

                        QQC2.Label {
                            Layout.fillWidth: true
                            text: issue.title
                            wrapMode: Text.WordWrap
                            font.bold: true
                            color: issue.highlighted ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor
                        }
                        QQC2.Label {
                            Layout.fillWidth: true
                            text: issue.detail
                            wrapMode: Text.WordWrap
                            font: Kirigami.Theme.smallFont
                            color: issue.highlighted ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor
                            opacity: 0.85
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            QQC2.Label {
                                Layout.fillWidth: true
                                text: issue.nodeLabel
                                elide: Text.ElideRight
                                font: Kirigami.Theme.smallFont
                                color: issue.highlighted ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.disabledTextColor
                            }
                            QQC2.Button {
                                visible: issue.fixable
                                text: qsTr("Fix")
                                icon.name: "tools-wizard"
                                onClicked: Backend.applyFix(issue.index)
                            }
                        }
                    }
                }
            }

            Kirigami.PlaceholderMessage {
                anchors.centerIn: parent
                width: parent.width - Kirigami.Units.largeSpacing * 4
                visible: issueView.count === 0
                icon.name: "checkmark"
                text: qsTr("No issues found")
                explanation: qsTr("This document follows the checked guidelines.")
            }
        }
    }
}
