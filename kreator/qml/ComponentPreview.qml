import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// What a component of the Add tab looks like before it is added: the live
// component (or a picture of the widget) with its full description, shown
// beside the sidebar for one row of the list, like a page of Kirigami
// Gallery. It is looked at, not used: it takes neither the mouse nor the
// keyboard.
Item {
    id: flyout
    objectName: "componentPreview"

    // the sidebar it goes beside
    required property Item panel
    // the row to show (a delegate of the list: its `index`, `name`, `iconName`,
    // `description` and `module`), or null for none
    property Item row: null

    // the row that is shown; it stays while the next one is waited for
    property Item shownRow: null
    property int shownIndex: -1
    property string name
    property string iconName
    property string description
    property string module
    // Backend.componentPreview()'s answer
    property var content: ({ kind: "", note: "" })
    readonly property bool active: shownIndex >= 0

    parent: QQC2.Overlay.overlay
    z: 1
    width: Kirigami.Units.gridUnit * 20
    height: column.implicitHeight
    visible: active
    // (fades in; gone at once, with what it showed)
    opacity: active ? 1 : 0
    Behavior on opacity {
        enabled: flyout.active
        NumberAnimation {
            duration: Kirigami.Units.shortDuration
        }
    }

    onRowChanged: {
        if (row !== null) {
            hideTimer.stop()
            // the first one after a moment, like a tooltip; the next ones as
            // the pointer gets to them (but not every row it passes over)
            showTimer.interval = active ? 80 : Kirigami.Units.toolTipDelay
            showTimer.restart()
        } else {
            showTimer.stop()
            hideTimer.restart()
        }
    }

    Timer {
        id: showTimer
        onTriggered: flyout.load()
    }
    Timer {
        id: hideTimer
        interval: 150
        onTriggered: flyout.unload()
    }

    function load() {
        if (row === null)
            return
        if (shownRow !== row || shownIndex !== row.index) {
            shownRow = row
            name = row.name
            iconName = row.iconName
            description = row.description
            module = row.module
            content = Backend.componentPreview(row.index, stage)
            if (content.kind === "item")
                content.item.anchors.fill = stage
            // (after the content, which `active` shows)
            shownIndex = row.index
        }
        place()
    }
    function unload() {
        showTimer.stop()
        hideTimer.stop()
        if (!active)
            return
        shownIndex = -1
        shownRow = null
        content = { kind: "", note: "" }
        Backend.clearComponentPreview()
    }

    // Beside the sidebar, on the side with room for it, level with its row.
    function place() {
        const area = parent
        if (!area || shownRow === null)
            return
        const gap = Kirigami.Units.smallSpacing
        const left = panel.mapToItem(area, 0, 0).x
        const right = left + panel.width
        x = right + gap + width <= area.width || left - gap - width < 0 ? right + gap : left - gap - width
        const mid = shownRow.mapToItem(area, 0, shownRow.height / 2).y
        y = Math.max(gap, Math.min(area.height - height - gap, Math.round(mid - height / 2)))
    }
    onHeightChanged: place()

    Kirigami.ShadowedRectangle {
        anchors.fill: parent
        Kirigami.Theme.colorSet: Kirigami.Theme.View
        Kirigami.Theme.inherit: false
        color: Kirigami.Theme.backgroundColor
        radius: Kirigami.Units.cornerRadius
        border.width: 1
        border.color: Kirigami.ColorUtils.linearInterpolation(Kirigami.Theme.backgroundColor, Kirigami.Theme.textColor, Kirigami.Theme.frameContrast)
        shadow.size: Kirigami.Units.gridUnit
        shadow.color: Qt.rgba(0, 0, 0, 0.25)
        shadow.yOffset: 2
    }

    ColumnLayout {
        id: column
        // (inside the frame's border)
        x: 1
        y: 1
        width: parent.width - 2
        spacing: 0

        Kirigami.Theme.colorSet: Kirigami.Theme.View
        Kirigami.Theme.inherit: false

        ColumnLayout {
            Layout.fillWidth: true
            Layout.margins: Kirigami.Units.largeSpacing
            spacing: Kirigami.Units.smallSpacing

            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                Kirigami.Icon {
                    source: flyout.iconName
                    implicitWidth: Kirigami.Units.iconSizes.smallMedium
                    implicitHeight: Kirigami.Units.iconSizes.smallMedium
                }
                Kirigami.Heading {
                    objectName: "componentPreviewName"
                    level: 4
                    text: flyout.name
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                QQC2.Label {
                    text: flyout.module
                    font: Kirigami.Theme.smallFont
                    color: Kirigami.Theme.disabledTextColor
                }
            }
            QQC2.Label {
                Layout.fillWidth: true
                text: flyout.description
                wrapMode: Text.WordWrap
            }
        }

        Kirigami.Separator {
            Layout.fillWidth: true
        }

        // the stage: a piece of window for the component to stand on
        Item {
            id: stageFrame
            Layout.fillWidth: true
            Layout.bottomMargin: 1
            implicitHeight: {
                const unit = Kirigami.Units.gridUnit
                const c = flyout.content
                const wanted = c.kind === "item" ? c.item.implicitHeight
                             : c.kind === "image" ? c.height : Kirigami.Units.iconSizes.huge
                return Math.round(Math.max(unit * 3, Math.min(unit * 16, wanted))) + stage.anchors.margins * 2
            }
            clip: true

            Kirigami.Theme.colorSet: Kirigami.Theme.Window
            Kirigami.Theme.inherit: false

            Rectangle {
                anchors.fill: parent
                color: Kirigami.Theme.backgroundColor
                bottomLeftRadius: Kirigami.Units.cornerRadius - 1
                bottomRightRadius: Kirigami.Units.cornerRadius - 1
                visible: noteLabel.text === ""
            }
            Rectangle {
                anchors.fill: parent
                color: Kirigami.Theme.backgroundColor
                visible: noteLabel.text !== ""
            }

            // (a focus scope that never has the focus: a component that asks
            // for it gets it in here only, not from where the user types)
            FocusScope {
                id: stage
                objectName: "componentPreviewStage"
                anchors.fill: parent
                anchors.margins: Kirigami.Units.largeSpacing
            }

            Image {
                objectName: "componentPreviewImage"
                anchors.centerIn: parent
                visible: flyout.content.kind === "image"
                // (a new picture every time: nothing to keep)
                cache: false
                source: visible ? flyout.content.source : ""
                width: visible ? flyout.content.width : 0
                height: visible ? flyout.content.height : 0
            }

            Kirigami.Icon {
                anchors.centerIn: parent
                visible: flyout.content.kind === "none"
                source: flyout.iconName
                implicitWidth: Kirigami.Units.iconSizes.huge
                implicitHeight: Kirigami.Units.iconSizes.huge
                opacity: 0.5
            }

            // looked at, not used
            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.AllButtons
                hoverEnabled: true
                onWheel: wheel => wheel.accepted = true
            }
        }

        Kirigami.Separator {
            Layout.fillWidth: true
            visible: noteLabel.text !== ""
        }
        QQC2.Label {
            id: noteLabel
            objectName: "componentPreviewNote"
            Layout.fillWidth: true
            Layout.margins: Kirigami.Units.largeSpacing
            visible: text !== ""
            text: flyout.content.note || ""
            wrapMode: Text.WordWrap
            font: Kirigami.Theme.smallFont
            color: Kirigami.Theme.disabledTextColor
        }
    }
}
