import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

// An application as Kirigami ones are built: a sidebar, a drawer at each of
// the other edges, and a dialog that opens over all of it.
Kirigami.ApplicationWindow {
    id: root

    width: Kirigami.Units.gridUnit * 34
    height: Kirigami.Units.gridUnit * 22

    globalDrawer: Kirigami.GlobalDrawer {
        objectName: "sidebar"
        modal: false
        collapsible: false
        width: Kirigami.Units.gridUnit * 10
        Component.onCompleted: drawerOpen = true
        actions: [
            Kirigami.Action {
                text: "Calendars"
            }
        ]
    }

    contextDrawer: Kirigami.OverlayDrawer {
        objectName: "rightDrawer"
        edge: Qt.RightEdge
        modal: false
        handleVisible: false
        width: Kirigami.Units.gridUnit * 6
        Component.onCompleted: drawerOpen = true
        contentItem: QQC2.Label {
            text: "Details"
        }
    }

    pageStack.initialPage: Kirigami.Page {
        title: "Page"

        QQC2.Label {
            anchors.centerIn: parent
            text: "Content"
        }
    }

    QQC2.Drawer {
        objectName: "bottomDrawer"
        edge: Qt.BottomEdge
        modal: false
        interactive: false
        visible: true
        width: root.width
        height: Kirigami.Units.gridUnit * 2

        QQC2.Label {
            text: "Status"
        }
    }

    QQC2.Dialog {
        objectName: "dialog"
        anchors.centerIn: QQC2.Overlay.overlay
        modal: true
        visible: true
        title: "Dialog"

        QQC2.Label {
            text: "A modal dialog"
        }
    }
}
