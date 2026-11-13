import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import org.kde.kirigami as Kirigami

// The document's signal flow (see signalflow.py): objects as boxes, arrows for
// what makes what happen (signal handlers, Connections) and, dashed, for
// property bindings. A label shows its code, an object selects it; objects
// can be dragged around. A Qt Designer form's connections can be edited:
// drag from a widget's handle to another, or click a connection's label.
ColumnLayout {
    id: pane
    objectName: "flowPane"
    spacing: 0

    property bool active: false
    readonly property bool isUi: Backend.docKind === "ui"
    property var flow: ({ nodes: [], edges: [], counts: {} })
    // key -> { x, y, w, h, layer } (canvas coordinates)
    property var placed: ({})
    property size canvasSize: Qt.size(0, 0)
    property real zoom: 1
    property string hoverKey: ""

    // show the code of an edge / an object (1-based)
    signal jumpRequested(int line, int column)

    Settings {
        id: settings
        category: "signalFlow"
        property bool showSignals: true
        property bool showBindings: true
        property bool showLayout: false
        property bool selectedOnly: false
        property bool showUnconnected: true   // a form's widgets without connections
    }

    function kinds() {
        const k = []
        if (settings.showSignals)
            k.push("signal")
        if (settings.showBindings && !isUi)
            k.push("binding")
        if (settings.showLayout && !isUi)
            k.push("layout")
        return k
    }
    // a document with more edges than this shows the selected object's
    // (a graph that big is not readable, and slow to draw), unless asked
    readonly property int bigGraph: 150
    property bool tooBig: false
    property bool showAllAnyway: false
    readonly property bool focused: settings.selectedOnly || (tooBig && !showAllAnyway)
    function reload() {
        if (!active || !Backend.hasDocument)
            return
        if (shownKey !== Backend.currentKey)
            showAllAnyway = false
        if (!settings.selectedOnly && !showAllAnyway) {
            const all = Backend.signalFlow(kinds(), 0, showAll)
            tooBig = all.edges.length > bigGraph
            flow = tooBig ? Backend.signalFlow(kinds(), Backend.selectedUid || -1, false) : all
        } else {
            flow = Backend.signalFlow(kinds(), settings.selectedOnly ? Backend.selectedUid : 0, showAll)
        }
        relayout()
        // another document: start with all of it in view
        if (shownKey !== Backend.currentKey) {
            shownKey = Backend.currentKey
            Qt.callLater(fit)
        }
    }
    property string shownKey: ""
    readonly property bool showAll: isUi && settings.showUnconnected

    // objects moved by hand in the shown document: { stable key: [x, y] }
    // (Backend keeps them per document, in the session too)
    property var moves: ({})
    property int movedCount: 0
    function stableKey(n) {
        return n.stable || n.key
    }
    function moveNode(key, x, y) {
        const p = Object.assign({}, placed)
        const r = p[key]
        if (!r)
            return
        p[key] = Object.assign({}, r, { x: Math.max(0, x), y: Math.max(0, y), moved: true })
        placed = p
        const n = flow.nodes.find(m => m.key === key)
        moves[stableKey(n)] = [p[key].x, p[key].y]
        movedCount = Object.keys(moves).length
        growCanvas()
    }
    // a drag ended: keep the places
    function storeMoves() {
        Backend.setFlowPositions(moves)
    }
    function resetLayout() {
        moves = {}
        movedCount = 0
        Backend.setFlowPositions({})
        relayout()
    }
    function growCanvas() {
        let w = canvasSize.width, h = canvasSize.height
        for (const k in placed) {
            w = Math.max(w, placed[k].x + placed[k].w + margin)
            h = Math.max(h, placed[k].y + placed[k].h + margin)
        }
        if (w !== canvasSize.width || h !== canvasSize.height)
            canvasSize = Qt.size(w, h)
    }
    property bool reloadQueued: false
    function queueReload() {
        if (reloadQueued)
            return
        reloadQueued = true
        Qt.callLater(() => { reloadQueued = false; reload() })
    }

    onActiveChanged: if (active) reload()
    Connections {
        target: Backend
        function onContentChanged() { pane.queueReload() }
        function onDocumentChanged() { pane.queueReload() }
        function onSelectionChanged() {
            if (pane.focused)
                pane.queueReload()
        }
    }

    // ------------------------------------------------------------ geometry
    // A node: its title bar (the name, dragged to move it), its type, and a
    // row per port: the signals, functions and properties that take part.
    // An input port has its connector on the left, an output on the right.
    TextMetrics { id: boldMetrics; font.bold: true }
    TextMetrics { id: plainMetrics; font: Kirigami.Theme.smallFont }
    TextMetrics { id: portMetrics; font: Kirigami.Theme.smallFont }
    readonly property real titleHeight: Kirigami.Units.gridUnit * 1.4
    readonly property real typeHeight: Kirigami.Units.gridUnit * 1.1
    readonly property real portHeight: Kirigami.Units.gridUnit * 1.25
    readonly property real connectorSize: Math.round(Kirigami.Units.gridUnit * 0.6)
    readonly property real rowGap: Kirigami.Units.gridUnit * 1.2
    readonly property real columnGap: Kirigami.Units.gridUnit * 6
    readonly property real margin: Kirigami.Units.gridUnit * 2

    function textWidth(metrics, text) {
        metrics.text = text
        return metrics.advanceWidth
    }
    function nodeTitle(n) {
        return n.label || n.type
    }
    function nodeSubtitle(n) {
        if (n.external)
            return qsTr("outside this file")
        return n.label ? n.type : qsTr("no id")
    }
    function nodeHeight(n) {
        return n.dummy ? Kirigami.Units.gridUnit : titleHeight + typeHeight + (n.ports || []).length * portHeight
                                                   + Kirigami.Units.smallSpacing
    }
    function nodeWidth(n) {
        if (n.dummy)
            return Kirigami.Units.gridUnit
        let w = Math.max(textWidth(boldMetrics, nodeTitle(n)), textWidth(plainMetrics, nodeSubtitle(n)))
        for (const p of n.ports || [])
            w = Math.max(w, textWidth(portMetrics, p.name) + Kirigami.Units.gridUnit)
        return Math.max(Kirigami.Units.gridUnit * 6, Math.min(Kirigami.Units.gridUnit * 16, w + Kirigami.Units.largeSpacing * 3))
    }

    function relayout() {
        const layers = []
        for (const n of flow.nodes) {
            (layers[n.layer] = layers[n.layer] || []).push(n)
        }
        const layerW = [], layerH = []
        for (let l = 0; l < layers.length; ++l) {
            const col = (layers[l] || []).sort((a, b) => a.order - b.order)
            layers[l] = col
            layerW[l] = Math.max(0, ...col.map(n => nodeWidth(n)))
            layerH[l] = col.reduce((h, n) => h + nodeHeight(n), 0) + Math.max(0, col.length - 1) * rowGap
        }
        const fullH = Math.max(Kirigami.Units.gridUnit, ...layerH)
        const p = {}
        let cx = margin
        for (let l = 0; l < layers.length; ++l) {
            let y = margin + (fullH - layerH[l]) / 2
            for (const n of layers[l]) {
                const w = nodeWidth(n), h = nodeHeight(n)
                const ports = {}
                ;(n.ports || []).forEach((q, i) => ports[q.name] = i)
                p[n.key] = { x: cx + (layerW[l] - w) / 2, y: y, w: w, h: h, dummy: n.dummy, ports: ports }
                y += h + rowGap
            }
            cx += layerW[l] + (l < layers.length - 1 ? columnGap : 0)
        }
        moves = Backend.flowPositions()
        for (const n of flow.nodes) {
            const m = n.dummy ? null : moves[stableKey(n)]
            if (m) {
                p[n.key].x = m[0]
                p[n.key].y = m[1]
                p[n.key].moved = true
            }
        }
        movedCount = Object.keys(moves).length
        placed = p
        canvasSize = Qt.size(cx + margin, fullH + margin * 2)
        growCanvas()
    }

    // where a port's connector is (canvas coordinates); "" is the object itself (its title bar)
    function portPoint(r, port, out) {
        const i = port !== "" && r.ports ? r.ports[port] : undefined
        const y = i === undefined ? r.y + titleHeight / 2 : r.y + titleHeight + typeHeight + i * portHeight + portHeight / 2
        return Qt.point(out ? r.x + r.w : r.x, y)
    }

    // an edge's geometry: an SVG path from the output connector to the input
    // connector, its arrow head, and the middle (for its handle)
    function geometry(e) {
        const a = placed[e.from], b = placed[e.to]
        if (!a || !b)
            return null
        const p0 = portPoint(a, e.fromPort, true), p3 = portPoint(b, e.toPort, false)
        const bez = (s, c1, c2, t) => Qt.point((s.x + 3 * c1.x + 3 * c2.x + t.x) / 8, (s.y + 3 * c1.y + 3 * c2.y + t.y) / 8)
        if (e.from === e.to) {  // a form's widget connected to its own slot: around the top
            const d = Kirigami.Units.gridUnit * 2
            const c1 = Qt.point(p0.x + d, a.y - d), c2 = Qt.point(p3.x - d, a.y - d)
            return { d: `M ${p0.x} ${p0.y} C ${c1.x} ${c1.y} ${c2.x} ${c2.y} ${p3.x} ${p3.y}`, tip: p3, mid: bez(p0, c1, c2, p3) }
        }
        // through the layout's waypoints (while both ends are in their places)
        const via = e.reversed || a.moved || b.moved ? [] : e.path.slice(1, -1).map(k => placed[k]).filter(q => q)
        const q = [p0, ...via.map(r => Qt.point(r.x + r.w / 2, r.y + r.h / 2)), p3]
        let d = `M ${p0.x} ${p0.y}`
        const mids = []
        for (let i = 1; i < q.length; ++i) {
            const s = q[i - 1], t = q[i]
            // out to the right, in from the left (a curve back loops around)
            const h = Math.max(Kirigami.Units.gridUnit * 2.5, Math.abs(t.x - s.x) / 2)
            const c1 = Qt.point(s.x + h, s.y), c2 = Qt.point(t.x - h, t.y)
            d += ` C ${c1.x} ${c1.y} ${c2.x} ${c2.y} ${t.x} ${t.y}`
            mids.push(bez(s, c1, c2, t))
        }
        return { d: d, tip: p3, mid: mids[Math.floor((mids.length - 1) / 2)] }
    }
    function arrowPath(gm) {
        const h = Kirigami.Units.smallSpacing * 2.2, t = gm.tip
        return `M ${t.x} ${t.y} L ${t.x - h} ${t.y - h * 0.55} L ${t.x - h} ${t.y + h * 0.55} Z`
    }

    // the selected (or hovered) object: its edges stand out
    readonly property string focusKey: {
        if (hoverKey !== "")
            return hoverKey
        for (const n of flow.nodes)
            if (n.uid !== 0 && n.uid === Backend.selectedUid)
                return n.key
        return ""
    }
    function edgeActive(e) {
        return focusKey === "" || e.from === focusKey || e.to === focusKey
    }
    function edgeColor(kind) {
        return kind === "signal" ? Kirigami.Theme.highlightColor
             : kind === "binding" ? Kirigami.Theme.textColor : Kirigami.Theme.disabledTextColor
    }

    function portColor(kind) {
        return kind === "signal" ? Kirigami.Theme.highlightColor
             : kind === "function" ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
    }
    function portTip(q) {
        const what = q.kind === "signal" ? qsTr("signal") : q.kind === "function" ? qsTr("function") : qsTr("property")
        if (q.unconnected && q.kind === "property" && !isUi)
            return qsTr("property %1: declared, but nothing in this file sets or reads it (another file may). Click to remove it or see it (line %2)")
                   .arg(q.name).arg(q.line)
        if (q.unconnected && isUi)
            return q.removable ? qsTr("%1 %2: declared in the form, but nothing is connected to it. Click to remove it").arg(what).arg(q.name)
                               : qsTr("%1 %2: declared in the form, but nothing is connected to it here (another widget of its class is)").arg(what).arg(q.name)
        if (q.unconnected)
            return qsTr("%1 %2: nothing in this file is connected to it (it may still be used elsewhere, or only change its own object). Click to %3see its code (line %4)")
                   .arg(what).arg(q.name).arg(q.removable ? qsTr("remove it or ") : "").arg(q.line)
        return q.line ? qsTr("%1 %2: click to see its code (line %3)").arg(what).arg(q.name).arg(q.line)
                      : qsTr("%1 %2: click to see where it is used").arg(what).arg(q.name)
    }
    // a port: where it is written, or else where it is used
    function portClicked(n, q, item) {
        if (q.unconnected && q.removable && n.uid) {
            memberMenu.node = n
            memberMenu.port = q
            // beside the port, past its connector: on the right, or on the
            // left if there's no room
            const gap = connectorSize * zoom
            const right = item.mapToItem(flick, item.width, 0)
            const left = item.mapToItem(flick, 0, 0)
            const x = right.x + gap + memberMenu.implicitWidth <= flick.width ? right.x + gap
                    : left.x - gap - memberMenu.implicitWidth
            memberMenu.popup(flick, Math.max(0, x), right.y)
            return
        }
        if (q.line) {
            jumpRequested(q.line, q.column)
            return
        }
        const items = []
        for (const e of flow.edges)
            if ((e.from === n.key && e.fromPort === q.name) || (e.to === n.key && e.toPort === q.name))
                items.push(...e.items)
        if (items.length === 1)
            jumpRequested(items[0].line, items[0].column)
        else if (items.length > 1) {
            codeMenu.items = items
            codeMenu.popup()
        }
    }

    // Tooltips of what is on the canvas: one, in the view's own coordinates
    // above the item (an item's own tooltip would be placed in the zoomed
    // canvas's coordinates, over the item, and take its clicks)
    component CanvasTip: QtObject {
        required property Item item
        property string text
        property bool shown
        onShownChanged: shown ? pane.showTip(item, text) : pane.hideTip(item)
        onTextChanged: if (shown) pane.showTip(item, text)
        Component.onDestruction: pane.hideTip(item)
    }
    function showTip(item, text) {
        canvasTip.owner = item
        canvasTip.text = text
        const top = item.mapToItem(flick, item.width / 2, 0)
        const bottom = item.mapToItem(flick, item.width / 2, item.height)
        const w = canvasTip.implicitWidth, h = canvasTip.implicitHeight
        canvasTip.x = Math.max(0, Math.min(flick.width - w, top.x - w / 2))
        canvasTip.y = top.y - h - Kirigami.Units.smallSpacing >= 0 ? top.y - h - Kirigami.Units.smallSpacing
                                                                    : bottom.y + Kirigami.Units.smallSpacing
        canvasTip.open()
    }
    function hideTip(item) {
        if (canvasTip.owner === item) {
            canvasTip.owner = null
            canvasTip.close()
        }
    }

    property bool fitPending: false
    // ------------------------------------------------------------ editing a form's connections
    // a connection being dragged out of a widget's handle or one of its
    // signals' connectors (canvas coordinates)
    property string connectFrom: ""
    property string connectSignal: ""
    property point connectStart
    property point connectTo
    property string dropKey: ""
    property string dropPort: ""
    function nodeAt(pt) {
        for (const n of flow.nodes) {
            const r = placed[n.key]
            if (!n.dummy && !n.external && r && pt.x >= r.x - connectorSize && pt.x <= r.x + r.w + connectorSize
                    && pt.y >= r.y && pt.y <= r.y + r.h)
                return n
        }
        return null
    }
    function startConnect(key, signal, start) {
        connectFrom = key
        connectSignal = signal
        connectStart = start
        connectTo = start
    }
    function trackConnect(pt) {
        connectTo = pt
        const n = nodeAt(pt)
        dropKey = n ? n.key : ""
        dropPort = ""
        if (n) {  // over one of its slots: that one
            const r = placed[n.key]
            const i = Math.floor((pt.y - r.y - titleHeight - typeHeight) / portHeight)
            const q = (n.ports || [])[i]
            if (q && q.in)
                dropPort = q.name
        }
    }
    function finishConnect() {
        const from = flow.nodes.find(n => n.key === connectFrom)
        const to = flow.nodes.find(n => n.key === dropKey)
        const signal = connectSignal, slot = dropPort
        connectFrom = ""
        dropKey = ""
        dropPort = ""
        if (from)
            connectionDialog.openFor(-1, from.id, signal, to ? to.id : "", slot)
    }
    function newConnection(sender, receiver) {
        connectionDialog.openFor(-1, sender, "", receiver, "")
    }

    // an edge's handle was clicked: a form's connection can be edited; in QML
    // its code is shown (a menu when it is written in several places)
    function edgeClicked(e) {
        if (isUi) {
            edgeMenu.item = e.items[0]
            edgeMenu.popup()
        } else if (e.items.length === 1) {
            jumpRequested(e.items[0].line, e.items[0].column)
        } else {
            codeMenu.items = e.items
            codeMenu.popup()
        }
    }
    function edgeText(e) {
        return e.items.map(i => i.line ? qsTr("%1 (line %2)").arg(i.label).arg(i.line) : i.label).join("\n")
    }

    QQC2.Menu {
        id: edgeMenu
        objectName: "flowEdgeMenu"
        property var item: ({})
        QQC2.MenuItem {
            text: qsTr("Edit Connection…")
            icon.name: "document-edit"
            onTriggered: connectionDialog.openFor(edgeMenu.item.index, edgeMenu.item.sender, edgeMenu.item.signal,
                                                  edgeMenu.item.receiver, edgeMenu.item.slot)
        }
        QQC2.MenuItem {
            text: qsTr("Delete Connection")
            icon.name: "edit-delete"
            onTriggered: Backend.removeConnection(edgeMenu.item.index)
        }
        QQC2.MenuSeparator {}
        QQC2.MenuItem {
            text: qsTr("Show in Source")
            icon.name: "code-context"
            onTriggered: pane.jumpRequested(edgeMenu.item.line, edgeMenu.item.column)
        }
    }
    // a declared member nothing is connected to (a red port)
    QQC2.Menu {
        id: memberMenu
        objectName: "flowMemberMenu"
        property var node: ({})
        property var port: ({})
        QQC2.MenuItem {
            objectName: "flowRemoveMember"
            text: {
                const p = memberMenu.port
                const what = p.kind === "signal" ? qsTr("Signal") : p.kind === "property" ? qsTr("Property")
                           : pane.isUi ? qsTr("Slot") : qsTr("Function")
                return qsTr("Remove %1 “%2”").arg(what).arg(p.name || "")
            }
            icon.name: "edit-delete"
            onTriggered: Backend.removeMember(memberMenu.node.uid, memberMenu.port.name, memberMenu.port.kind)
        }
        QQC2.MenuSeparator {
            visible: !!memberMenu.port.line
            height: visible ? implicitHeight : 0
        }
        QQC2.MenuItem {
            visible: !!memberMenu.port.line
            height: visible ? implicitHeight : 0
            text: qsTr("Show in Source")
            icon.name: "code-context"
            onTriggered: pane.jumpRequested(memberMenu.port.line, memberMenu.port.column)
        }
    }
    QQC2.Menu {
        id: codeMenu
        objectName: "flowCodeMenu"
        property var items: []
        Instantiator {
            model: codeMenu.items
            delegate: QQC2.MenuItem {
                required property var modelData
                text: qsTr("%1 (line %2)").arg(modelData.label).arg(modelData.line)
                icon.name: "code-context"
                onTriggered: pane.jumpRequested(modelData.line, modelData.column)
            }
            onObjectAdded: (index, object) => codeMenu.insertItem(index, object)
            onObjectRemoved: (index, object) => codeMenu.removeItem(object)
        }
    }
    QQC2.ToolTip {
        id: canvasTip
        objectName: "flowTip"
        parent: flick
        property Item owner: null
        delay: Kirigami.Units.toolTipDelay
    }
    ConnectionDialog {
        id: connectionDialog
        parent: QQC2.Overlay.overlay
    }

    // zoom keeping the point under the pointer (viewport coordinates) in place
    function zoomAt(newZoom, vx, vy) {
        newZoom = Math.max(0.25, Math.min(2, newZoom))
        if (newZoom === zoom)
            return
        // canvas coordinates under the pointer, then the scroll that puts them there again
        const cx = (vx - canvas.x) / zoom
        const cy = (vy - canvas.y) / zoom
        zoom = newZoom
        const ox = Math.max(0, (flick.width - canvas.width * zoom) / 2)
        const oy = Math.max(0, (flick.height - canvas.height * zoom) / 2)
        flick.contentX = Math.max(0, Math.min(flick.contentWidth - flick.width, cx * zoom + ox - vx))
        flick.contentY = Math.max(0, Math.min(flick.contentHeight - flick.height, cy * zoom + oy - vy))
    }
    function fit() {
        if (canvasSize.width <= 0)
            return
        // not laid out yet: once it is
        fitPending = flick.width < Kirigami.Units.gridUnit * 4 || flick.height < Kirigami.Units.gridUnit * 4
        if (fitPending)
            return
        zoom = Math.max(0.25, Math.min(1, flick.width / canvasSize.width, flick.height / canvasSize.height))
    }

    // ------------------------------------------------------------ toolbar
    QQC2.ToolBar {
        Layout.fillWidth: true
        position: QQC2.ToolBar.Header

        RowLayout {
            anchors.fill: parent
            spacing: Kirigami.Units.smallSpacing

            QQC2.ToolButton {
                objectName: "flowSignals"
                icon.name: "format-connect-node"
                text: pane.isUi ? qsTr("Connections (%1)").arg(pane.flow.counts.signal || 0)
                                : qsTr("Signals (%1)").arg(pane.flow.counts.signal || 0)
                checkable: true
                checked: settings.showSignals
                onToggled: { settings.showSignals = checked; pane.reload() }
                QQC2.ToolTip.text: pane.isUi ? qsTr("The form's signal/slot connections")
                                             : qsTr("Signal handlers and Connections, and the functions they call")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.ToolButton {
                objectName: "flowBindings"
                visible: !pane.isUi
                icon.name: "insert-link"
                text: qsTr("Bindings (%1)").arg(pane.flow.counts.binding || 0)
                checkable: true
                checked: settings.showBindings
                onToggled: { settings.showBindings = checked; pane.reload() }
                QQC2.ToolTip.text: qsTr("Properties bound to other objects' properties (dashed)")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.ToolButton {
                objectName: "flowLayout"
                visible: !pane.isUi
                icon.name: "transform-move"
                text: qsTr("Layout (%1)").arg(pane.flow.counts.layout || 0)
                checkable: true
                checked: settings.showLayout
                onToggled: { settings.showLayout = checked; pane.reload() }
                QQC2.ToolTip.text: qsTr("Anchors, sizes and positions bound to other objects (dotted)")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }

            Kirigami.Separator {
                Layout.fillHeight: true
                Layout.topMargin: Kirigami.Units.smallSpacing
                Layout.bottomMargin: Kirigami.Units.smallSpacing
            }

            QQC2.ToolButton {
                objectName: "flowSelectedOnly"
                icon.name: "view-filter"
                text: qsTr("Selected Object Only")
                checkable: true
                checked: settings.selectedOnly
                onToggled: { settings.selectedOnly = checked; pane.reload() }
                QQC2.ToolTip.text: qsTr("Show only what the selected object is connected to")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
            QQC2.ToolButton {
                objectName: "flowUnconnected"
                visible: pane.isUi
                icon.name: "view-list-tree"
                text: qsTr("All Widgets")
                checkable: true
                checked: settings.showUnconnected
                onToggled: { settings.showUnconnected = checked; pane.reload() }
                QQC2.ToolTip.text: qsTr("Also show the widgets and actions that have no connections, to connect them")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }

            Kirigami.Separator {
                visible: pane.isUi
                Layout.fillHeight: true
                Layout.topMargin: Kirigami.Units.smallSpacing
                Layout.bottomMargin: Kirigami.Units.smallSpacing
            }
            QQC2.ToolButton {
                objectName: "flowNewConnection"
                visible: pane.isUi
                icon.name: "list-add"
                text: qsTr("New Connection…")
                onClicked: {
                    const sel = pane.flow.nodes.find(n => n.uid !== 0 && n.uid === Backend.selectedUid)
                    pane.newConnection(sel ? sel.id : Backend.selectedId, "")
                }
                QQC2.ToolTip.text: qsTr("Connect a signal of the selected widget to a slot (or drag from a widget's handle to another)")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }

            Item {
                Layout.fillWidth: true
            }

            QQC2.ToolButton {
                objectName: "flowResetLayout"
                icon.name: "edit-reset"
                text: qsTr("Reset Layout")
                display: QQC2.AbstractButton.IconOnly
                enabled: pane.movedCount > 0
                onClicked: pane.resetLayout()
                QQC2.ToolTip.text: qsTr("Put the objects you moved back in their places")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
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
            QQC2.ToolButton {
                icon.name: "zoom-fit-best"
                text: qsTr("Fit to View")
                display: QQC2.AbstractButton.IconOnly
                onClicked: pane.fit()
                QQC2.ToolTip.text: text
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }
        }
    }

    Kirigami.InlineMessage {
        objectName: "flowTooBig"
        Layout.fillWidth: true
        position: Kirigami.InlineMessage.Position.Header
        visible: pane.tooBig && !pane.showAllAnyway && !settings.selectedOnly
        type: Kirigami.MessageType.Information
        text: qsTr("This document has too many connections to show at once: these are the selected object's. Select another object to follow the flow.")
        actions: Kirigami.Action {
            text: qsTr("Show All")
            icon.name: "view-visible"
            onTriggered: {
                pane.showAllAnyway = true
                pane.reload()
            }
        }
    }

    // ------------------------------------------------------------ graph
    Rectangle {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Kirigami.Theme.colorSet: Kirigami.Theme.View
        Kirigami.Theme.inherit: false
        color: Kirigami.Theme.backgroundColor
        clip: true

        // the view onto the canvas: not a Flickable, whose own wheel handling
        // (scrolling) wins over a WheelHandler inside it. The wheel zooms at
        // the pointer, dragging the background scrolls, and so do the bars.
        Item {
            id: flick
            objectName: "flowFlick"
            anchors.fill: parent
            property real contentX: 0
            property real contentY: 0
            readonly property real contentWidth: Math.max(width, pane.canvasSize.width * pane.zoom)
            readonly property real contentHeight: Math.max(height, pane.canvasSize.height * pane.zoom)
            function clamp() {
                contentX = Math.max(0, Math.min(contentWidth - width, contentX))
                contentY = Math.max(0, Math.min(contentHeight - height, contentY))
            }
            onContentWidthChanged: clamp()
            onContentHeightChanged: clamp()
            onWidthChanged: { clamp(); if (pane.fitPending) Qt.callLater(pane.fit) }
            onHeightChanged: { clamp(); if (pane.fitPending) Qt.callLater(pane.fit) }

            // a mouse wheel zooms (at the pointer)
            WheelHandler {
                id: wheel
                objectName: "flowWheel"
                target: null
                acceptedDevices: PointerDevice.Mouse
                onWheel: event => {
                    const delta = event.angleDelta.y !== 0 ? event.angleDelta.y : event.angleDelta.x
                    pane.zoomAt(pane.zoom * Math.pow(1.0015, delta), wheel.point.position.x, wheel.point.position.y)
                }
            }
            // two fingers on a touchpad scroll (pinching zooms; so does Ctrl with scrolling)
            function touchpadScroll(event, point) {
                if (event.modifiers & Qt.ControlModifier) {
                    pane.zoomAt(pane.zoom * Math.pow(1.0015, event.angleDelta.y), point.x, point.y)
                    return
                }
                // pixels when the touchpad gives them, else wheel steps (120 = 3 lines)
                const d = event.pixelDelta.x !== 0 || event.pixelDelta.y !== 0
                        ? event.pixelDelta : Qt.point(event.angleDelta.x / 4, event.angleDelta.y / 4)
                contentX -= d.x
                contentY -= d.y
                clamp()
            }
            WheelHandler {
                id: touchpad
                objectName: "flowTouchpad"
                target: null
                acceptedDevices: PointerDevice.TouchPad
                onWheel: event => flick.touchpadScroll(event, touchpad.point.position)
            }
            // (a WheelHandler takes one direction: this one the sideways-only swipes)
            WheelHandler {
                id: touchpadSideways
                target: null
                acceptedDevices: PointerDevice.TouchPad
                orientation: Qt.Horizontal
                onWheel: event => {
                    if (event.angleDelta.y === 0 && event.pixelDelta.y === 0)
                        flick.touchpadScroll(event, touchpadSideways.point.position)
                }
            }
            // pinching on a touchpad (or a touch screen) zooms as well
            PinchHandler {
                id: pinch
                target: null
                property real startZoom: 1
                onActiveChanged: if (active) startZoom = pane.zoom
                onActiveScaleChanged: {
                    if (!active)
                        return
                    const c = flick.mapFromItem(null, centroid.scenePosition)
                    pane.zoomAt(startZoom * activeScale, c.x, c.y)
                }
            }
            DragHandler {
                id: pan
                target: null
                cursorShape: active ? Qt.ClosedHandCursor : Qt.ArrowCursor
                property point start
                onActiveChanged: if (active) start = Qt.point(flick.contentX, flick.contentY)
                onTranslationChanged: {
                    if (!active)
                        return
                    flick.contentX = start.x - translation.x
                    flick.contentY = start.y - translation.y
                    flick.clamp()
                }
            }
            // a click on empty space ends hovering highlights / nothing else
            TapHandler {
                onTapped: pane.hoverKey = ""
            }
            QQC2.ScrollBar {
                id: vbar
                z: 10
                orientation: Qt.Vertical
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: hbar.visible ? hbar.top : parent.bottom
                visible: size < 1
                size: flick.height / flick.contentHeight
                position: flick.contentY / flick.contentHeight
                onPositionChanged: if (active) flick.contentY = position * flick.contentHeight
            }
            QQC2.ScrollBar {
                id: hbar
                z: 10
                orientation: Qt.Horizontal
                anchors.left: parent.left
                anchors.right: vbar.visible ? vbar.left : parent.right
                anchors.bottom: parent.bottom
                visible: size < 1
                size: flick.width / flick.contentWidth
                position: flick.contentX / flick.contentWidth
                onPositionChanged: if (active) flick.contentX = position * flick.contentWidth
            }

            Item {
                id: canvas
                width: pane.canvasSize.width
                height: pane.canvasSize.height
                scale: pane.zoom
                transformOrigin: Item.TopLeft
                x: Math.max(0, (flick.width - width * pane.zoom) / 2) - flick.contentX
                y: Math.max(0, (flick.height - height * pane.zoom) / 2) - flick.contentY

                // edges
                Repeater {
                    model: pane.flow.edges
                    delegate: Shape {
                        id: edgeShape
                        required property var modelData
                        readonly property var gm: pane.geometry(modelData)
                        readonly property bool on: pane.edgeActive(modelData)
                        readonly property color stroke: pane.edgeColor(modelData.kind)
                        anchors.fill: parent
                        visible: gm !== null
                        opacity: on ? 1 : 0.15
                        z: on ? 1 : 0
                        preferredRendererType: Shape.CurveRenderer

                        ShapePath {
                            strokeColor: edgeShape.stroke
                            strokeWidth: edgeShape.modelData.kind === "signal" ? 2 : 1.5
                            fillColor: "transparent"
                            strokeStyle: edgeShape.modelData.kind === "signal" ? ShapePath.SolidLine : ShapePath.DashLine
                            dashPattern: edgeShape.modelData.kind === "layout" ? [1, 3] : [4, 3]
                            PathSvg { path: edgeShape.gm ? edgeShape.gm.d : "" }
                        }
                        ShapePath {
                            strokeColor: "transparent"
                            fillColor: edgeShape.stroke
                            PathSvg { path: edgeShape.gm ? pane.arrowPath(edgeShape.gm) : "" }
                        }
                    }
                }

                // a connection being dragged out of a handle or a signal's connector
                Shape {
                    anchors.fill: parent
                    z: 5
                    visible: pane.connectFrom !== ""
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        strokeColor: Kirigami.Theme.highlightColor
                        strokeWidth: 2
                        strokeStyle: ShapePath.DashLine
                        dashPattern: [3, 2]
                        fillColor: "transparent"
                        PathSvg {
                            path: {
                                const s = pane.connectStart, t = pane.connectTo
                                const d = Math.max(Kirigami.Units.gridUnit * 2, Math.abs(t.x - s.x) / 2)
                                return `M ${s.x} ${s.y} C ${s.x + d} ${s.y} ${t.x - d} ${t.y} ${t.x} ${t.y}`
                            }
                        }
                    }
                }

                // objects
                Repeater {
                    model: pane.flow.nodes.filter(n => !n.dummy)
                    delegate: Rectangle {
                        id: box
                        required property var modelData
                        readonly property var g: pane.placed[modelData.key] || { x: 0, y: 0, w: 0, h: 0 }
                        readonly property bool selected: modelData.uid !== 0 && modelData.uid === Backend.selectedUid
                        objectName: "flowNode_" + (modelData.id || modelData.label || modelData.type)
                        x: g.x
                        y: g.y
                        width: g.w
                        height: g.h
                        radius: Kirigami.Units.cornerRadius
                        z: drag.active || hover.hovered || connect.active ? 4 : 2
                        opacity: modelData.unconnected && !hover.hovered ? 0.75 : 1
                        color: modelData.external ? Kirigami.Theme.alternateBackgroundColor : Kirigami.Theme.backgroundColor
                        border.width: selected || pane.dropKey === modelData.key ? 2 : 1
                        border.color: selected || pane.dropKey === modelData.key ? Kirigami.Theme.highlightColor
                                     : Qt.alpha(Kirigami.Theme.textColor, hover.hovered ? 0.5 : 0.25)

                        HoverHandler {
                            id: hover
                            cursorShape: box.modelData.uid ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onHoveredChanged: {
                                if (hovered)
                                    pane.hoverKey = box.modelData.key
                                else if (pane.hoverKey === box.modelData.key)
                                    pane.hoverKey = ""
                            }
                        }
                        TapHandler {
                            onTapped: if (box.modelData.uid) Backend.select(box.modelData.uid)
                            onDoubleTapped: if (box.modelData.line) pane.jumpRequested(box.modelData.line, box.modelData.column)
                        }

                        // the title bar: the object's name, and where it is dragged to move it
                        // (the place is kept until Reset Layout, in the session too)
                        Rectangle {
                            id: titleBar
                            objectName: "flowTitle_" + (box.modelData.id || box.modelData.label || box.modelData.type)
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: box.border.width
                            height: pane.titleHeight - box.border.width
                            radius: Math.max(0, box.radius - box.border.width)
                            color: box.selected ? Qt.alpha(Kirigami.Theme.highlightColor, 0.25)
                                 : titleHover.hovered || drag.active ? Qt.alpha(Kirigami.Theme.textColor, 0.12)
                                 : Qt.alpha(Kirigami.Theme.textColor, 0.06)
                            Rectangle {  // square lower corners
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                height: parent.radius
                                color: parent.color
                            }
                            QQC2.Label {
                                anchors.fill: parent
                                anchors.leftMargin: Kirigami.Units.largeSpacing
                                anchors.rightMargin: Kirigami.Units.largeSpacing * (pane.isUi ? 2 : 1)
                                text: pane.nodeTitle(box.modelData)
                                font.bold: true
                                font.italic: box.modelData.external
                                elide: Text.ElideRight
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }
                            HoverHandler {
                                id: titleHover
                                cursorShape: drag.active ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                            }
                            DragHandler {
                                id: drag
                                target: null
                                cursorShape: Qt.ClosedHandCursor
                                grabPermissions: PointerHandler.CanTakeOverFromAnything
                                property point start
                                onActiveChanged: {
                                    if (active)
                                        start = Qt.point(box.g.x, box.g.y)
                                    else
                                        pane.storeMoves()
                                }
                                onCentroidChanged: {
                                    if (!active)
                                        return
                                    const c = centroid
                                    pane.moveNode(box.modelData.key, start.x + (c.scenePosition.x - c.scenePressPosition.x) / pane.zoom,
                                                  start.y + (c.scenePosition.y - c.scenePressPosition.y) / pane.zoom)
                                }
                            }
                        }
                        QQC2.Label {
                            id: typeLabel
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: titleBar.bottom
                            height: pane.typeHeight
                            anchors.leftMargin: Kirigami.Units.largeSpacing
                            anchors.rightMargin: Kirigami.Units.largeSpacing
                            text: pane.nodeSubtitle(box.modelData)
                            font: Kirigami.Theme.smallFont
                            opacity: box.modelData.label || box.modelData.external ? 0.7 : 0.45
                            elide: Text.ElideRight
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        // the ports: an input's connector on the left, an output's on the right
                        Repeater {
                            model: box.modelData.ports || []
                            delegate: Item {
                                id: port
                                required property var modelData
                                required property int index
                                objectName: "flowPort_" + (box.modelData.id || box.modelData.label) + "_" + modelData.name
                                x: 0
                                y: pane.titleHeight + pane.typeHeight + index * pane.portHeight
                                width: box.width
                                height: pane.portHeight
                                readonly property bool dropHere: pane.dropKey === box.modelData.key && pane.dropPort === modelData.name

                                // nothing connects to it: red
                                readonly property bool loose: port.modelData.unconnected === true
                                readonly property bool clickable: !pane.isUi || (loose && port.modelData.removable === true)
                                Rectangle {
                                    anchors.fill: parent
                                    anchors.leftMargin: 1
                                    anchors.rightMargin: 1
                                    color: port.dropHere ? Qt.alpha(Kirigami.Theme.highlightColor, 0.3)
                                         : portHover.hovered ? Qt.alpha(port.loose ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.highlightColor, 0.15)
                                         : port.loose ? Qt.alpha(Kirigami.Theme.negativeTextColor, 0.08) : "transparent"
                                }
                                QQC2.Label {
                                    anchors.fill: parent
                                    anchors.leftMargin: pane.connectorSize
                                    anchors.rightMargin: pane.connectorSize
                                    text: port.modelData.name
                                    font: Kirigami.Theme.smallFont
                                    color: port.loose ? Kirigami.Theme.negativeTextColor
                                         : port.modelData.kind === "signal" ? Kirigami.Theme.highlightColor : Kirigami.Theme.textColor
                                    elide: Text.ElideRight
                                    verticalAlignment: Text.AlignVCenter
                                    horizontalAlignment: port.modelData.in && !port.modelData.out ? Text.AlignLeft
                                                       : port.modelData.out && !port.modelData.in ? Text.AlignRight : Text.AlignHCenter
                                }
                                // connectors
                                Rectangle {
                                    visible: port.modelData.in
                                    width: pane.connectorSize
                                    height: width
                                    radius: width / 2
                                    x: -width / 2
                                    y: (parent.height - height) / 2
                                    color: Kirigami.Theme.backgroundColor
                                    border.width: 2
                                    border.color: port.loose ? Kirigami.Theme.negativeTextColor : pane.portColor(port.modelData.kind)
                                }
                                Rectangle {
                                    id: outConnector
                                    objectName: "flowOut_" + (box.modelData.id || box.modelData.label) + "_" + port.modelData.name
                                    visible: port.modelData.out
                                    width: pane.connectorSize * (outHover.hovered || outDrag.active ? 1.4 : 1)
                                    height: width
                                    radius: width / 2
                                    x: parent.width - width / 2
                                    y: (parent.height - height) / 2
                                    // (unconnected: hollow, in red)
                                    color: port.loose ? Kirigami.Theme.backgroundColor : pane.portColor(port.modelData.kind)
                                    border.width: port.loose ? 2 : 0
                                    border.color: Kirigami.Theme.negativeTextColor
                                    // a form's signal: drag from here to a slot to connect it again
                                    HoverHandler {
                                        id: outHover
                                        enabled: pane.isUi
                                        cursorShape: Qt.CrossCursor
                                    }
                                    DragHandler {
                                        id: outDrag
                                        target: null
                                        enabled: pane.isUi && !box.modelData.external
                                        grabPermissions: PointerHandler.CanTakeOverFromAnything
                                        onActiveChanged: {
                                            const start = Qt.point(box.g.x + box.g.w, port.y + box.g.y + port.height / 2)
                                            if (active)
                                                pane.startConnect(box.modelData.key, port.modelData.name, start)
                                            else
                                                pane.finishConnect()
                                        }
                                        onCentroidChanged: {
                                            if (!active)
                                                return
                                            const c = centroid
                                            pane.trackConnect(Qt.point(pane.connectStart.x + (c.scenePosition.x - c.scenePressPosition.x) / pane.zoom,
                                                                       pane.connectStart.y + (c.scenePosition.y - c.scenePressPosition.y) / pane.zoom))
                                        }
                                    }
                                    CanvasTip {
                                        item: outConnector
                                        text: qsTr("Drag to a slot to connect %1 to it").arg(port.modelData.name)
                                        shown: outHover.hovered && !outDrag.active
                                    }
                                }
                                HoverHandler {
                                    id: portHover
                                    cursorShape: port.clickable ? Qt.PointingHandCursor : Qt.ArrowCursor
                                }
                                // where it is written (QML): a click shows it; a
                                // declaration nothing uses can be removed
                                TapHandler {
                                    enabled: port.clickable
                                    gesturePolicy: TapHandler.ReleaseWithinBounds
                                    onTapped: pane.portClicked(box.modelData, port.modelData, port)
                                }
                                CanvasTip {
                                    item: port
                                    text: pane.portTip(port.modelData)
                                    shown: portHover.hovered
                                }
                            }
                        }

                        // a form's widget: drag from here to another widget to connect them
                        Rectangle {
                            id: handle
                            objectName: "flowHandle_" + box.modelData.id
                            readonly property bool shown: pane.isUi && !box.modelData.external
                                                          && (hover.hovered || handleHover.hovered || connect.active)
                            visible: shown
                            width: pane.connectorSize * 1.5
                            height: width
                            radius: width / 2
                            x: box.width - width / 2
                            y: (pane.titleHeight - height) / 2
                            color: connect.active || handleHover.hovered ? Kirigami.Theme.highlightColor : Kirigami.Theme.backgroundColor
                            border.width: 2
                            border.color: Kirigami.Theme.highlightColor
                            HoverHandler {
                                id: handleHover
                                enabled: pane.isUi
                                cursorShape: Qt.CrossCursor
                            }
                            DragHandler {
                                id: connect
                                target: null
                                enabled: pane.isUi && !box.modelData.external
                                grabPermissions: PointerHandler.CanTakeOverFromAnything
                                onActiveChanged: {
                                    if (active)
                                        pane.startConnect(box.modelData.key, "", Qt.point(box.g.x + box.g.w, box.g.y + pane.titleHeight / 2))
                                    else
                                        pane.finishConnect()
                                }
                                onCentroidChanged: {
                                    if (!active)
                                        return
                                    const c = centroid
                                    pane.trackConnect(Qt.point(pane.connectStart.x + (c.scenePosition.x - c.scenePressPosition.x) / pane.zoom,
                                                               pane.connectStart.y + (c.scenePosition.y - c.scenePressPosition.y) / pane.zoom))
                                }
                            }
                            CanvasTip {
                                item: handle
                                text: qsTr("Drag to another widget to connect a signal of %1 to it").arg(box.modelData.id)
                                shown: handleHover.hovered && !connect.active
                            }
                        }

                        CanvasTip {
                            item: box
                            text: box.modelData.external ? qsTr("%1 is not defined in this file").arg(box.modelData.label)
                                              : titleHover.hovered ? qsTr("Drag the title bar to move it")
                                              : pane.isUi ? qsTr("Click to select")
                                              : qsTr("Click to select, double-click to see its code")
                            shown: !drag.active && !handleHover.hovered
                                   && (titleHover.hovered || hover.hovered && !(box.modelData.ports || []).length)
                        }
                    }
                }

                // a handle in the middle of each edge: what it does, and a click
                // shows its code (a form's connection: edit or delete it)
                Repeater {
                    model: pane.flow.edges
                    delegate: Rectangle {
                        id: dot
                        required property var modelData
                        readonly property var gm: pane.geometry(modelData)
                        readonly property bool on: pane.edgeActive(modelData)
                        objectName: "flowEdge_" + modelData.from + "." + modelData.fromPort + "_" + modelData.to + "." + modelData.toPort
                        visible: gm !== null
                        // no smaller on screen when zoomed out: it is what is clicked
                        readonly property real size: pane.connectorSize * (dotHover.hovered ? 1.6 : 1.1) / Math.min(1, pane.zoom)
                        width: size
                        height: size
                        radius: size / 2
                        x: gm ? gm.mid.x - size / 2 : 0
                        y: gm ? gm.mid.y - size / 2 : 0
                        z: on ? 3 : 1
                        opacity: on ? 1 : 0.3
                        color: dotHover.hovered ? pane.edgeColor(modelData.kind) : Kirigami.Theme.backgroundColor
                        border.width: 2
                        border.color: pane.edgeColor(modelData.kind)
                        HoverHandler {
                            id: dotHover
                            cursorShape: Qt.PointingHandCursor
                            margin: Kirigami.Units.smallSpacing
                        }
                        TapHandler {
                            gesturePolicy: TapHandler.ReleaseWithinBounds
                            onTapped: pane.edgeClicked(dot.modelData)
                        }
                        CanvasTip {
                            item: dot
                            text: pane.edgeText(dot.modelData) + "\n" + (pane.isUi ? qsTr("Click to edit or delete")
                                                                                             : qsTr("Click to see the code"))
                            shown: dotHover.hovered
                        }
                    }
                }
            }
        }

        Kirigami.PlaceholderMessage {
            anchors.centerIn: parent
            width: parent.width - Kirigami.Units.gridUnit * 4
            visible: pane.flow.nodes.length === 0
            icon.name: "distribute-graph-directed"
            readonly property int total: (pane.flow.counts.signal || 0) + (pane.isUi ? 0 : (pane.flow.counts.binding || 0) + (pane.flow.counts.layout || 0))
            text: pane.isUi && total === 0 ? qsTr("This form has no signal/slot connections")
                : total === 0 ? qsTr("No signal flow found")
                : pane.focused ? qsTr("Nothing connects to the selected object")
                : qsTr("All connections are hidden")
            explanation: pane.isUi && total === 0 ? qsTr("Turn on All Widgets to connect them here, or use New Connection…. Connections made in C++ code are not part of the form.")
                : total === 0 ? qsTr("Signal handlers, Connections and bindings that refer to other objects by their id show up here.")
                : pane.focused ? qsTr("Select another object, or show the whole document.")
                : qsTr("Turn on one of the kinds in the toolbar.")
        }
    }

    // ------------------------------------------------------------ legend
    QQC2.ToolBar {
        Layout.fillWidth: true
        position: QQC2.ToolBar.Footer
        visible: pane.flow.nodes.length > 0

        QQC2.Label {
            anchors.fill: parent
            anchors.leftMargin: Kirigami.Units.smallSpacing
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            font: Kirigami.Theme.smallFont
            opacity: 0.8
            text: pane.isUi ? qsTr("Drag from a widget's handle or a signal to another widget to connect them; click an arrow's dot to edit it. The wheel or a pinch zooms.")
                            : qsTr("Solid: a signal and what it does · dashed: a binding · dotted: layout · red: nothing connected. Click an arrow's dot to see its code; drag a title bar to move an object; the wheel or a pinch zooms.")
        }
    }
}
