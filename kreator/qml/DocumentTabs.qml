import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// One tab per open document, like Kate's tab bar: a dot for unsaved changes,
// a close button (or middle click), Ctrl+Tab to cycle.
RowLayout {
    id: bar
    spacing: 0

    // the sidebar toggle sits at the start of the tab bar
    property bool projectPanelShown: true
    signal toggleProjectPanel()

    QQC2.ToolButton {
        icon.name: bar.projectPanelShown ? "sidebar-collapse-left" : "sidebar-expand-left"
        text: bar.projectPanelShown ? qsTr("Hide Sidebar") : qsTr("Show Sidebar")
        display: QQC2.AbstractButton.IconOnly
        onClicked: bar.toggleProjectPanel()
        QQC2.ToolTip.text: text + " (F9)"
        QQC2.ToolTip.visible: hovered
        QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
    }

    FontMetrics {
        id: tabMetrics
        font.bold: true
    }

    QQC2.TabBar {
        id: tabs
        Layout.fillWidth: true
        // (scrolled tabs must not be drawn outside the bar, over the sidebar)
        clip: true
        // (set from the tabs' `current` flags: the container changes
        // currentIndex itself when tabs are inserted, so a binding would break)
        function currentTabIndex() {
            for (let i = 0; i < tabRepeater.count; ++i) {
                const t = tabRepeater.itemAt(i)
                if (t && t.current)
                    return i
            }
            return -1
        }
        // the tab bar's list would flick sideways and take the drag from the tabs
        Component.onCompleted: {
            if (contentItem && contentItem.interactive !== undefined) {
                contentItem.interactive = false
                // the style keeps the current tab in a highlight range and
                // snaps back after any scrolling; we keep it visible ourselves
                contentItem.highlightRangeMode = ListView.NoHighlightRange
                contentItem.highlightFollowsCurrentItem = false
            }
            Qt.callLater(ensureCurrentVisible)
        }

        // ---- scrolling when the tabs don't fit: wheel, ◀ ▶ buttons, the
        // current tab is kept in view, and the edges scroll while dragging
        readonly property Item list: contentItem
        // scroll range from the tabs' real positions: the list moves its content
        // origin when the documents change, so 0 … contentWidth is not reliable
        function tabsLeft() {
            let x = Infinity
            for (let i = 0; i < tabRepeater.count; ++i) {
                const t = tabRepeater.itemAt(i)
                if (t)
                    x = Math.min(x, t.x)
            }
            return x === Infinity ? 0 : x
        }
        function tabsRight() {
            let x = 0
            for (let i = 0; i < tabRepeater.count; ++i) {
                const t = tabRepeater.itemAt(i)
                if (t)
                    x = Math.max(x, t.x + t.width)
            }
            return x
        }
        readonly property real maxScroll: list ? Math.max(0, list.contentWidth - list.width) : 0
        readonly property bool overflowing: maxScroll > 1
        readonly property bool atStart: !list || list.contentX <= tabsLeft() + 1
        readonly property bool atEnd: !list || list.contentX + list.width >= tabsRight() - 1

        NumberAnimation {
            id: scrollAnimation
            target: tabs.list
            property: "contentX"
            duration: Kirigami.Units.shortDuration
            easing.type: Easing.OutCubic
        }
        function scrollTo(x, animated) {
            const lo = tabsLeft(), hi = Math.max(lo, tabsRight() - list.width)
            const to = Math.max(lo, Math.min(hi, x))
            scrollAnimation.stop()
            if (animated) {
                scrollAnimation.to = to
                scrollAnimation.start()
            } else {
                list.contentX = to
            }
        }
        function scrollBy(dx, animated) {
            scrollTo((scrollAnimation.running ? scrollAnimation.to : list.contentX) + dx, animated)
        }
        function ensureCurrentVisible() {
            if (!list)
                return
            list.forceLayout()  // new tabs may not be placed yet
            const i = currentTabIndex()
            if (i >= 0 && currentIndex !== i)
                currentIndex = i
            const t = tabRepeater.itemAt(i)
            if (!t)
                return
            if (t.x < list.contentX)
                scrollTo(t.x, true)
            else if (t.x + t.width > list.contentX + list.width)
                scrollTo(t.x + t.width - list.width, true)
        }
        onCurrentIndexChanged: ensureTimer.restart()
        Timer {  // after the tabs were laid out again
            id: ensureTimer
            interval: 0
            onTriggered: tabs.ensureCurrentVisible()
        }
        Connections {
            target: Backend
            function onDocumentsChanged() {
                ensureTimer.restart()
            }
        }
        onWidthChanged: Qt.callLater(ensureCurrentVisible)

        // vertical wheels scroll sideways here; touchpads may send x
        function wheelScroll(event) {
            const d = event.pixelDelta.x !== 0 || event.pixelDelta.y !== 0
                ? (event.pixelDelta.x !== 0 ? -event.pixelDelta.x : -event.pixelDelta.y)
                : -(event.angleDelta.y !== 0 ? event.angleDelta.y : event.angleDelta.x) / 120 * Kirigami.Units.gridUnit * 3
            scrollBy(d, false)
            event.accepted = true
        }
        WheelHandler {  // the empty part of the bar
            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
            onWheel: event => tabs.wheelScroll(event)
        }

        // dragging a tab near an edge scrolls the bar
        property real dragSceneX: -1
        Timer {
            interval: 16
            repeat: true
            running: tabs.dragFrom >= 0 && tabs.overflowing
            onTriggered: {
                const x = tabs.list.mapFromItem(null, tabs.dragSceneX, 0).x
                const edge = Kirigami.Units.gridUnit * 2
                let d = 0
                if (x < edge)
                    d = -Math.min(12, (edge - x) / 3 + 2)
                else if (x > tabs.list.width - edge)
                    d = Math.min(12, (x - tabs.list.width + edge) / 3 + 2)
                if (d !== 0) {
                    tabs.scrollBy(d, false)
                    tabs.updateDrop(tabs.dragSceneX)
                }
            }
        }

        // ---- reordering by dragging: the tab follows the pointer, a marker
        // shows where it will go, releasing moves it there
        property int dragFrom: -1
        property int dropAt: -1          // insertion index (0 … count)
        property real dropX: 0

        function updateDrop(sceneX) {
            dragSceneX = sceneX
            const content = list.contentItem   // tabs live in the list's scrolling content
            const x = content.mapFromItem(null, sceneX, 0).x
            let at = tabRepeater.count
            for (let i = 0; i < tabRepeater.count; ++i) {
                const t = tabRepeater.itemAt(i)
                if (t && x < t.x + t.width / 2) {
                    at = i
                    break
                }
            }
            dropAt = at
            const ref = tabRepeater.itemAt(Math.min(at, tabRepeater.count - 1))
            if (ref)
                dropX = content.mapToItem(tabs, at < tabRepeater.count ? ref.x : ref.x + ref.width, 0).x
        }
        function finishDrag() {
            const from = dragFrom, at = dropAt
            dragFrom = -1
            dropAt = -1
            if (from < 0 || at < 0)
                return
            const to = at > from ? at - 1 : at  // index after removing the dragged tab
            if (to !== from)
                Backend.moveTab(from, to)
        }

        Rectangle {  // drop marker
            parent: tabs
            z: 10
            visible: tabs.dragFrom >= 0 && tabs.dropAt >= 0 && tabs.dropAt !== tabs.dragFrom && tabs.dropAt !== tabs.dragFrom + 1
            x: tabs.dropX - width / 2
            y: Kirigami.Units.smallSpacing / 2
            width: 3
            height: tabs.height - Kirigami.Units.smallSpacing
            radius: 1
            color: Kirigami.Theme.highlightColor
        }

        Repeater {
            id: tabRepeater
            model: Backend.documentTabs
            delegate: QQC2.TabButton {
                id: tab
                required property int index
                required property string key
                required property string path
                required property string name
                required property bool modified
                required property bool current

                // sized for the whole file name (the style would measure its own text)
                width: Math.min(Kirigami.Units.gridUnit * 14, Math.max(Kirigami.Units.gridUnit * 5,
                    tabMetrics.advanceWidth(tab.name) + Kirigami.Units.iconSizes.small * 2 + leftPadding + rightPadding + Kirigami.Units.smallSpacing * 5))
                checked: tab.current
                Accessible.name: tab.name + (tab.modified ? " " + qsTr("(modified)") : "")
                QQC2.ToolTip.text: (tab.path || qsTr("Not saved yet")) + (tab.modified ? "\n" + qsTr("Unsaved changes") : "")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay * 2


                // drag to reorder
                readonly property bool dragging: tabs.dragFrom === index
                property real dragOffset: 0
                z: dragging ? 5 : 0
                // while dragged: an opaque, raised tab above the others
                Kirigami.ShadowedRectangle {
                    z: -1
                    anchors.fill: parent
                    visible: tab.dragging
                    color: Kirigami.Theme.backgroundColor
                    radius: Kirigami.Units.cornerRadius / 2
                    border.width: 1
                    border.color: Kirigami.Theme.highlightColor
                    shadow.size: Kirigami.Units.smallSpacing * 2
                    shadow.color: Qt.rgba(0, 0, 0, 0.25)
                }
                transform: Translate { x: tab.dragging ? tab.dragOffset : 0 }
                // Clicks, middle clicks and dragging, handled here: the tab
                // button keeps its mouse grab, which would veto a DragHandler.
                // Presses on the close button go through to it.
                MouseArea {
                    anchors.fill: parent
                    z: 1
                    acceptedButtons: Qt.LeftButton | Qt.MiddleButton
                    preventStealing: true
                    cursorShape: moved ? Qt.ClosedHandCursor : Qt.ArrowCursor
                    property real pressX: 0
                    property bool moved: false
                    property bool wasDrag: false
                    onPressed: mouse => {
                        const p = mapToItem(closeButton, mouse.x, mouse.y)
                        if (mouse.button === Qt.LeftButton && closeButton.visible && closeButton.contains(p)) {
                            mouse.accepted = false
                            return
                        }
                        pressX = mapToItem(null, mouse.x, 0).x
                        moved = false
                        wasDrag = false
                    }
                    onPositionChanged: mouse => {
                        if (!(pressedButtons & Qt.LeftButton))
                            return
                        const sx = mapToItem(null, mouse.x, 0).x
                        if (!moved && Math.abs(sx - pressX) >= Qt.styleHints.startDragDistance) {
                            moved = true
                            tabs.dragFrom = tab.index
                        }
                        if (moved) {
                            tab.dragOffset = sx - pressX
                            tabs.updateDrop(sx)
                        }
                    }
                    onReleased: {
                        wasDrag = moved
                        if (moved) {
                            moved = false
                            tabs.finishDrag()
                            tab.dragOffset = 0
                        }
                    }
                    onWheel: wheel => tabs.wheelScroll(wheel)
                    onCanceled: {
                        moved = false
                        tabs.dragFrom = -1
                        tabs.dropAt = -1
                        tab.dragOffset = 0
                    }
                    onClicked: mouse => {
                        if (wasDrag)
                            return
                        if (mouse.button === Qt.MiddleButton)
                            applicationWindow().closeTab(tab.key)
                        else if (!tab.current)
                            applicationWindow().switchFile(tab.key)
                    }
                }

                contentItem: RowLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon {
                        source: tab.name.endsWith(".ui") ? "window" : "text-x-qml"
                        implicitWidth: Kirigami.Units.iconSizes.small
                        implicitHeight: Kirigami.Units.iconSizes.small
                    }
                    QQC2.Label {
                        Layout.fillWidth: true
                        text: tab.name
                        elide: Text.ElideMiddle
                        font.bold: tab.current
                    }
                    // unsaved changes: a dot that turns into the close button on hover, like Kate
                    Item {
                        implicitWidth: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
                        implicitHeight: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
                        Rectangle {
                            anchors.centerIn: parent
                            visible: tab.modified && !tab.hovered
                            width: Kirigami.Units.smallSpacing * 1.6
                            height: width
                            radius: width / 2
                            color: Kirigami.Theme.neutralTextColor
                        }
                        QQC2.ToolButton {
                            id: closeButton
                            anchors.fill: parent
                            visible: tab.hovered || !tab.modified
                            opacity: tab.hovered || tab.current ? 1 : 0.4
                            padding: 0
                            icon.name: "tab-close"
                            icon.width: Kirigami.Units.iconSizes.small
                            icon.height: Kirigami.Units.iconSizes.small
                            text: qsTr("Close Tab")
                            display: QQC2.AbstractButton.IconOnly
                            flat: true
                            onClicked: applicationWindow().closeTab(tab.key)
                        }
                    }
                }
            }
        }
    }

    // shown when the tabs don't fit
    QQC2.ToolButton {
        visible: tabs.overflowing
        enabled: { tabs.list ? tabs.list.contentX : 0; return !tabs.atStart }
        icon.name: "go-previous"
        text: qsTr("Scroll Tabs Left")
        display: QQC2.AbstractButton.IconOnly
        autoRepeat: true
        onClicked: tabs.scrollBy(-Kirigami.Units.gridUnit * 6, true)
        QQC2.ToolTip.text: text
        QQC2.ToolTip.visible: hovered
        QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
    }
    QQC2.ToolButton {
        visible: tabs.overflowing
        enabled: { tabs.list ? tabs.list.contentX : 0; return !tabs.atEnd }
        icon.name: "go-next"
        text: qsTr("Scroll Tabs Right")
        display: QQC2.AbstractButton.IconOnly
        autoRepeat: true
        onClicked: tabs.scrollBy(Kirigami.Units.gridUnit * 6, true)
        QQC2.ToolTip.text: text
        QQC2.ToolTip.visible: hovered
        QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
    }
    QQC2.ToolButton {
        id: listButton
        visible: tabs.overflowing
        icon.name: "view-list-details"
        text: qsTr("All Documents")
        display: QQC2.AbstractButton.IconOnly
        onClicked: documentMenu.popup(listButton, 0, listButton.height)
        QQC2.ToolTip.text: text
        QQC2.ToolTip.visible: hovered
        QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay

        QQC2.Menu {
            id: documentMenu
            Instantiator {
                model: Backend.openDocuments
                delegate: QQC2.MenuItem {
                    required property var modelData
                    text: (modelData.modified ? "• " : "") + modelData.name
                    icon.name: modelData.name.endsWith(".ui") ? "window" : "text-x-qml"
                    font.bold: modelData.current
                    onTriggered: applicationWindow().switchFile(modelData.key)
                }
                onObjectAdded: (index, object) => documentMenu.insertItem(index, object)
                onObjectRemoved: (index, object) => documentMenu.removeItem(object)
            }
        }
    }
}
