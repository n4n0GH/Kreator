import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// Background work at the bottom of the sidebar, like Discover shows its
// installs: indexing the project's symbols, then loading the types of the
// imported modules. Shows "done" briefly, then hides.
ColumnLayout {
    id: status
    spacing: 0

    readonly property bool busy: Lsp.indexing || Lsp.loadingTypes
    property bool showDone: false
    property int lastTotal: 0

    visible: busy || showDone

    Connections {
        target: Lsp
        function onIndexChanged() {
            if (Lsp.indexing)
                status.lastTotal = Lsp.indexTotal
            if (status.busy) {
                status.showDone = false
                doneTimer.stop()
            } else if (status.lastTotal > 0 && !status.showDone && !doneTimer.running) {
                status.showDone = true
                doneTimer.restart()
            }
        }
    }
    Timer {
        id: doneTimer
        interval: 3000
        onTriggered: {
            status.showDone = false
            status.lastTotal = 0
        }
    }

    Kirigami.Separator {
        Layout.fillWidth: true
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.margins: Kirigami.Units.smallSpacing * 2
        spacing: Kirigami.Units.largeSpacing

        Kirigami.Icon {
            source: status.busy ? "code-class" : "checkmark"
            implicitWidth: Kirigami.Units.iconSizes.smallMedium
            implicitHeight: Kirigami.Units.iconSizes.smallMedium
            Layout.alignment: Qt.AlignVCenter
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing / 2

            QQC2.Label {
                Layout.fillWidth: true
                elide: Text.ElideRight
                text: Lsp.indexing ? qsTr("Indexing and checking files…")
                      : Lsp.loadingTypes ? qsTr("Loading types…")
                      : qsTr("%n file(s) indexed", "", status.lastTotal)
            }
            QQC2.ProgressBar {
                Layout.fillWidth: true
                visible: status.busy
                from: 0
                to: Math.max(1, Lsp.indexTotal)
                value: Lsp.indexDone
                indeterminate: !Lsp.indexing
            }
            QQC2.Label {
                Layout.fillWidth: true
                visible: Lsp.indexing
                elide: Text.ElideMiddle
                font: Kirigami.Theme.smallFont
                opacity: 0.7
                text: qsTr("%1 of %2").arg(Lsp.indexDone).arg(Lsp.indexTotal)
                      + (Lsp.indexFile !== "" ? " · " + Lsp.indexFile : "")
            }
        }
    }

    Accessible.role: Accessible.StatusBar
    Accessible.name: Lsp.indexing ? qsTr("Indexing and checking files, %1 of %2").arg(Lsp.indexDone).arg(Lsp.indexTotal)
                                   : (Lsp.loadingTypes ? qsTr("Loading types") : "")
}
