import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kreator.kate

// Prototype: Kate's editor inside a Kirigami window, laid out like Kreator's
// source view. Things to try are listed in the left pane.
Kirigami.ApplicationWindow {
    id: root
    width: 1300
    height: 800
    visible: true
    title: "Kate editor in Kreator (prototype)"

    pageStack.initialPage: Kirigami.Page {
        title: "KTextEditor " + editor.frameworkVersion
        padding: 0

        actions: [
            Kirigami.Action {
                text: "Menu"
                icon.name: "application-menu"
                onTriggered: sceneMenu.popup()
            },
            Kirigami.Action {
                text: "Dialog"
                icon.name: "dialog-messages"
                onTriggered: dialog.open()
            },
            Kirigami.Action {
                text: "Notification"
                icon.name: "notifications"
                onTriggered: root.showPassiveNotification("A passive notification over the editor area")
            },
            Kirigami.Action {
                text: "Go to line 10"
                icon.name: "go-jump"
                onTriggered: {
                    editor.setCursorPosition(9, 4)
                    editor.focusEditor()
                }
            }
        ]

        Kirigami.PromptDialog {
            id: dialog
            title: "A dialog over the editor"
            subtitle: "While it's open the editor shows a snapshot of itself, so this isn't covered."
            standardButtons: Kirigami.Dialog.Ok
        }

        // the usual in-scene popup: expected to be hidden behind the editor
        QQC2.Menu {
            id: sceneMenu
            objectName: "sceneMenu"
            QQC2.MenuItem { text: "In-scene popup (may be covered by the editor)" }
            QQC2.MenuItem { text: "Second item" }
        }
        QQC2.SplitView {
            anchors.fill: parent

            ColumnLayout {
                QQC2.SplitView.preferredWidth: Kirigami.Units.gridUnit * 16
                spacing: Kirigami.Units.largeSpacing
                QQC2.Label {
                    Layout.fillWidth: true
                    Layout.margins: Kirigami.Units.largeSpacing
                    wrapMode: Text.Wrap
                    text: "Please try:\n\n"
                          + "• typing, selecting with the mouse, scrolling\n"
                          + "• Kate shortcuts in the editor (Ctrl+F, Ctrl+G, Ctrl+D, Alt+Shift+arrows, Ctrl+Space)\n"
                          + "• Kate's own popups: word completion, context menu\n"
                          + "• clicking the field below, then back into the editor (focus)\n"
                          + "• dragging the dividers and resizing the window\n"
                          + "• the toolbar menus and the dialog over the editor (now drawn above it)\n"
                          + "• the notification (not handled yet: expected under the editor)\n"
                          + "• HiDPI / fractional scaling sharpness"
                }
                QQC2.TextField {
                    Layout.fillWidth: true
                    Layout.margins: Kirigami.Units.largeSpacing
                    placeholderText: "A QML text field, for focus tests"
                }
                QQC2.Label {
                    Layout.fillWidth: true
                    Layout.margins: Kirigami.Units.largeSpacing
                    text: "Cursor: %1:%2\nCharacters: %3\nEdits seen by QML: %4\nEditor has focus: %5\nFrozen (popup open): %6"
                          .arg(editor.cursorLine + 1).arg(editor.cursorColumn + 1)
                          .arg(editor.text.length).arg(edits.count).arg(editor.editorFocus).arg(editor.frozen)
                    QtObject {
                        id: edits
                        property int count: 0
                    }
                    Connections {
                        target: editor
                        function onTextEdited() { edits.count++ }
                    }
                }
                Item { Layout.fillHeight: true }
            }

            KateEditor {
                id: editor
                QQC2.SplitView.fillWidth: true
                // anything open in the popup layer except notifications
                frozen: {
                    const ov = root.QQC2.Overlay.overlay
                    if (!ov)
                        return false
                    for (const c of ov.children) {
                        if (c.visible && !String(c).startsWith("PassiveNotificationsManager"))
                            return true
                    }
                    return false
                }
                mode: "QML"
                text: demoText
            }

            Rectangle {
                QQC2.SplitView.preferredWidth: Kirigami.Units.gridUnit * 14
                color: Kirigami.Theme.backgroundColor
                QQC2.Label {
                    anchors.centerIn: parent
                    text: "(property panel)"
                    opacity: 0.6
                }
            }
        }
    }
}
