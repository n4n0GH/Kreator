import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Templates as T
import QtQuick.Layouts
import QtCore
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: pane
    spacing: 0

    property bool interact: false
    property int sizePreset: 0
    readonly property var presets: [
        { name: qsTr("Fit to View"), w: 0, h: 0 },
        { name: qsTr("Phone (360 × 720)"), w: 360, h: 720 },
        { name: qsTr("Phone Landscape (720 × 360)"), w: 720, h: 360 },
        { name: qsTr("Tablet (800 × 1280)"), w: 800, h: 1280 },
        { name: qsTr("Laptop (1280 × 800)"), w: 1280, h: 800 },
        { name: qsTr("Desktop (1920 × 1080)"), w: 1920, h: 1080 }
    ]
    readonly property bool isUi: Backend.docKind === "ui"

    property QtObject attached: null
    property Item pageHost: null
    property real naturalWidth: 0
    property real naturalHeight: 0
    property real zoom: 1
    // narrow: the toolbar's buttons without their labels
    readonly property bool compactToolBar: width < Kirigami.Units.gridUnit * 38

    // ------------------------------------------------------------ design grid
    // Measured in Kirigami's units, as KDE's guidelines measure spacing and
    // sizes; objects placed on it are given positions in those units
    // ("Kirigami.Units.largeSpacing * 3"), so they follow the user's font and
    // scale settings like the rest of the application.
    Settings {
        id: gridSettings
        category: "designGrid"
        property bool showGrid: false
        property bool snap: true
        property int size: 1
        // arrow keys also stop where the object lines up with others
        property bool nudgeToGuides: false
    }
    readonly property var gridUnits: [
        { unit: "smallSpacing", name: qsTr("Small Spacing"), size: Kirigami.Units.smallSpacing },
        { unit: "largeSpacing", name: qsTr("Large Spacing"), size: Kirigami.Units.largeSpacing },
        { unit: "gridUnit", name: qsTr("Grid Unit"), size: Kirigami.Units.gridUnit }
    ]
    readonly property var gridUnit: gridUnits[Math.max(0, Math.min(gridUnits.length - 1, gridSettings.size))]
    readonly property real gridStep: gridUnit.size
    readonly property alias showGrid: gridSettings.showGrid
    readonly property alias snapToGrid: gridSettings.snap

    // a coordinate of the design view on the grid (unless snapping is off, or
    // `free`: Shift held)
    function snapped(v, free) {
        return gridSettings.snap && !free ? Math.round(v / gridStep) * gridStep : Math.round(v)
    }
    // the next grid line from v in direction d (-1, 1)
    function nextLine(v, d) {
        if (d === 0)
            return v
        const k = d > 0 ? Math.floor(v / gridStep + 1e-6) + 1 : Math.ceil(v / gridStep - 1e-6) - 1
        return k * gridStep
    }
    // what Backend.placeAt / insertComponentAt write positions in
    function placeStep(free) {
        return gridSettings.snap && !free ? gridStep : 0
    }
    function placeUnit(free) {
        return gridSettings.snap && !free ? gridUnit.unit : ""
    }

    // ------------------------------------------------------------ toolbar
    QQC2.ToolBar {
        Layout.fillWidth: true
        position: QQC2.ToolBar.Header

        RowLayout {
            anchors.fill: parent
            spacing: Kirigami.Units.smallSpacing

            QQC2.ToolButton {
                icon.name: "edit-select"
                text: qsTr("Select")
                display: pane.compactToolBar ? QQC2.AbstractButton.IconOnly : QQC2.AbstractButton.TextBesideIcon
                checkable: true
                checked: !pane.interact
                autoExclusive: true
                enabled: !pane.isUi
                QQC2.ToolTip.text: qsTr("Click on the preview to select objects")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                onClicked: pane.interact = false
            }
            QQC2.ToolButton {
                icon.name: "input-mouse"
                text: qsTr("Interact")
                display: pane.compactToolBar ? QQC2.AbstractButton.IconOnly : QQC2.AbstractButton.TextBesideIcon
                checkable: true
                checked: pane.interact
                autoExclusive: true
                enabled: !pane.isUi
                QQC2.ToolTip.text: qsTr("Use the preview like the real application")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                onClicked: pane.interact = true
            }

            Kirigami.Separator {
                Layout.fillHeight: true
                Layout.topMargin: Kirigami.Units.smallSpacing
                Layout.bottomMargin: Kirigami.Units.smallSpacing
            }

            QQC2.ComboBox {
                id: presetBox
                model: pane.presets
                textRole: "name"
                currentIndex: pane.sizePreset
                enabled: !pane.isUi
                // gives way first when the pane is narrow (the text is elided)
                Layout.fillWidth: true
                Layout.maximumWidth: implicitWidth
                Layout.minimumWidth: Kirigami.Units.gridUnit * 4
                Accessible.name: qsTr("Preview size")
                onActivated: index => pane.sizePreset = index
            }

            QQC2.ToolButton {
                icon.name: "zoom-out"
                text: qsTr("Zoom Out")
                display: QQC2.AbstractButton.IconOnly
                enabled: pane.zoom > 0.26
                onClicked: pane.zoom = Math.max(0.25, pane.zoom - 0.25)
                QQC2.ToolTip.text: text
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.Label {
                text: Math.round(pane.zoom * 100) + "%"
                Layout.minimumWidth: Kirigami.Units.gridUnit * 2
                horizontalAlignment: Text.AlignHCenter
            }
            QQC2.ToolButton {
                icon.name: "zoom-in"
                text: qsTr("Zoom In")
                display: QQC2.AbstractButton.IconOnly
                enabled: pane.zoom < 2
                onClicked: pane.zoom = Math.min(2, pane.zoom + 0.25)
                QQC2.ToolTip.text: text
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }

            Kirigami.Separator {
                Layout.fillHeight: true
                Layout.topMargin: Kirigami.Units.smallSpacing
                Layout.bottomMargin: Kirigami.Units.smallSpacing
            }

            QQC2.ToolButton {
                objectName: "showGridButton"
                icon.name: "view-grid"
                text: qsTr("Show Grid")
                display: QQC2.AbstractButton.IconOnly
                checkable: true
                checked: gridSettings.showGrid
                onToggled: gridSettings.showGrid = checked
                QQC2.ToolTip.text: text
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.ToolButton {
                objectName: "snapButton"
                icon.name: "snap"
                text: qsTr("Snap to Grid")
                display: QQC2.AbstractButton.IconOnly
                checkable: true
                checked: gridSettings.snap
                onToggled: gridSettings.snap = checked
                QQC2.ToolTip.text: qsTr("Snap objects you place or move to the grid (hold Shift to place them freely)")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.ToolButton {
                id: gridSizeButton
                objectName: "gridSizeButton"
                text: qsTr("%1 px").arg(pane.gridStep)
                icon.name: "arrow-down"
                icon.width: Kirigami.Units.iconSizes.small
                icon.height: Kirigami.Units.iconSizes.small
                LayoutMirroring.enabled: true   // the arrow after the text
                down: gridSizeMenu.visible
                Accessible.name: qsTr("Grid size: %1").arg(pane.gridUnit.name)
                onClicked: gridSizeMenu.popup(gridSizeButton, 0, gridSizeButton.height)
                QQC2.ToolTip.text: qsTr("Grid size: %1 (Kirigami.Units.%2), and alignment options").arg(pane.gridUnit.name).arg(pane.gridUnit.unit)
                QQC2.ToolTip.visible: hovered && !gridSizeMenu.visible
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay

                QQC2.Menu {
                    id: gridSizeMenu
                    QQC2.ActionGroup {
                        id: gridSizeGroup
                    }
                    Repeater {
                        model: pane.gridUnits
                        QQC2.MenuItem {
                            required property var modelData
                            required property int index
                            text: qsTr("%1 (%2 px)").arg(modelData.name).arg(modelData.size)
                            checkable: true
                            checked: gridSettings.size === index
                            QQC2.ActionGroup.group: gridSizeGroup
                            onTriggered: gridSettings.size = index
                        }
                    }
                    QQC2.MenuSeparator {}
                    QQC2.MenuItem {
                        objectName: "nudgeToGuidesItem"
                        text: qsTr("Arrow Keys Stop at Guides")
                        checkable: true
                        checked: gridSettings.nudgeToGuides
                        onToggled: gridSettings.nudgeToGuides = checked
                        QQC2.ToolTip.text: qsTr("Arrow keys also stop where the object's sides or centre line up with the objects next to it")
                        QQC2.ToolTip.visible: hovered
                        QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                    }
                }
            }

            Item {
                Layout.fillWidth: true
            }

            QQC2.ToolButton {
                icon.name: "view-refresh"
                text: qsTr("Reload Preview")
                display: QQC2.AbstractButton.IconOnly
                onClicked: Backend.refresh_preview()
                QQC2.ToolTip.text: text
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
        }
    }

    Kirigami.InlineMessage {
        Layout.fillWidth: true
        Layout.margins: Kirigami.Units.smallSpacing
        type: Kirigami.MessageType.Error
        visible: Backend.previewError !== ""
        text: Backend.previewError
        showCloseButton: false
    }
    Kirigami.InlineMessage {
        Layout.fillWidth: true
        Layout.margins: Kirigami.Units.smallSpacing
        type: Kirigami.MessageType.Warning
        visible: Backend.previewNote !== "" && Backend.previewError === "" && Backend.previewNote !== pane.dismissedNote
        text: Backend.previewNote
        actions: [
            Kirigami.Action {
                icon.name: "dialog-close"
                text: qsTr("Dismiss")
                displayHint: Kirigami.DisplayHint.IconOnly
                onTriggered: pane.dismissedNote = Backend.previewNote
            }
        ]
    }

    // ------------------------------------------------------------ canvas
    Rectangle {
        id: canvasBg
        Layout.fillWidth: true
        Layout.fillHeight: true
        color: Qt.darker(Kirigami.Theme.backgroundColor, 1.08)
        clip: true

        Kirigami.Theme.colorSet: Kirigami.Theme.Window
        Kirigami.Theme.inherit: false

        readonly property real margin: Kirigami.Units.gridUnit * 1.5

        Flickable {
            id: flick
            anchors.fill: parent
            contentWidth: Math.max(width, frame.width * pane.zoom + canvasBg.margin * 2)
            contentHeight: Math.max(height, frame.height * pane.zoom + canvasBg.margin * 2)
            boundsBehavior: Flickable.StopAtBounds
            interactive: false
            QQC2.ScrollBar.vertical: QQC2.ScrollBar {}
            QQC2.ScrollBar.horizontal: QQC2.ScrollBar {}

            WheelHandler {
                acceptedModifiers: Qt.ControlModifier
                onWheel: event => {
                    pane.zoom = Math.max(0.25, Math.min(2, pane.zoom + (event.angleDelta.y > 0 ? 0.1 : -0.1)))
                }
            }

            Item {
                id: scaler
                width: frame.width * pane.zoom
                height: frame.height * pane.zoom
                x: Math.max(canvasBg.margin, (flick.contentWidth - width) / 2)
                y: Math.max(canvasBg.margin, (flick.contentHeight - height) / 2)

                Kirigami.ShadowedRectangle {
                    id: frame

                    readonly property var preset: pane.presets[pane.sizePreset]
                    readonly property bool fills: pane.isUi ? false : (pane.naturalWidth <= 0 || pane.naturalHeight <= 0)
                    readonly property real fitWidth: (flick.width - canvasBg.margin * 2) / pane.zoom
                    readonly property real fitHeight: (flick.height - canvasBg.margin * 2) / pane.zoom

                    transformOrigin: Item.TopLeft
                    scale: pane.zoom
                    width: pane.isUi ? Backend.uiWidth : (preset.w > 0 ? preset.w : (fills ? Math.max(Kirigami.Units.gridUnit * 10, fitWidth) : pane.naturalWidth))
                    height: pane.isUi ? Backend.uiHeight : (preset.h > 0 ? preset.h : (fills ? Math.max(Kirigami.Units.gridUnit * 8, fitHeight) : pane.naturalHeight))
                    color: Kirigami.Theme.backgroundColor
                    radius: Kirigami.Units.cornerRadius
                    shadow.size: Kirigami.Units.gridUnit
                    shadow.color: Qt.rgba(0, 0, 0, 0.25)
                    shadow.yOffset: 2
                    border.width: 1
                    border.color: Kirigami.ColorUtils.linearInterpolation(Kirigami.Theme.backgroundColor, Kirigami.Theme.textColor, Kirigami.Theme.frameContrast)

                    Item {
                        id: host
                        objectName: "previewHost"
                        anchors.fill: parent
                        clip: true
                    }

                    Component {
                        id: pageHostComponent
                        Kirigami.ApplicationItem {
                            anchors.fill: parent
                            pageStack.globalToolBar.style: Kirigami.ApplicationHeaderStyle.ToolBar
                            pageStack.globalToolBar.showNavigationButtons: Kirigami.ApplicationHeaderStyle.NoNavigationButtons
                        }
                    }

                    // What the preview shows over itself: its dialogs, menus,
                    // drawers and passive notifications. Qt puts those in the
                    // overlay of the window, which is Kreator's: an
                    // application's sidebar would cover Kreator's own, and its
                    // dialogs dim and block all of Kreator. The backend's
                    // PopupConfiner hands them over to this layer instead, so
                    // they stay in the frame (zoomed, scrolled and clipped
                    // like the rest of the preview).
                    Item {
                        id: popupLayer
                        objectName: "previewPopupLayer"
                        anchors.fill: parent
                        z: 500
                        clip: true

                        readonly property Item windowOverlay: QQC2.Overlay.overlay
                        // the popups that dimmed (`dim`) or blocked (`modal`)
                        // what is around them: { popup, item, dim, modal }
                        property var veiled: []
                        // the topmost of those that is open
                        readonly property var veil: {
                            let top = null
                            for (const v of veiled) {
                                // (the item: a replaced preview's are hidden)
                                if (v.popup && v.popup.visible && v.item.visible && (top === null || v.popup.z >= top.popup.z))
                                    top = v
                            }
                            return top
                        }

                        // Stands in for the overlay's: dims the preview, not
                        // the window, and keeps clicks from what is under a
                        // modal popup (which, as in the overlay, may close it).
                        Rectangle {
                            objectName: "previewPopupVeil"
                            anchors.fill: parent
                            z: popupLayer.veil ? popupLayer.veil.popup.z : 0
                            visible: popupLayer.veil !== null
                            color: popupLayer.veil && popupLayer.veil.dim ? Qt.rgba(0, 0, 0, 0.35) : "transparent"

                            MouseArea {
                                anchors.fill: parent
                                enabled: popupLayer.veil !== null && popupLayer.veil.modal
                                acceptedButtons: Qt.AllButtons
                                hoverEnabled: enabled
                                onWheel: wheel => wheel.accepted = true
                                onPressed: {
                                    const p = popupLayer.veil.popup
                                    if (p.closePolicy & (QQC2.Popup.CloseOnPressOutside | QQC2.Popup.CloseOnReleaseOutside)) {
                                        if (typeof p.reject === "function")
                                            p.reject()
                                        else
                                            p.close()
                                    }
                                }
                            }
                        }

                        // Qt places drawers by the window's size, at the
                        // position of the item they belong to. For the
                        // drawers at the right and bottom edges, these items
                        // end where the window does, seen from the frame.
                        Item {
                            id: rightEdge
                            x: popupLayer.width - width
                            width: popupLayer.windowOverlay ? popupLayer.windowOverlay.width : 0
                            height: popupLayer.height
                        }
                        Item {
                            id: bottomEdge
                            y: popupLayer.height - height
                            width: popupLayer.width
                            height: popupLayer.windowOverlay ? popupLayer.windowOverlay.height : 0
                        }

                        // something that isn't a popup, like Kirigami's
                        // passive notifications
                        function adoptItem(item) {
                            item.parent = popupLayer
                        }

                        function adoptPopup(item, popup) {
                            const drawer = popup instanceof T.Drawer
                            const home = !drawer ? popupLayer
                                       : popup.edge === Qt.RightEdge ? rightEdge
                                       : popup.edge === Qt.BottomEdge ? bottomEdge : popupLayer
                            // what is laid out in the window's overlay is
                            // laid out in the frame
                            const centered = popup.anchors.centerIn === windowOverlay
                            if (popup.parent === windowOverlay || centered || home !== popupLayer)
                                popup.parent = home
                            if (centered)
                                popup.anchors.centerIn = home
                            // The overlay dims the whole window, and blocks it
                            // for modal popups: the veil does both instead. (Not
                            // for drawers, which applications lay themselves
                            // out by: a modal one stays modal.)
                            const dim = popup.dim, modal = popup.modal && !drawer
                            if (dim || modal) {
                                if (modal)
                                    popup.modal = false
                                popup.dim = false
                                veiled = veiled.filter(v => v.popup && v.popup !== popup).concat([{ popup: popup, item: item, dim: dim, modal: modal }])
                            }
                            item.parent = home
                            // Kirigami's drawers at the sides are as high as
                            // what they are in, less their `y` and the window's
                            // footer: Kreator's window's, and `y` reads wrong
                            // outside the overlay. Here: as high as the frame.
                            if (drawer && popup.drawerOpen !== undefined && home !== bottomEdge && popup.edge !== Qt.TopEdge
                                    && popup.parent && Math.abs(popup.height - (popup.parent.height - (popup.modal ? 0 : popup.y))) < 1)
                                popup.height = Qt.binding(() => popup.parent ? popup.parent.height : 0)
                            // Qt placed it for the overlay: have it placed again
                            const margins = popup.margins
                            popup.margins = margins + 1
                            popup.margins = margins
                        }

                        Component.onCompleted: Backend.confinePopups(popupLayer)
                    }

                    Image {
                        id: uiImage
                        anchors.fill: parent
                        visible: pane.isUi
                        source: pane.isUi ? Backend.uiImage : ""
                        cache: false
                        smooth: true
                        fillMode: Image.Stretch
                    }

                    Kirigami.PlaceholderMessage {
                        anchors.centerIn: parent
                        width: parent.width - Kirigami.Units.largeSpacing * 4
                        visible: !pane.isUi && (Backend.previewMode === "nonvisual" || (Backend.previewObject === null && Backend.previewError !== ""))
                        icon.name: Backend.previewMode === "nonvisual" ? "view-hidden" : "data-error"
                        text: Backend.previewMode === "nonvisual" ? qsTr("Nothing to show") : qsTr("The preview could not be created")
                        explanation: Backend.previewMode === "nonvisual" ? qsTr("The root object is not visual. Select objects in the outline to edit them.") : ""
                    }

                    // selection highlight
                    Rectangle {
                        id: highlight
                        z: 1000
                        visible: false
                        opacity: mover.active ? 0 : 1
                        color: Backend.isRootSelected ? "transparent" : Qt.rgba(Kirigami.Theme.highlightColor.r, Kirigami.Theme.highlightColor.g, Kirigami.Theme.highlightColor.b, 0.12)
                        border.color: Kirigami.Theme.highlightColor
                        border.width: Math.max(1, 2 / pane.zoom)
                        radius: 2
                    }

                    // where a moved object goes
                    Rectangle {
                        objectName: "moveGhost"
                        z: 1001
                        visible: mover.active && mover.problem === ""
                        x: mover.x
                        y: mover.y
                        width: mover.w
                        height: mover.h
                        color: Qt.rgba(Kirigami.Theme.highlightColor.r, Kirigami.Theme.highlightColor.g, Kirigami.Theme.highlightColor.b, pane.isUi ? 0.25 : 0.08)
                        border.color: Kirigami.Theme.highlightColor
                        border.width: Math.max(1, 2 / pane.zoom)
                        radius: 2
                    }

                    // Click to select; drag the selected object to move it;
                    // arrow keys move it to the next grid line (Shift: by a pixel).
                    MouseArea {
                        id: canvasMouse
                        objectName: "designCanvas"
                        anchors.fill: parent
                        z: 999
                        enabled: !pane.interact || pane.isUi
                        visible: enabled
                        hoverEnabled: false
                        preventStealing: true
                        cursorShape: mover.active ? (mover.problem === "" ? Qt.ClosedHandCursor : Qt.ForbiddenCursor) : Qt.PointingHandCursor
                        Accessible.role: Accessible.Canvas
                        Accessible.name: qsTr("Design view")
                        Accessible.description: qsTr("Arrow keys move the selected object to the next grid line, Ctrl+arrow keys resize it; with Shift, by one pixel. Alt+click selects the object under the selected one")
                        // the selected object stays selected when pressed where
                        // another covers it, to drag it; a plain click then
                        // selects the one on top. Alt+click: the one below.
                        property bool covered: false
                        onPressed: mouse => {
                            forceActiveFocus()
                            covered = Backend.pressAt(pane.isUi ? null : host, mouse.x, mouse.y, mouse.modifiers & Qt.AltModifier)
                            mover.prepare(mouse.x, mouse.y)
                        }
                        onPositionChanged: mouse => mover.drag(mouse.x, mouse.y, mouse.modifiers & Qt.ShiftModifier)
                        onReleased: mouse => {
                            const dragged = mover.active
                            mover.finish(mouse.modifiers & Qt.ShiftModifier)
                            if (covered && !dragged) {
                                if (pane.isUi)
                                    Backend.pickUi(mouse.x, mouse.y)
                                else
                                    Backend.pickAt(host, mouse.x, mouse.y)
                            }
                            covered = false
                        }
                        onCanceled: mover.cancel()
                        Keys.onEscapePressed: event => {
                            event.accepted = mover.active
                            mover.cancel()
                        }
                        Keys.onPressed: event => pane.nudge(event)
                    }

                    // components dragged from the sidebar's Add tab
                    DropArea {
                        id: dropArea
                        objectName: "designDropArea"
                        anchors.fill: parent
                        z: 998
                        keys: ["kreator/component"]
                        // where the component's top-left corner goes, and into what;
                        // the corner lines up with the container's and its
                        // children's sides and centres (`targets`), else the grid
                        property real dropX: 0
                        property real dropY: 0
                        property var target: ({})
                        property var targets: []
                        property var guides: []
                        property var distances: []
                        // the size it will likely get there (0: unknown, no preview)
                        // its natural size, and the size shown and given (fitted
                        // between neighbours, or the natural one)
                        property real naturalW: 0
                        property real naturalH: 0
                        property real dropW: 0
                        property real dropH: 0
                        property bool fittedW: false
                        property bool fittedH: false
                        property int sizedIndex: -1

                        function track(d) {
                            const free = d.source && d.source.free
                            const index = d.source ? d.source.paletteIndex : -1
                            const rx = Math.max(0, Math.min(frame.width, d.x))
                            const ry = Math.max(0, Math.min(frame.height, d.y))
                            // (the container under the pointer: the aligned point
                            // may lie on a neighbour's edge)
                            const t = Backend.dropTarget(pane.isUi ? null : host, rx, ry)
                            if (t.uid !== target.uid || index !== sizedIndex) {
                                targets = t.free ? Backend.containerRects(pane.isUi ? null : host, t.uid) : []
                                const size = t.free && index >= 0 ? Backend.componentSize(index, t.uid) : [0, 0]
                                naturalW = size[0]
                                naturalH = size[1]
                                sizedIndex = index
                            }
                            target = t
                            // its sides and centre line up, when its size is known
                            const nw = naturalW, nh = naturalH
                            // between two neighbours: stretched to fill the gap, leaving
                            // gaps as wide as one between other objects
                            const fitX = !free && nw > 0 ? pane.fitBetween(rx, ry, nw, nh, targets, true) : null
                            const fitY = !free && nh > 0 ? pane.fitBetween(rx, ry, nw, nh, targets, false) : null
                            // else: as wide (high) as an object nearby, when it nearly is
                            const sameW = !free && !fitX && nw > 0 ? pane.nearestSize(nw, pane.neighbourSizes(rx, ry, nw, nh, targets, true)) : null
                            const sameH = !free && !fitY && nh > 0 ? pane.nearestSize(nh, pane.neighbourSizes(rx, ry, nw, nh, targets, false)) : null
                            // (given on dropping only when it isn't its own size anyway)
                            fittedW = fitX !== null || (sameW !== null && Math.abs(sameW - nw) >= 0.5)
                            fittedH = fitY !== null || (sameH !== null && Math.abs(sameH - nh) >= 0.5)
                            dropW = fitX ? fitX.size : sameW !== null ? sameW : nw
                            dropH = fitY ? fitY.size : sameH !== null ? sameH : nh
                            const stopsX = dropW > 0 ? pane.spacingStops(rx, ry, dropW, dropH, targets, true) : []
                            const stopsY = dropH > 0 ? pane.spacingStops(rx, ry, dropW, dropH, targets, false) : []
                            dropX = fitX ? fitX.pos : pane.align(rx, dropW > 0 ? [0, dropW / 2, dropW] : [0], true, free, targets, stopsX)
                            dropY = fitY ? fitY.pos : pane.align(ry, dropH > 0 ? [0, dropH / 2, dropH] : [0], false, free, targets, stopsY)
                            guides = free ? [] : pane.guidesFor(dropX, dropY, dropW, dropH, targets)
                            distances = t.free === true && dropW > 0
                                ? pane.distancesFor(dropX, dropY, dropW, dropH, targets)
                                      .concat(free ? [] : pane.equalSizes(dropX, dropY, dropW, dropH, targets, true, true, false))
                                : []
                            source = d.source || null
                            if (source && source.previewed !== undefined)
                                source.previewed = t.free === true && dropW > 0
                        }
                        // the dragged component (its name, and hiding its chip)
                        property var source: null
                        function clear() {
                            if (source && source.previewed !== undefined)
                                source.previewed = false
                            source = null
                            target = ({})
                            targets = []
                            guides = []
                            distances = []
                            naturalW = 0
                            naturalH = 0
                            dropW = 0
                            dropH = 0
                            fittedW = false
                            fittedH = false
                            sizedIndex = -1
                        }
                        onEntered: drag => track(drag)
                        onPositionChanged: drag => track(drag)
                        onExited: clear()
                        onDropped: drop => {
                            track(drop)
                            const free = drop.source && drop.source.free
                            const index = drop.source ? drop.source.paletteIndex : -1
                            const container = target.uid || 0
                            const fitW = fittedW ? dropW : 0, fitH = fittedH ? dropH : 0
                            clear()
                            if (index < 0)
                                return
                            drop.accept()
                            Backend.insertComponentSized(pane.isUi ? null : host, index, container, dropX, dropY,
                                                         fitW, fitH, pane.placeStep(free), pane.placeUnit(free))
                        }
                    }
                }

                // the grid, drawn at screen resolution over the preview (lines
                // closer than a few pixels on screen are thinned out)
                Item {
                    id: gridOverlay
                    objectName: "designGrid"
                    anchors.fill: parent
                    z: 1
                    visible: gridSettings.showGrid || (gridSettings.snap && (mover.active || dropArea.containsDrag))
                    clip: true
                    readonly property real spacing: pane.gridStep * pane.zoom
                    readonly property int every: Math.max(1, Math.ceil(Kirigami.Units.smallSpacing * 1.5 / Math.max(0.01, spacing)))
                    readonly property real lineSpacing: spacing * every
                    readonly property color lineColor: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.14)

                    Repeater {
                        model: gridOverlay.visible ? Math.floor(gridOverlay.width / gridOverlay.lineSpacing) : 0
                        Rectangle {
                            required property int index
                            x: Math.round((index + 1) * gridOverlay.lineSpacing)
                            width: 1
                            height: gridOverlay.height
                            color: gridOverlay.lineColor
                        }
                    }
                    Repeater {
                        model: gridOverlay.visible ? Math.floor(gridOverlay.height / gridOverlay.lineSpacing) : 0
                        Rectangle {
                            required property int index
                            y: Math.round((index + 1) * gridOverlay.lineSpacing)
                            height: 1
                            width: gridOverlay.width
                            color: gridOverlay.lineColor
                        }
                    }
                }

                // a component being dropped: the object it is added to, and
                // where it goes
                Rectangle {
                    readonly property var r: dropArea.target.rect || []
                    z: 2
                    visible: dropArea.containsDrag && r.length === 4
                    x: r.length === 4 ? r[0] * pane.zoom : 0
                    y: r.length === 4 ? r[1] * pane.zoom : 0
                    width: r.length === 4 ? r[2] * pane.zoom : 0
                    height: r.length === 4 ? r[3] * pane.zoom : 0
                    color: "transparent"
                    border.color: Kirigami.Theme.focusColor
                    border.width: 2
                    radius: Kirigami.Units.cornerRadius
                }
                // the component's likely size where it will go
                Rectangle {
                    objectName: "dropGhost"
                    z: 3
                    visible: dropArea.containsDrag && dropArea.target.free === true && dropArea.dropW > 0
                    x: Math.round(dropArea.dropX * pane.zoom)
                    y: Math.round(dropArea.dropY * pane.zoom)
                    width: Math.max(1, Math.round(dropArea.dropW * pane.zoom))
                    height: Math.max(1, Math.round(dropArea.dropH * pane.zoom))
                    color: Qt.rgba(Kirigami.Theme.highlightColor.r, Kirigami.Theme.highlightColor.g, Kirigami.Theme.highlightColor.b, 0.15)
                    border.color: Kirigami.Theme.highlightColor
                    border.width: 1
                    radius: 2
                }
                Rectangle {
                    objectName: "dropMarker"
                    z: 3
                    visible: dropArea.containsDrag && dropArea.target.free === true
                    x: dropArea.dropX * pane.zoom - width / 2
                    y: dropArea.dropY * pane.zoom - height / 2
                    width: Kirigami.Units.smallSpacing * 2
                    height: width
                    radius: width / 2
                    color: Kirigami.Theme.highlightColor
                    border.color: Kirigami.Theme.highlightedTextColor
                }
                Rectangle {
                    z: 4
                    visible: dropArea.containsDrag && dropArea.target.label !== undefined
                    readonly property bool belowGhost: dropArea.target.free === true && dropArea.dropW > 0
                    // filling a gap in a column: beside the preview, so the gap
                    // below it (and its measurement) stays visible
                    readonly property bool besideGhost: belowGhost && dropArea.fittedH
                    x: Math.min(scaler.width - width,
                                besideGhost ? (dropArea.dropX + dropArea.dropW) * pane.zoom + Kirigami.Units.smallSpacing
                                            : dropArea.dropX * pane.zoom + (belowGhost ? 0 : Kirigami.Units.largeSpacing))
                    y: Math.min(scaler.height - height,
                                besideGhost ? (dropArea.dropY + dropArea.dropH / 2) * pane.zoom - height / 2
                                            : (dropArea.dropY + (belowGhost ? dropArea.dropH : 0)) * pane.zoom + (belowGhost ? Kirigami.Units.smallSpacing : Kirigami.Units.largeSpacing))
                    width: dropLabel.implicitWidth + Kirigami.Units.largeSpacing * 2
                    height: dropLabel.implicitHeight + Kirigami.Units.smallSpacing * 2
                    radius: Kirigami.Units.cornerRadius
                    color: Kirigami.Theme.highlightColor
                    QQC2.Label {
                        id: dropLabel
                        anchors.centerIn: parent
                        color: Kirigami.Theme.highlightedTextColor
                        text: dropArea.target.free
                              ? (dropArea.dropW > 0
                                 ? qsTr("Add %1 to %2 (%3 × %4)").arg(dropArea.source ? dropArea.source.name : "").arg(dropArea.target.label).arg(Math.round(dropArea.dropW)).arg(Math.round(dropArea.dropH))
                                 : qsTr("Add to %1").arg(dropArea.target.label))
                              : qsTr("Add to %1 (its layout places it)").arg(dropArea.target.label)
                    }
                }

                // alignment guides while moving or resizing
                Repeater {
                    model: mover.active ? mover.guides : (dropArea.containsDrag ? dropArea.guides : pane.nudgeGuides)
                    Rectangle {
                        required property var modelData
                        objectName: "alignGuide"
                        z: 2
                        color: Kirigami.Theme.neutralTextColor
                        x: modelData.vertical ? Math.round(modelData.at * pane.zoom) : modelData.from * pane.zoom
                        y: modelData.vertical ? modelData.from * pane.zoom : Math.round(modelData.at * pane.zoom)
                        width: modelData.vertical ? 1 : (modelData.to - modelData.from) * pane.zoom
                        height: modelData.vertical ? (modelData.to - modelData.from) * pane.zoom : 1
                    }
                }

                // distances to the objects nearby while moving, resizing or dropping
                Repeater {
                    model: mover.active ? mover.distances : (dropArea.containsDrag ? dropArea.distances : pane.nudgeDistances)
                    Item {
                        id: measure
                        required property var modelData
                        objectName: "distance"
                        readonly property bool horizontal: modelData.horizontal
                        readonly property real x1: Math.round(modelData.x1 * pane.zoom)
                        readonly property real y1: Math.round(modelData.y1 * pane.zoom)
                        readonly property real x2: Math.round(modelData.x2 * pane.zoom)
                        readonly property real y2: Math.round(modelData.y2 * pane.zoom)
                        // ("=": as wide as another gap between neighbours)
                        readonly property string text: (modelData.equal ? "= " : "") + (modelData.unit !== ""
                            ? qsTr("%1 · %2").arg(Math.round(modelData.value)).arg(modelData.unit)
                            : String(Math.round(modelData.value)))
                        readonly property color color: Kirigami.Theme.neutralTextColor
                        readonly property real cap: Kirigami.Units.smallSpacing * 1.5
                        z: 2
                        // the line
                        Rectangle {
                            x: measure.horizontal ? measure.x1 : measure.x1
                            y: measure.horizontal ? measure.y1 : measure.y1
                            width: measure.horizontal ? measure.x2 - measure.x1 : 1
                            height: measure.horizontal ? 1 : measure.y2 - measure.y1
                            color: measure.color
                        }
                        // its ends
                        Repeater {
                            model: 2
                            Rectangle {
                                required property int index
                                x: measure.horizontal ? (index === 0 ? measure.x1 : measure.x2 - 1) : measure.x1 - measure.cap / 2
                                y: measure.horizontal ? measure.y1 - measure.cap / 2 : (index === 0 ? measure.y1 : measure.y2 - 1)
                                width: measure.horizontal ? 1 : measure.cap
                                height: measure.horizontal ? measure.cap : 1
                                color: measure.color
                            }
                        }
                        // The value, on the line. When the gap is too narrow: for a
                        // gap between neighbours, above their row (left of their
                        // column), so labels of gaps side by side don't collide;
                        // to the parent's edge, past its far end (not over the
                        // object moved).
                        Rectangle {
                            readonly property real length: measure.horizontal ? measure.x2 - measure.x1 : measure.y2 - measure.y1
                            readonly property bool fits: length > (measure.horizontal ? width : height) + 4
                            readonly property string side: measure.modelData.side
                            readonly property bool between: measure.modelData.a1 !== undefined
                            readonly property real outside: between ? Math.round(measure.modelData.a1 * pane.zoom) - gap : 0
                            readonly property real gap: 2
                            x: measure.horizontal
                               ? (fits || between ? (measure.x1 + measure.x2 - width) / 2
                                                  : side === "l" ? measure.x1 - width - gap : measure.x2 + gap)
                               : (fits || !between ? measure.x1 - width / 2 : outside - width)
                            y: measure.horizontal
                               ? (fits || !between ? measure.y1 - height / 2 : outside - height)
                               : (fits || between ? (measure.y1 + measure.y2 - height) / 2
                                                  : side === "t" ? measure.y1 - height - gap : measure.y2 + gap)
                            width: distanceLabel.implicitWidth + Kirigami.Units.smallSpacing * 2
                            height: distanceLabel.implicitHeight
                            radius: 2
                            color: measure.color
                            QQC2.Label {
                                id: distanceLabel
                                anchors.centerIn: parent
                                text: measure.text
                                color: Kirigami.Theme.highlightedTextColor
                                font: Kirigami.Theme.smallFont
                            }
                        }
                    }
                }

                // The selection's name tag and resize handles, at screen size:
                // the tag sits above the frame's border, outside the object.
                Item {
                    id: selectionOverlay
                    objectName: "selectionOverlay"
                    z: 3
                    readonly property bool tracking: mover.active && mover.problem === ""
                    // (not while a component is dropped: the measurements need the room)
                    visible: (highlight.visible || tracking) && !dropArea.containsDrag
                    x: (tracking ? mover.x : highlight.x) * pane.zoom
                    y: (tracking ? mover.y : highlight.y) * pane.zoom
                    width: (tracking ? mover.w : highlight.width) * pane.zoom
                    height: (tracking ? mover.h : highlight.height) * pane.zoom
                    // handles: not while moving, nor in Interact mode
                    readonly property bool handlesShown: !(tracking && mover.edges === null) && (!pane.interact || pane.isUi)

                    Rectangle {
                        objectName: "selectionTag"
                        // (not while dragging: the measurements need the room)
                        visible: !selectionOverlay.tracking
                        // (beside the top-left handle, when there is one)
                        x: selectionOverlay.handlesShown && pane.canMove && pane.canResize ? Kirigami.Units.smallSpacing + 2 : 0
                        y: -height
                        width: tagLabel.implicitWidth + Kirigami.Units.smallSpacing * 2
                        height: tagLabel.implicitHeight + 2
                        color: Kirigami.Theme.highlightColor
                        // (rounded at the top only: it stands on the border)
                        topLeftRadius: 2
                        topRightRadius: 2
                        QQC2.Label {
                            id: tagLabel
                            anchors.centerIn: parent
                            text: Backend.selectedId || Backend.selectedType.split(".").pop()
                            color: Kirigami.Theme.highlightedTextColor
                            font: Kirigami.Theme.smallFont
                        }
                    }

                    Repeater {
                        // the corners and the middles of the sides
                        model: [[0, 0], [0.5, 0], [1, 0], [1, 0.5], [1, 1], [0.5, 1], [0, 1], [0, 0.5]]
                        Rectangle {
                            id: handle
                            required property var modelData
                            readonly property real fx: modelData[0]
                            readonly property real fy: modelData[1]
                            readonly property var edges: ({ l: fx === 0, r: fx === 1, t: fy === 0, b: fy === 1 })
                            readonly property bool middle: fx === 0.5 || fy === 0.5
                            readonly property bool usable: (edges.l || edges.t) ? pane.canResize && pane.canMove : pane.canResize
                            // small objects: corners only
                            readonly property bool roomy: (fx === 0.5 ? selectionOverlay.width : selectionOverlay.height) > Kirigami.Units.gridUnit * 2
                            objectName: "resizeHandle_" + (edges.t ? "t" : edges.b ? "b" : "") + (edges.l ? "l" : edges.r ? "r" : "")
                            visible: selectionOverlay.handlesShown && usable && (!middle || roomy)
                            width: Kirigami.Units.smallSpacing * 2
                            height: width
                            x: Math.round(fx * selectionOverlay.width - width / 2)
                            y: Math.round(fy * selectionOverlay.height - height / 2)
                            radius: 1
                            color: Kirigami.Theme.backgroundColor
                            border.color: Kirigami.Theme.highlightColor
                            border.width: 1

                            MouseArea {
                                // larger than the handle: easier to grab
                                anchors.centerIn: parent
                                width: Kirigami.Units.gridUnit
                                height: width
                                preventStealing: true
                                cursorShape: handle.fx === 0.5 ? Qt.SizeVerCursor
                                           : handle.fy === 0.5 ? Qt.SizeHorCursor
                                           : (handle.edges.l === handle.edges.t) ? Qt.SizeFDiagCursor : Qt.SizeBDiagCursor
                                Accessible.role: Accessible.Grip
                                Accessible.name: qsTr("Resize")
                                function framePoint(mouse) {
                                    return frame.mapFromItem(this, mouse.x, mouse.y)
                                }
                                onPressed: mouse => {
                                    canvasMouse.forceActiveFocus()
                                    const p = framePoint(mouse)
                                    mover.prepare(p.x, p.y, handle.edges)
                                }
                                onPositionChanged: mouse => {
                                    const p = framePoint(mouse)
                                    mover.drag(p.x, p.y, mouse.modifiers & Qt.ShiftModifier)
                                }
                                onReleased: mouse => mover.finish(mouse.modifiers & Qt.ShiftModifier)
                                onCanceled: mover.cancel()
                            }
                        }
                    }
                }

                // why the object being dragged can't be moved
                Rectangle {
                    objectName: "moveProblem"
                    z: 4
                    visible: mover.active && mover.problem !== ""
                    x: Math.min(scaler.width - width, mover.pointerX * pane.zoom + Kirigami.Units.largeSpacing)
                    y: Math.min(scaler.height - height, mover.pointerY * pane.zoom + Kirigami.Units.largeSpacing)
                    width: problemLabel.implicitWidth + Kirigami.Units.largeSpacing * 2
                    height: problemLabel.implicitHeight + Kirigami.Units.smallSpacing * 2
                    radius: Kirigami.Units.cornerRadius
                    color: Kirigami.Theme.negativeBackgroundColor
                    border.color: Kirigami.Theme.negativeTextColor
                    QQC2.Label {
                        id: problemLabel
                        anchors.centerIn: parent
                        color: Kirigami.Theme.negativeTextColor
                        text: mover.edges ? qsTr("Can't resize this: %1").arg(mover.problem) : qsTr("Can't move this: %1").arg(mover.problem)
                    }
                }
            }
        }

        Timer {
            id: highlightTimer
            interval: 150
            repeat: true
            running: pane.visible && Backend.hasDocument
            triggeredOnStart: true
            onTriggered: pane.updateHighlight()
        }
    }

    // the selected object's rectangle in the design view, or null
    function selectedRect() {
        if (isUi) {
            const r = Backend.uiRect(Backend.selectedUid)
            return r.length === 4 ? { x: r[0], y: r[1], w: r[2], h: r[3] } : null
        }
        const item = Backend.previewItemFor(Backend.selectedUid)[0]
        if (!item || !item.visible || item.width <= 0 || item.height <= 0)
            return null
        const p = item.mapToItem(frame, 0, 0)
        return { x: p.x, y: p.y, w: item.width, h: item.height }
    }

    function updateHighlight() {
        const r = selectedRect()
        highlight.visible = r !== null
        if (r) {
            highlight.x = r.x; highlight.y = r.y; highlight.width = r.w; highlight.height = r.h
        }
    }

    // ------------------------------------------------------------ alignment
    // Objects being moved, resized or dropped line up with the objects next
    // to them (`targets`: [x, y, w, h] in design-view coordinates).

    // the lines (left, centre, right; or top, middle, bottom) of the targets
    function guideLines(targets, vertical) {
        const out = []
        for (const r of targets) {
            const a = vertical ? r[0] : r[1], len = vertical ? r[2] : r[3]
            out.push(a, a + len / 2, a + len)
        }
        return out
    }
    // a position whose moving lines (offsets from it) land on a target line
    // within reach (a few pixels on screen), else on the grid
    // (`stops`: more positions to snap to, e.g. equal spacing)
    function align(raw, offsets, vertical, free, targets, stops) {
        if (free || !targets || targets.length === 0)
            return snapped(raw, free)
        const reach = Kirigami.Units.smallSpacing * 1.5 / zoom
        let best = null
        for (const p of stops || []) {
            const d = p - raw
            if (Math.abs(d) <= reach && (best === null || Math.abs(d) < Math.abs(best)))
                best = d
        }
        for (const t of guideLines(targets, vertical)) {
            for (const o of offsets) {
                const d = t - (raw + o)
                if (Math.abs(d) <= reach && (best === null || Math.abs(d) < Math.abs(best)))
                    best = d
            }
        }
        return best === null ? snapped(raw, free) : raw + best
    }
    // the guides for the lines of (x, y, w, h) that meet a target's:
    // { vertical, at, from, to }
    function guidesFor(x, y, w, h, targets) {
        const mx = [x, x + w / 2, x + w], my = [y, y + h / 2, y + h]
        const seen = {}
        function add(key, guide) {
            const g = seen[key]
            seen[key] = g ? { vertical: g.vertical, at: g.at, from: Math.min(g.from, guide.from), to: Math.max(g.to, guide.to) } : guide
        }
        for (const r of targets || []) {
            for (const t of [r[0], r[0] + r[2] / 2, r[0] + r[2]]) {
                if (mx.some(v => Math.abs(v - t) < 0.5))
                    add("v" + Math.round(t), { vertical: true, at: t, from: Math.min(y, r[1]), to: Math.max(y + h, r[1] + r[3]) })
            }
            for (const t of [r[1], r[1] + r[3] / 2, r[1] + r[3]]) {
                if (my.some(v => Math.abs(v - t) < 0.5))
                    add("h" + Math.round(t), { vertical: false, at: t, from: Math.min(x, r[0]), to: Math.max(x + w, r[0] + r[2]) })
            }
        }
        const out = []
        for (const k in seen)
            out.push(seen[k])
        return out
    }

    // Whether r encloses (x, y, w, h): its parent, not a neighbour.
    function encloses(r, x, y, w, h) {
        return r[0] <= x + 0.5 && r[1] <= y + 0.5 && r[0] + r[2] >= x + w - 0.5 && r[1] + r[3] >= y + h - 0.5
    }
    // The gaps between neighbouring targets, side by side in a row
    // (horizontal) or a column: { horizontal, x1, y1, x2, y2, value }.
    function neighbourGaps(targets) {
        const out = []
        const rs = (targets || []).filter(r => !(targets || []).some(o => o !== r && encloses(r, o[0], o[1], o[2], o[3])))
        for (let i = 0; i < rs.length; ++i) {
            for (let j = 0; j < rs.length; ++j) {
                const a = rs[i], b = rs[j]
                if (i === j)
                    continue
                // a before b in a row: overlapping vertically, nothing between
                const top = Math.max(a[1], b[1]), bottom = Math.min(a[1] + a[3], b[1] + b[3])
                const ar = a[0] + a[2]
                if (bottom - top > 0 && b[0] - ar >= 0.5
                        && !rs.some(c => c !== a && c !== b && c[0] >= ar - 0.5 && c[0] + c[2] <= b[0] + 0.5
                                         && Math.min(c[1] + c[3], bottom) - Math.max(c[1], top) > 0))
                    out.push({ horizontal: true, x1: ar, y1: (top + bottom) / 2, x2: b[0], y2: (top + bottom) / 2, value: b[0] - ar, a1: top, a2: bottom })
                // a above b in a column
                const left = Math.max(a[0], b[0]), right = Math.min(a[0] + a[2], b[0] + b[2])
                const ab = a[1] + a[3]
                if (right - left > 0 && b[1] - ab >= 0.5
                        && !rs.some(c => c !== a && c !== b && c[1] >= ab - 0.5 && c[1] + c[3] <= b[1] + 0.5
                                         && Math.min(c[0] + c[2], right) - Math.max(c[0], left) > 0))
                    out.push({ horizontal: false, x1: (left + right) / 2, y1: ab, x2: (left + right) / 2, y2: b[1], value: b[1] - ab, a1: left, a2: right })
            }
        }
        return out
    }
    // Positions for (x, y, w, h)'s left side (top side, `vertical` false)
    // that give it the same gap to its nearest neighbour as two others have,
    // or put it midway between its neighbours on both sides.
    // The nearest neighbours of (x, y, w, h) in its row (`vertical`: by x) or
    // column: { before: where the one before it ends, after: where the one
    // after it starts } (null: none).
    function rowNeighbours(x, y, w, h, targets, vertical) {
        const lo = vertical ? 0 : 1, len = vertical ? 2 : 3, plo = vertical ? 1 : 0, plen = vertical ? 3 : 2
        const pos = vertical ? x : y, size = vertical ? w : h
        const across = vertical ? [y, y + h] : [x, x + w]
        let before = null, after = null
        for (const r of targets || []) {
            if (encloses(r, x, y, w, h))
                continue
            if (Math.min(r[plo] + r[plen], across[1]) - Math.max(r[plo], across[0]) <= 0)
                continue
            const end = r[lo] + r[len]
            if (end <= pos + size / 2 && (before === null || end > before))
                before = end
            if (r[lo] >= pos + size / 2 && (after === null || r[lo] < after))
                after = r[lo]
        }
        return { before: before, after: after }
    }
    // Positions for a side being dragged by a resize handle (`far`: the
    // right / bottom side) that give it the same gap to the next neighbour as
    // two others have, or as the object's other side has.
    function edgeStops(x, y, w, h, targets, vertical, far) {
        const n = rowNeighbours(x, y, w, h, targets, vertical)
        const gaps = neighbourGaps(targets).filter(g => g.horizontal === vertical).map(g => g.value)
        const start = vertical ? x : y, end = vertical ? x + w : y + h
        const out = []
        if (far && n.after !== null) {
            if (n.before !== null)
                gaps.push(start - n.before)
            for (const g of gaps)
                out.push(n.after - g)
        } else if (!far && n.before !== null) {
            if (n.after !== null)
                gaps.push(n.after - end)
            for (const g of gaps)
                out.push(n.before + g)
        }
        return out
    }
    // For a component being dropped (x, y, w, h: at its natural size) into a
    // gap between two neighbours close by in its row (`vertical`: by x) or
    // column: { pos, size } that fill the gap leaving, on both sides, a gap as
    // wide as one between other objects (the one keeping it closest to its
    // natural size); null if none.
    function fitBetween(x, y, w, h, targets, vertical) {
        const n = rowNeighbours(x, y, w, h, targets, vertical)
        if (n.before === null || n.after === null)
            return null
        const near = Kirigami.Units.gridUnit * 6 / zoom
        const start = vertical ? x : y, size = vertical ? w : h
        if (start - n.before > near || n.after - (start + size) > near)
            return null
        let best = null
        for (const g of neighbourGaps(targets).filter(g => g.horizontal === vertical)) {
            const s = n.after - n.before - 2 * g.value
            if (s >= Kirigami.Units.gridUnit && (best === null || Math.abs(s - size) < Math.abs(best.size - size)))
                best = { pos: n.before + g.value, size: s }
        }
        return best
    }
    function spacingStops(x, y, w, h, targets, vertical) {
        const gaps = neighbourGaps(targets).filter(g => g.horizontal === vertical).map(g => g.value)
        const n = rowNeighbours(x, y, w, h, targets, vertical)
        const before = n.before, after = n.after
        const size = vertical ? w : h
        const out = []
        for (const g of gaps) {
            if (before !== null)
                out.push(before + g)
            if (after !== null)
                out.push(after - g - size)
        }
        if (before !== null && after !== null)
            out.push((before + after - size) / 2)
        return out
    }

    // The widths (`vertical`: sizes along x) or heights of the objects
    // around (x, y, w, h) that aren't its parent.
    function neighbourSizes(x, y, w, h, targets, vertical) {
        const out = []
        for (const r of targets || []) {
            if (!encloses(r, x, y, w, h))
                out.push(vertical ? r[2] : r[3])
        }
        return out
    }
    // The size among `sizes` nearest to `size`, within reach; null if none.
    function nearestSize(size, sizes) {
        const reach = Kirigami.Units.smallSpacing * 1.5 / zoom
        let best = null
        for (const s of sizes) {
            if (Math.abs(s - size) <= reach && (best === null || Math.abs(s - size) < Math.abs(best - size)))
                best = s
        }
        return best
    }
    // Size marks for (x, y, w, h) and the objects as wide (`widths`) or as
    // high (`heights`) as it: a line along the top (widths) or the right side
    // (heights) of each, labelled "= <size>"; shaped like distances. Its own
    // mark is along its bottom (left side), clear of its distances upwards.
    // Only objects near it are marked (as far as distances are measured);
    // `own` false: not its own mark (a drop's label gives its size).
    function equalSizes(x, y, w, h, targets, widths, heights, own) {
        const out = []
        const off = Kirigami.Units.smallSpacing * 2 / zoom
        const near = Kirigami.Units.gridUnit * 6 / zoom
        function nearby(r) {
            const dx = Math.max(0, r[0] - (x + w), x - (r[0] + r[2]))
            const dy = Math.max(0, r[1] - (y + h), y - (r[1] + r[3]))
            return Math.max(dx, dy) <= near
        }
        function mark(rx, ry, rw, rh, horizontal, own) {
            const along = horizontal ? (own ? ry + rh + off : ry - off) : (own ? rx - off : rx + rw + off)
            out.push(horizontal
                     ? { horizontal: true, x1: rx, y1: along, x2: rx + rw, y2: along, value: rw, equal: true, side: "size", unit: "" }
                     : { horizontal: false, x1: along, y1: ry, x2: along, y2: ry + rh, value: rh, equal: true, side: "size", unit: "" })
        }
        for (const [on, horizontal] of [[widths, true], [heights, false]]) {
            if (!on)
                continue
            const size = horizontal ? w : h
            const same = (targets || []).filter(r => !encloses(r, x, y, w, h) && nearby(r)
                                                      && Math.abs((horizontal ? r[2] : r[3]) - size) < 0.5)
            if (same.length === 0)
                continue
            if (own !== false)
                mark(x, y, w, h, horizontal, true)
            for (const r of same)
                mark(r[0], r[1], r[2], r[3], horizontal, false)
        }
        return out
    }

    // Distances from (x, y, w, h) to the nearest object on each side, and to
    // the inner edges of an object around it (its parent), within reach:
    // { horizontal, x1, y1, x2, y2, value, unit }. `unit` names the Kirigami
    // spacing unit the distance equals, if any (the HIG's spacings).
    function distancesFor(x, y, w, h, targets) {
        const reach = Kirigami.Units.gridUnit * 6 / zoom
        const best = {}
        function offer(side, d, line, parent) {
            if (d >= 0.5 && d <= reach && (!best[side] || d < best[side].value))
                best[side] = Object.assign({ value: d, parent: !!parent }, line)
        }
        for (const r of targets || []) {
            const rl = r[0], rt = r[1], rr = r[0] + r[2], rb = r[1] + r[3]
            const around = rl <= x + 0.5 && rt <= y + 0.5 && rr >= x + w - 0.5 && rb >= y + h - 0.5
            if (around) {
                const my = y + h / 2, mx = x + w / 2
                offer("l", x - rl, { horizontal: true, x1: rl, y1: my, x2: x, y2: my }, true)
                offer("r", rr - (x + w), { horizontal: true, x1: x + w, y1: my, x2: rr, y2: my }, true)
                offer("t", y - rt, { horizontal: false, x1: mx, y1: rt, x2: mx, y2: y }, true)
                offer("b", rb - (y + h), { horizontal: false, x1: mx, y1: y + h, x2: mx, y2: rb }, true)
                continue
            }
            // side by side: where they overlap across the gap
            const top = Math.max(y, rt), bottom = Math.min(y + h, rb)
            if (bottom - top > 0) {
                const my = (top + bottom) / 2
                if (rr <= x + 0.5)
                    offer("l", x - rr, { horizontal: true, x1: rr, y1: my, x2: x, y2: my, a1: top, a2: bottom })
                if (rl >= x + w - 0.5)
                    offer("r", rl - (x + w), { horizontal: true, x1: x + w, y1: my, x2: rl, y2: my, a1: top, a2: bottom })
            }
            const left = Math.max(x, rl), right = Math.min(x + w, rr)
            if (right - left > 0) {
                const mx = (left + right) / 2
                if (rb <= y + 0.5)
                    offer("t", y - rb, { horizontal: false, x1: mx, y1: rb, x2: mx, y2: y, a1: left, a2: right })
                if (rt >= y + h - 0.5)
                    offer("b", rt - (y + h), { horizontal: false, x1: mx, y1: y + h, x2: mx, y2: rt, a1: left, a2: right })
            }
        }
        const units = [["smallSpacing", Kirigami.Units.smallSpacing], ["largeSpacing", Kirigami.Units.largeSpacing],
                       ["gridUnit", Kirigami.Units.gridUnit]]
        const out = []
        const gaps = neighbourGaps(targets)
        const shown = {}
        for (const side in best) {
            const m = best[side]
            m.side = side   // l, r, t, b: where the gap is, seen from the object
            // equal spacing: gaps between other neighbours that are as wide
            m.equal = false
            if (!m.parent) {
                for (const g of gaps) {
                    if (g.horizontal !== m.horizontal || Math.abs(g.value - m.value) >= 0.5)
                        continue
                    m.equal = true
                    const key = [g.x1, g.y1, g.x2, g.y2].map(Math.round).join(",")
                    if (!shown[key]) {
                        shown[key] = true
                        out.push(Object.assign({}, g, { side: g.horizontal ? "r" : "b", equal: true, parent: false }))
                    }
                }
            }
            out.push(m)
        }
        // midway between two neighbours: its own gaps are equal
        for (const [p, q] of [["l", "r"], ["t", "b"]]) {
            if (best[p] && best[q] && !best[p].parent && !best[q].parent && Math.abs(best[p].value - best[q].value) < 0.5)
                best[p].equal = best[q].equal = true
        }
        for (const m of out) {
            const u = units.find(u => Math.abs(m.value - u[1]) < 0.5)
            m.unit = u ? u[0] : ""
        }
        return out
    }

    // what the selected object allows (updated when it or the preview changes)
    property bool canMove: false
    property bool canResize: false
    function updateAbilities() {
        const uid = Backend.selectedUid
        canMove = uid > 0 && !Backend.isRootSelected && Backend.placementProblem(uid) === ""
        canResize = uid > 0 && !Backend.isRootSelected && Backend.resizeProblem(uid) === ""
    }
    Connections {
        target: Backend
        function onSelectionChanged() {
            pane.updateAbilities()
        }
        function onContentChanged() {
            pane.updateAbilities()
        }
    }

    // moving the selected object by dragging it, or resizing it by dragging
    // one of its handles (`edges`: which sides move, null when moving)
    QtObject {
        id: mover
        property bool pressed: false
        property bool active: false
        property var edges: null
        property int uid: 0
        property string problem: ""
        property real pressX: 0
        property real pressY: 0
        property real startX: 0
        property real startY: 0
        property real startW: 0
        property real startH: 0
        property real x: 0
        property real y: 0
        property real w: 0
        property real h: 0
        property real pointerX: 0
        property real pointerY: 0
        // the live item, moved along for QML documents
        property Item item: null
        property real itemX: 0
        property real itemY: 0
        // what it aligns with (the parent and its other children, [x, y, w, h])
        // and the guides shown: { vertical, at, from, to }
        property var targets: []
        property var guides: []
        property var distances: []

        function prepare(px, py, sides) {
            const r = pane.selectedRect()
            pressed = r !== null && !Backend.isRootSelected
            active = false
            edges = sides || null
            if (!pressed)
                return
            uid = Backend.selectedUid
            pressX = px; pressY = py
            startX = r.x; startY = r.y; startW = r.w; startH = r.h
            x = r.x; y = r.y; w = r.w; h = r.h
        }
        function drag(px, py, free) {
            if (!pressed)
                return
            pointerX = px; pointerY = py
            if (!active) {
                if (Math.hypot(px - pressX, py - pressY) < Qt.styleHints.startDragDistance / pane.zoom)
                    return
                active = true
                if (!edges)
                    problem = Backend.placementProblem(uid)
                else
                    problem = Backend.resizeProblem(uid) || ((edges.l || edges.t) ? Backend.placementProblem(uid) : "")
                if (problem === "" && !pane.isUi) {
                    item = Backend.previewItemFor(uid)[0] || null
                    if (item) {
                        itemX = item.x; itemY = item.y
                    }
                }
                targets = problem === "" ? Backend.guideRects(pane.isUi ? null : host, uid) : []
            }
            if (problem !== "")
                return
            const dx = px - pressX, dy = py - pressY
            if (!edges) {
                // its sides or centre align with others nearby, else go on the grid
                const rx = startX + dx, ry = startY + dy
                x = pane.align(rx, [0, startW / 2, startW], true, free, targets, pane.spacingStops(rx, ry, startW, startH, targets, true))
                y = pane.align(ry, [0, startH / 2, startH], false, free, targets, pane.spacingStops(rx, ry, startW, startH, targets, false))
            } else {
                // the dragged sides align or go on the grid; at least one step wide
                const least = gridSettings.snap && !free ? pane.gridStep : 1
                let left = startX, right = startX + startW, top = startY, bottom = startY + startH
                // (where the dragged sides would be: for the equal-spacing stops)
                const rl = edges.l ? left + dx : left, rr = edges.r ? right + dx : right
                const rt = edges.t ? top + dy : top, rb = edges.b ? bottom + dy : bottom
                // equal spacing, and the sizes of the other objects (measured
                // from the side that stays)
                function stops(vertical, far) {
                    const sizes = pane.neighbourSizes(rl, rt, rr - rl, rb - rt, targets, vertical)
                    const fixed = vertical ? (far ? left : right) : (far ? top : bottom)
                    return pane.edgeStops(rl, rt, rr - rl, rb - rt, targets, vertical, far)
                               .concat(sizes.map(sz => far ? fixed + sz : fixed - sz))
                }
                if (edges.l) left = Math.min(pane.align(rl, [0], true, free, targets, stops(true, false)), right - least)
                if (edges.r) right = Math.max(pane.align(rr, [0], true, free, targets, stops(true, true)), left + least)
                if (edges.t) top = Math.min(pane.align(rt, [0], false, free, targets, stops(false, false)), bottom - least)
                if (edges.b) bottom = Math.max(pane.align(rb, [0], false, free, targets, stops(false, true)), top + least)
                x = left; y = top; w = right - left; h = bottom - top
            }
            guides = free ? [] : pane.guidesFor(x, y, w, h, targets)
            distances = pane.distancesFor(x, y, w, h, targets)
            if (edges)  // resizing: the objects as wide (high) as it
                distances = distances.concat(pane.equalSizes(x, y, w, h, targets, edges.l || edges.r, edges.t || edges.b))
            if (item) {
                item.x = itemX + x - startX
                item.y = itemY + y - startY
                if (edges) {
                    item.width = w
                    item.height = h
                }
            }
        }
        function finish(free) {
            const was = active
            pressed = false
            active = false
            guides = []
            distances = []
            targets = []
            if (!was || problem !== "") {
                edges = null
                return
            }
            const moved = Math.abs(x - startX) >= 0.5 || Math.abs(y - startY) >= 0.5
            const sized = Math.abs(w - startW) >= 0.5 || Math.abs(h - startH) >= 0.5
            let done = false
            if (!edges)
                done = moved && Backend.placeAt(pane.isUi ? null : host, uid, x, y, pane.placeStep(free), pane.placeUnit(free))
            else if (moved || sized)
                done = Backend.resizeTo(pane.isUi ? null : host, uid, x, y, w, h, pane.placeStep(free), pane.placeUnit(free), edges.l || edges.t)
            if (!done && item)
                restore()
            item = null
            edges = null
        }
        function cancel() {
            const was = active
            pressed = false
            active = false
            guides = []
            distances = []
            targets = []
            edges = null
            if (was && item)
                restore()
            item = null
        }
        function restore() {
            // (the preview's bindings for x / y were replaced: make it anew)
            Backend.refresh_preview()
        }
    }

    // Arrow keys: the selected object to the next grid line (and, with "Arrow
    // Keys Stop at Guides", to the next place where it lines up with others,
    // whichever comes first); Shift: one pixel. Ctrl: its right or bottom side.

    // the next stop from v in direction d: a grid line, or a target line
    // reached by one of the moving lines (offsets from v)
    function nextStop(v, d, offsets, vertical, targets, useGrid) {
        if (d === 0)
            return v
        // (whole pixels: positions are written so, and each press moves)
        const from = Math.round(v)
        let best = useGrid ? nextLine(v, d) : null
        if (gridSettings.nudgeToGuides) {
            for (const t of guideLines(targets, vertical)) {
                for (const o of offsets) {
                    const p = Math.round(t - o)
                    if ((p - from) * d >= 1 && (best === null || Math.abs(p - from) < Math.abs(best - from)))
                        best = p
                }
            }
        }
        return best === null ? from + d : best
    }

    // guides shown for a moment after a nudge that lined something up
    property var nudgeGuides: []
    property var nudgeDistances: []
    Timer {
        id: nudgeGuidesTimer
        interval: 1000
        onTriggered: {
            pane.nudgeGuides = []
            pane.nudgeDistances = []
        }
    }

    function nudge(event) {
        const dirs = {}
        dirs[Qt.Key_Left] = [-1, 0]; dirs[Qt.Key_Right] = [1, 0]
        dirs[Qt.Key_Up] = [0, -1]; dirs[Qt.Key_Down] = [0, 1]
        const d = dirs[event.key]
        if (!d || mover.active || Backend.isRootSelected)
            return
        const r = selectedRect()
        if (!r)
            return
        event.accepted = true
        const shift = event.modifiers & Qt.ShiftModifier
        const free = shift || !gridSettings.snap
        const uid = Backend.selectedUid
        // (the neighbours: for the distances shown, and the guides' stops)
        const around = Backend.guideRects(isUi ? null : host, uid)
        const targets = !shift && gridSettings.nudgeToGuides ? around : []
        let rect
        if (event.modifiers & Qt.ControlModifier) {
            // Ctrl: the right / bottom side
            const least = free ? 1 : gridStep
            const right = shift ? Math.round(r.x + r.w) + d[0] : nextStop(r.x + r.w, d[0], [0], true, targets, !free)
            const bottom = shift ? Math.round(r.y + r.h) + d[1] : nextStop(r.y + r.h, d[1], [0], false, targets, !free)
            rect = { x: r.x, y: r.y, w: Math.max(least, right - r.x), h: Math.max(least, bottom - r.y) }
            Backend.resizeTo(isUi ? null : host, uid, rect.x, rect.y, rect.w, rect.h, placeStep(free), placeUnit(free), false)
        } else {
            const nx = shift ? Math.round(r.x) + d[0] : nextStop(r.x, d[0], [0, r.w / 2, r.w], true, targets, !free)
            const ny = shift ? Math.round(r.y) + d[1] : nextStop(r.y, d[1], [0, r.h / 2, r.h], false, targets, !free)
            rect = { x: nx, y: ny, w: r.w, h: r.h }
            Backend.placeAt(isUi ? null : host, uid, nx, ny, placeStep(free), placeUnit(free))
        }
        nudgeGuides = targets.length ? guidesFor(rect.x, rect.y, rect.w, rect.h, targets) : []
        nudgeDistances = distancesFor(rect.x, rect.y, rect.w, rect.h, around)
        if (nudgeGuides.length || nudgeDistances.length)
            nudgeGuidesTimer.restart()
    }

    // A popup previewed on its own is open as long as the preview is shown.
    // (The frame's popup layer keeps it, like the popups a document opens,
    // inside the frame.)
    property string attachedMode: ""
    property string dismissedNote: ""

    function syncPopup() {
        if (!attached || attachedMode !== "popup")
            return
        if (pane.visible && Backend.hasDocument)
            attached.open()
        else
            attached.close()
    }

    onVisibleChanged: syncPopup()

    function attach() {
        const o = Backend.previewObject
        if (o === attached)
            return
        if (attached && attachedMode === "popup")
            attached.close()
        if (pageHost) {
            // the page itself is deleted by the backend; take it out of the
            // stack first so the host's toolbar lets go of its actions
            const oldHost = pageHost
            pageHost = null
            oldHost.visible = false
            oldHost.pageStack.clear()
            oldHost.destroy()
        }
        attached = o
        attachedMode = o ? Backend.previewMode : ""
        naturalWidth = 0
        naturalHeight = 0
        if (!o)
            return
        switch (Backend.previewMode) {
        case "page":
            pageHost = pageHostComponent.createObject(frame)
            pageHost.pageStack.push(o)
            break
        case "window":
            naturalWidth = o.implicitWidth
            naturalHeight = o.implicitHeight
            o.parent = host
            o.anchors.fill = host
            break
        case "popup":
            o.parent = host
            o.closePolicy = QQC2.Popup.NoAutoClose
            o.modal = false
            o.dim = false
            if (o.popupType !== undefined)
                o.popupType = QQC2.Popup.Item  // not a separate native window
            syncPopup()
            break
        case "item":
            naturalWidth = o.width > 0 ? o.width : o.implicitWidth
            naturalHeight = o.height > 0 ? o.height : o.implicitHeight
            o.parent = host
            if (naturalWidth <= 0 || naturalHeight <= 0)
                o.anchors.fill = host
            break
        }
    }

    Connections {
        target: Backend
        function onPreviewChanged() {
            pane.attach()
            pane.updateAbilities()
        }
    }
    Component.onCompleted: {
        attach()
        updateAbilities()
    }
}
