import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kirigami.delegates as KD

ColumnLayout {
    id: panel
    spacing: 0

    Kirigami.Theme.colorSet: Kirigami.Theme.View
    Kirigami.Theme.inherit: false

    // The one sidebar: the folder's files, then the document's outline (qmlls'
    // symbols in the source view), components to add and guideline checks.
    property bool sourceMode: false
    readonly property bool showSymbols: sourceMode && Backend.docKind === "qml"
    // remembered tab (0 files, 1 outline/symbols, 2 add, 3 guidelines)
    property int currentTab: 0
    // without a document: the files, or the project's qmllint findings
    readonly property int shownTab: Backend.hasDocument || currentTab === 3 ? currentTab : 0
    readonly property int lintCount: Lsp.projectErrorCount + Lsp.projectWarningCount

    function showTab(index) {
        currentTab = index
    }
    // the source view brings up its outline (qmlls' symbols)
    onSourceModeChanged: if (sourceMode && Backend.hasDocument) currentTab = 1

    QQC2.TabBar {
        id: tabs
        Layout.fillWidth: true
        // icons only when the sidebar is too narrow for the labels
        readonly property bool compact: width < Kirigami.Units.gridUnit * 24

        clip: true

        component SideTab: QQC2.TabButton {
            id: tab
            property string fullText
            property string shortText: fullText
            // (the desktop style ignores `display`, so the label is dropped instead)
            text: tabs.compact && !checked ? "" : shortText
            display: text === "" ? QQC2.AbstractButton.IconOnly : QQC2.AbstractButton.TextBesideIcon
            Accessible.name: fullText
            onClicked: panel.currentTab = QQC2.TabBar.index
            QQC2.ToolTip.text: fullText
            QQC2.ToolTip.visible: (text === "" || text !== fullText) && hovered
            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
        }

        SideTab {
            fullText: Backend.projectPath !== "" ? Backend.projectName : qsTr("Files")
            icon.name: "folder"
            QQC2.ToolTip.text: Backend.projectPath !== "" ? Backend.projectPath : fullText
            QQC2.ToolTip.visible: hovered && (text === "" || Backend.projectPath !== "")
        }
        SideTab {
            enabled: Backend.hasDocument
            fullText: panel.showSymbols ? qsTr("Symbols") : qsTr("Outline")
            icon.name: panel.showSymbols ? "code-class" : "view-list-tree"
        }
        SideTab {
            enabled: Backend.hasDocument
            fullText: qsTr("Add Component")
            shortText: qsTr("Add")
            icon.name: "list-add"
        }
        SideTab {
            readonly property int count: (Backend.hasDocument ? Backend.issueCount : 0) + panel.lintCount
            enabled: Backend.hasDocument || Backend.projectPath !== ""
            fullText: count > 0 ? qsTr("Guidelines (%1)").arg(count) : qsTr("Guidelines")
            icon.name: Lsp.projectErrorCount > 0 ? "data-error"
                       : (Backend.warningCount > 0 || Lsp.projectWarningCount > 0) ? "data-warning" : "checkmark"
        }
    }

    // (a Binding: clicking a tab would break a plain one)
    Binding {
        target: tabs
        property: "currentIndex"
        value: panel.shownTab
    }

    StackLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        currentIndex: panel.shownTab

        // ---------------------------------------------------------- folder
        ProjectPanel {}

        // ---------------------------------------------------------- outline / symbols
        Item {
        SymbolsView {
            anchors.fill: parent
            visible: panel.showSymbols
            cursorLine: applicationWindow().mainPage.sourceLine
        }
        ColumnLayout {
            anchors.fill: parent
            visible: !panel.showSymbols
            spacing: 0

            QQC2.ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                background: Rectangle {
                    color: Kirigami.Theme.backgroundColor
                }

                ListView {
                    id: outlineView
                    clip: true
                    model: Backend.outline
                    keyNavigationEnabled: true
                    activeFocusOnTab: true
                    reuseItems: true
                    currentIndex: -1

                    function syncCurrent() {
                        currentIndex = Backend.selectedRow()
                        if (currentIndex >= 0)
                            positionViewAtIndex(currentIndex, ListView.Contain)
                    }

                    Connections {
                        target: Backend
                        function onSelectionChanged() {
                            outlineView.syncCurrent()
                        }
                        function onContentChanged() {
                            outlineView.syncCurrent()
                        }
                    }
                    Component.onCompleted: syncCurrent()

                    Keys.onUpPressed: Backend.selectRow(Math.max(0, currentIndex - 1))
                    Keys.onDownPressed: Backend.selectRow(Math.min(count - 1, currentIndex + 1))
                    Keys.onLeftPressed: {
                        const item = currentItem
                        if (item && item.hasChildren && item.expanded)
                            Backend.toggleExpanded(item.uid)
                    }
                    Keys.onRightPressed: {
                        const item = currentItem
                        if (item && item.hasChildren && !item.expanded)
                            Backend.toggleExpanded(item.uid)
                    }

                    delegate: QQC2.ItemDelegate {
                        id: row

                        required property int index
                        required property int uid
                        required property int depth
                        required property string typeName
                        required property string fullType
                        required property string objectId
                        required property string label
                        required property bool hasChildren
                        required property bool expanded
                        required property int issueCount

                        width: ListView.view.width
                        highlighted: uid === Backend.selectedUid
                        leftPadding: Kirigami.Units.smallSpacing + depth * Kirigami.Units.gridUnit
                        topPadding: Kirigami.Units.smallSpacing
                        bottomPadding: Kirigami.Units.smallSpacing

                        Accessible.name: typeName + (objectId ? " " + objectId : "")

                        onClicked: {
                            outlineView.forceActiveFocus()
                            Backend.select(uid)
                        }
                        onDoubleClicked: if (hasChildren) Backend.toggleExpanded(uid)

                        contentItem: RowLayout {
                            spacing: Kirigami.Units.smallSpacing

                            QQC2.ToolButton {
                                Layout.preferredWidth: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing * 2
                                Layout.preferredHeight: Layout.preferredWidth
                                padding: 0
                                flat: true
                                opacity: row.hasChildren ? 1 : 0
                                enabled: row.hasChildren
                                icon.name: row.expanded ? "go-down-symbolic" : (Qt.application.layoutDirection === Qt.RightToLeft ? "go-previous-symbolic" : "go-next-symbolic")
                                icon.width: Kirigami.Units.iconSizes.small
                                icon.height: Kirigami.Units.iconSizes.small
                                text: row.expanded ? qsTr("Collapse") : qsTr("Expand")
                                display: QQC2.AbstractButton.IconOnly
                                onClicked: Backend.toggleExpanded(row.uid)
                            }
                            QQC2.Label {
                                text: row.label ? row.label + ":" : ""
                                visible: row.label !== ""
                                color: row.highlighted ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.disabledTextColor
                                font.italic: true
                            }
                            QQC2.Label {
                                text: row.typeName
                                font.bold: row.depth === 0
                                color: row.highlighted ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor
                                elide: Text.ElideRight
                                Layout.fillWidth: row.objectId === ""
                            }
                            QQC2.Label {
                                visible: row.objectId !== ""
                                text: row.objectId
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                                font.family: Kirigami.Theme.fixedWidthFont.family
                                color: row.highlighted ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.linkColor
                            }
                            Kirigami.Icon {
                                visible: row.issueCount > 0
                                source: "data-warning"
                                implicitWidth: Kirigami.Units.iconSizes.small
                                implicitHeight: Kirigami.Units.iconSizes.small
                                QQC2.ToolTip.text: qsTr("%n guideline issue(s)", "", row.issueCount)
                                QQC2.ToolTip.visible: issueHover.hovered
                                HoverHandler {
                                    id: issueHover
                                }
                            }
                        }
                    }
                }
            }

            Kirigami.Separator {
                Layout.fillWidth: true
            }

            Kirigami.ActionToolBar {
                Layout.fillWidth: true
                Layout.margins: Kirigami.Units.smallSpacing
                display: QQC2.AbstractButton.IconOnly
                flat: true
                actions: [
                    Kirigami.Action {
                        text: qsTr("Move Up")
                        icon.name: "go-up"
                        tooltip: qsTr("Move up (Alt+Up)")
                        enabled: !Backend.isRootSelected
                        onTriggered: Backend.moveSelected(-1)
                    },
                    Kirigami.Action {
                        text: qsTr("Move Down")
                        icon.name: "go-down"
                        tooltip: qsTr("Move down (Alt+Down)")
                        enabled: !Backend.isRootSelected
                        onTriggered: Backend.moveSelected(1)
                    },
                    Kirigami.Action {
                        text: qsTr("Duplicate")
                        icon.name: "edit-duplicate"
                        tooltip: qsTr("Duplicate (Ctrl+D)")
                        enabled: !Backend.isRootSelected
                        onTriggered: Backend.duplicateSelected()
                    },
                    Kirigami.Action {
                        text: qsTr("Cut")
                        icon.name: "edit-cut"
                        enabled: !Backend.isRootSelected
                        displayHint: Kirigami.DisplayHint.AlwaysHide
                        onTriggered: Backend.cutSelected()
                    },
                    Kirigami.Action {
                        text: qsTr("Copy")
                        icon.name: "edit-copy"
                        displayHint: Kirigami.DisplayHint.AlwaysHide
                        onTriggered: Backend.copySelected()
                    },
                    Kirigami.Action {
                        text: qsTr("Paste Inside")
                        icon.name: "edit-paste"
                        displayHint: Kirigami.DisplayHint.AlwaysHide
                        onTriggered: Backend.paste()
                    },
                    Kirigami.Action {
                        text: qsTr("Show in %1").arg(Backend.defaultEditorName)
                        icon.name: Backend.defaultEditorIcon
                        displayHint: Kirigami.DisplayHint.AlwaysHide
                        onTriggered: applicationWindow().openInEditor("")
                    },
                    Kirigami.Action {
                        text: qsTr("Delete")
                        icon.name: "edit-delete"
                        tooltip: qsTr("Delete (Del)")
                        enabled: !Backend.isRootSelected
                        onTriggered: Backend.deleteSelected()
                    }
                ]
            }
        }

        }

        // ---------------------------------------------------------- palette
        ColumnLayout {
            spacing: 0

            Kirigami.SearchField {
                // no window-wide Ctrl+F: the source view uses it for find
                focusSequences: []
                id: paletteSearch
                Layout.fillWidth: true
                Layout.margins: Kirigami.Units.smallSpacing
                placeholderText: qsTr("Search components…")
                onTextChanged: Backend.setPaletteFilter(text)
            }

            QQC2.Label {
                Layout.fillWidth: true
                Layout.leftMargin: Kirigami.Units.largeSpacing
                Layout.rightMargin: Kirigami.Units.largeSpacing
                Layout.bottomMargin: Kirigami.Units.smallSpacing
                wrapMode: Text.WordWrap
                font: Kirigami.Theme.smallFont
                opacity: 0.7
                text: Backend.selectedType !== "" ? qsTr("Click to add to %1, or drag onto the design view").arg(Backend.selectedId || Backend.selectedType) : ""
            }

            // Where a clicked component goes: among the selected object's
            // contents, or into one of its properties that hold objects (a
            // page's header, a control's contentItem, a view's delegate…)
            RowLayout {
                id: slotRow
                visible: Backend.docKind === "qml" && Backend.insertSlots.length > 0
                Layout.fillWidth: true
                Layout.leftMargin: Kirigami.Units.largeSpacing
                Layout.rightMargin: Kirigami.Units.smallSpacing
                Layout.bottomMargin: Kirigami.Units.smallSpacing
                spacing: Kirigami.Units.smallSpacing

                // the contents first, then the properties
                readonly property var choices: {
                    const out = [{ name: "", label: qsTr("Its contents"), full: false }]
                    for (const s of Backend.insertSlots) {
                        let label = s.name
                        if (s.full)
                            label = qsTr("%1 (has a %2)").arg(s.name).arg(s.holds === "expression" ? qsTr("value") : s.holds)
                        else if (s.isList && s.holds !== "" && s.holds !== "0")
                            label = qsTr("%1 (%2)").arg(s.name).arg(s.holds)
                        out.push({ name: s.name, label: label, full: s.full })
                    }
                    return out
                }

                QQC2.Label {
                    text: qsTr("Add to:")
                }
                QQC2.ComboBox {
                    id: slotBox
                    objectName: "insertSlotBox"
                    Layout.fillWidth: true
                    model: slotRow.choices
                    textRole: "label"
                    valueRole: "name"
                    Accessible.name: qsTr("Where added components go")
                    onActivated: index => Backend.insertSlot = slotRow.choices[index].name
                    delegate: QQC2.ItemDelegate {
                        required property var modelData
                        required property int index
                        width: ListView.view.width
                        text: modelData.label
                        // (a property that holds one object, and has one)
                        enabled: !modelData.full
                        highlighted: slotBox.highlightedIndex === index
                    }
                    QQC2.ToolTip.text: qsTr("Add the component to the object's contents, or put it into one of its properties, such as a page's header or a list's delegate")
                    QQC2.ToolTip.visible: hovered && !popup.visible
                    QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                }
                // (a Binding: choosing an entry would break a plain one)
                Binding {
                    target: slotBox
                    property: "currentIndex"
                    value: Math.max(0, slotRow.choices.findIndex(c => c.name === Backend.insertSlot))
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
                    id: paletteView
                    clip: true
                    model: Backend.palette
                    section.property: "category"
                    section.delegate: Kirigami.ListSectionHeader {
                        required property string section
                        width: ListView.view.width
                        text: section
                    }
                    delegate: QQC2.ItemDelegate {
                        id: pdel
                        required property string name
                        required property string iconName
                        required property string description
                        required property int index
                        width: ListView.view.width
                        text: name
                        Accessible.description: description
                        QQC2.ToolTip.text: description
                        QQC2.ToolTip.visible: hovered
                        QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay

                        contentItem: KD.IconTitleSubtitle {
                            title: pdel.name
                            subtitle: pdel.description
                            icon.name: pdel.iconName
                            icon.width: Kirigami.Units.iconSizes.smallMedium
                            selected: pdel.highlighted || pdel.down
                        }
                        onClicked: Backend.insertComponent(pdel.index)

                        // drag onto the design view to place it there
                        DragHandler {
                            id: paletteDrag
                            objectName: "paletteDrag"
                            target: null
                            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad | PointerDevice.Stylus
                            onActiveChanged: {
                                if (active)
                                    componentDrag.begin(pdel.index, pdel.name, pdel.iconName, centroid.scenePosition)
                                else
                                    componentDrag.end()
                            }
                            onCentroidChanged: {
                                if (active)
                                    componentDrag.follow(centroid.scenePosition, centroid.modifiers & Qt.ShiftModifier)
                            }
                        }
                    }

                    Kirigami.PlaceholderMessage {
                        anchors.centerIn: parent
                        width: parent.width - Kirigami.Units.largeSpacing * 4
                        visible: paletteView.count === 0
                        icon.name: "search"
                        text: qsTr("No matching components")
                    }
                }
            }
        }

        // ---------------------------------------------------------- guidelines
        IssuesPanel {}
    }

    // A component being dragged from the Add tab: drawn above the window and
    // dropped on the design view (its DropArea takes "kreator/component").
    Item {
        id: componentDrag
        objectName: "componentDrag"
        parent: QQC2.Overlay.overlay
        z: 1000
        visible: Drag.active
        width: 1
        height: 1
        property int paletteIndex: -1
        property bool free: false    // Shift held: not snapped to the grid
        // the design view shows where it goes, at its size: the chip steps aside
        property bool previewed: false
        property string name: ""
        property string iconName: ""
        Drag.keys: ["kreator/component"]
        Drag.dragType: Drag.Internal
        Drag.hotSpot: Qt.point(0, 0)

        function begin(index, name, iconName, scenePos) {
            paletteIndex = index
            componentDrag.name = name
            componentDrag.iconName = iconName
            follow(scenePos, false)
            Drag.active = true
        }
        function follow(scenePos, shift) {
            free = !!shift
            const p = parent ? parent.mapFromItem(null, scenePos.x, scenePos.y) : scenePos
            x = p.x
            y = p.y
        }
        function end() {
            if (Drag.active)
                Drag.drop()
            Drag.active = false
            paletteIndex = -1
            previewed = false
        }

        Rectangle {
            x: Kirigami.Units.largeSpacing
            y: Kirigami.Units.largeSpacing
            width: chipRow.implicitWidth + Kirigami.Units.largeSpacing * 2
            height: chipRow.implicitHeight + Kirigami.Units.smallSpacing * 2
            radius: Kirigami.Units.cornerRadius
            color: Kirigami.Theme.backgroundColor
            border.color: Kirigami.Theme.highlightColor
            opacity: componentDrag.previewed ? 0 : 0.95
            RowLayout {
                id: chipRow
                anchors.centerIn: parent
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Icon {
                    source: componentDrag.iconName
                    implicitWidth: Kirigami.Units.iconSizes.small
                    implicitHeight: Kirigami.Units.iconSizes.small
                }
                QQC2.Label {
                    text: componentDrag.name
                }
            }
        }
    }

    // background work (indexing), like Discover's install progress
    IndexStatus {
        Layout.fillWidth: true
    }
}
