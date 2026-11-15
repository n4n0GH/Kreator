"""Components that can be inserted from the palette.

QML snippets use the placeholders {K} (Kirigami prefix), {C} (QtQuick.Controls
prefix), {L} (QtQuick.Layouts prefix), {M} (the prefix of the entry's own
module) and {T} (translation call, e.g. i18n).
Defaults follow the KDE HIG: spacing from Kirigami.Units, translated strings,
title case for buttons/actions and sentence case for labels.

Optional keys of an entry:
  slot    the property of the selected object it goes into ("actions", …)
  visual  False for objects that aren't drawn (models, settings, dialogs…):
          they have no position, and stay with the object they are added to
  id      False for objects that can't have an id (ListElement)

The Add tab shows what a component looks like before it is added (see
preview_qml()): the snippet itself, live. Optional keys for that:
  demo    QML to show instead of the snippet, for components that show
          nothing on their own (an empty layout gets example contents)
  stage   how it is put on the preview's stage:
            "center"  at its own size (the default)
            "wide"    as wide as the stage (the default for snippets that
                      fill their layout's width)
            "fill"    filling the stage (the default for snippets anchored
                      to their parent)
            "popup"   a dialog, opened on the stage
            "none"    nothing is drawn (the default for visual=False)
  height  the stage's height in grid units, for "fill" and "popup" (the
          others take the height of the component)
  note    a line shown below the preview
"""

import re

KIRIGAMI = ("org.kde.kirigami", "Kirigami")
CONTROLS = ("QtQuick.Controls", "QQC2")
LAYOUTS = ("QtQuick.Layouts", "")
QUICK = ("QtQuick", "")
CORE = ("QtCore", "")
ITEM_MODELS = ("org.kde.kitemmodels", "KItemModels")

# a page as it looks in a window: with its title and actions in the toolbar
_IN_WINDOW = ('{K}ApplicationItem {\n    pageStack.globalToolBar.style: {K}ApplicationHeaderStyle.ToolBar\n'
              '    pageStack.initialPage: %s\n}')
# an example picture (a data: URL, so that nothing has to be installed)
_PICTURE = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='100'>"
            "<rect width='160' height='100' fill='%2393cee9'/><circle cx='122' cy='28' r='12' fill='%23fdbc4b'/>"
            "<path d='M0 100 L52 38 L88 78 L112 56 L160 100 Z' fill='%2327ae60'/></svg>")


def _boxes(count: int) -> str:
    """Example contents of a layout (`Box` is the preview stage's placeholder)."""
    return "".join(f'    Box {{\n        text: "{i}"\n    }}\n' for i in range(1, count + 1))


QML_COMPONENTS = [
    # --- Kirigami: pages & app structure
    dict(cat="Kirigami — Pages", name="Page", icon="document-new", module=KIRIGAMI,
         desc="A page with a title and actions in the toolbar",
         qml='{K}Page {\n    title: {T}("Page")\n}', slot="page", stage="fill", height=11,
         demo=_IN_WINDOW % ('{K}Page {\n        title: {T}("Page")\n        actions: {K}Action {\n'
                            '            icon.name: "list-add"\n            text: {T}("Add Item")\n        }\n'
                            '        {C}Label {\n            anchors.centerIn: parent\n'
                            '            text: {T}("Page contents")\n        }\n    }')),
    dict(cat="Kirigami — Pages", name="ScrollablePage", icon="view-list-details", module=KIRIGAMI,
         desc="Page whose content scrolls; use for lists and long forms",
         qml='{K}ScrollablePage {\n    title: {T}("Page")\n}', slot="page", stage="fill", height=11,
         demo=_IN_WINDOW % ('{K}ScrollablePage {\n        title: {T}("Page")\n        ListView {\n'
                            '            model: 20\n            delegate: {C}ItemDelegate {\n'
                            '                required property int index\n'
                            '                width: ListView.view.width\n'
                            '                text: {T}("Item %1", index + 1)\n            }\n        }\n    }')),
    dict(cat="Kirigami — Pages", name="GlobalDrawer", icon="view-split-left-right", module=KIRIGAMI,
         desc="Application-wide navigation drawer",
         qml='{K}GlobalDrawer {\n    isMenu: false\n}', slot="globalDrawer", stage="fill", height=10,
         # (a drawer lives at the edge of its window: it can't be put on the stage)
         note="A sketch: the drawer slides in at the window's edge, beside the pages",
         demo='RowLayout {\n    spacing: 0\n    {C}Pane {\n        Layout.fillHeight: true\n'
              '        {K}Theme.colorSet: {K}Theme.View\n        {K}Theme.inherit: false\n        padding: 0\n'
              '        contentItem: ColumnLayout {\n            spacing: 0\n            Repeater {\n'
              '                model: [\n                    { icon: "go-home", text: {T}("Home") },\n'
              '                    { icon: "bookmarks", text: {T}("Bookmarks") },\n'
              '                    { icon: "configure", text: {T}("Settings") }\n                ]\n'
              '                delegate: {C}ItemDelegate {\n                    required property var modelData\n'
              '                    Layout.fillWidth: true\n                    icon.name: modelData.icon\n'
              '                    text: modelData.text\n                }\n            }\n'
              '            Item {\n                Layout.fillHeight: true\n            }\n        }\n    }\n'
              '    {K}Separator {\n        Layout.fillHeight: true\n    }\n'
              '    Item {\n        Layout.fillWidth: true\n        Layout.fillHeight: true\n'
              '        {C}Label {\n            anchors.centerIn: parent\n            opacity: 0.6\n'
              '            text: {T}("Page")\n        }\n    }\n}'),
    dict(cat="Kirigami — Pages", name="Action", icon="code-context", module=KIRIGAMI,
         desc="A toolbar / menu action (goes into the page's actions)",
         qml='{K}Action {\n    icon.name: "list-add"\n    text: {T}("Add Item")\n}', slot="actions", stage="wide",
         note="Shown as a button of a toolbar, or as an entry of a menu",
         demo='{K}ActionToolBar {\n    alignment: Qt.AlignHCenter\n    actions: {K}Action {\n'
              '        icon.name: "list-add"\n        text: {T}("Add Item")\n    }\n}'),
    dict(cat="Kirigami — Pages", name="Dialog", icon="dialog-messages", module=KIRIGAMI,
         desc="Modal dialog with title and standard buttons",
         qml='{K}Dialog {\n    title: {T}("Dialog")\n    standardButtons: {K}Dialog.Ok | {K}Dialog.Cancel\n    padding: {K}Units.largeSpacing\n}', visual=False, stage="popup",
         demo='{K}Dialog {\n    title: {T}("Dialog")\n    standardButtons: {K}Dialog.Ok | {K}Dialog.Cancel\n'
              '    padding: {K}Units.largeSpacing\n    {C}Label {\n        text: {T}("Dialog contents")\n    }\n}'),
    dict(cat="Kirigami — Pages", name="PromptDialog", icon="dialog-information", module=KIRIGAMI,
         desc="Short question with a subtitle and buttons",
         qml='{K}PromptDialog {\n    title: {T}("Delete File?")\n    subtitle: {T}("This cannot be undone.")\n    standardButtons: {K}Dialog.Ok | {K}Dialog.Cancel\n}', visual=False, stage="popup", height=7),
    # --- Kirigami: content
    dict(cat="Kirigami — Content", name="FormLayout", icon="view-form", module=KIRIGAMI,
         desc="Two-column label/field layout following the HIG",
         qml='{K}FormLayout {\n}', stage="wide",
         demo='{K}FormLayout {\n    {C}TextField {\n        {K}FormData.label: {T}("Name:")\n    }\n'
              '    {C}ComboBox {\n        {K}FormData.label: {T}("Language:")\n'
              '        model: [{T}("English"), {T}("Deutsch")]\n    }\n'
              '    {C}CheckBox {\n        {K}FormData.label: {T}("Updates:")\n'
              '        text: {T}("Check automatically")\n    }\n}'),
    dict(cat="Kirigami — Content", name="Heading", icon="draw-text", module=KIRIGAMI,
         desc="Title text with semantic heading levels",
         qml='{K}Heading {\n    level: 2\n    text: {T}("Heading")\n}'),
    dict(cat="Kirigami — Content", name="Card", icon="games-config-board", module=KIRIGAMI,
         desc="Card with header, contents and actions",
         qml='{K}Card {\n    banner.title: {T}("Card Title")\n    contentItem: {C}Label {\n        text: {T}("Card contents")\n        wrapMode: Text.WordWrap\n    }\n}', stage="wide"),
    dict(cat="Kirigami — Content", name="InlineMessage", icon="dialog-information", module=KIRIGAMI,
         desc="In-content message for information, warnings or errors",
         qml='{K}InlineMessage {\n    {L}Layout.fillWidth: true\n    type: {K}MessageType.Information\n    text: {T}("Something you should know about.")\n    visible: true\n}'),
    dict(cat="Kirigami — Content", name="PlaceholderMessage", icon="help-hint", module=KIRIGAMI,
         desc="Explains empty views and offers a helpful action",
         qml='{K}PlaceholderMessage {\n    anchors.centerIn: parent\n    width: parent.width - ({K}Units.largeSpacing * 4)\n    icon.name: "folder-open"\n    text: {T}("Nothing here yet")\n    explanation: {T}("Items you add will show up here.")\n}', height=11),
    dict(cat="Kirigami — Content", name="SearchField", icon="search", module=KIRIGAMI,
         desc="Text field with search icon and clear button",
         qml='{K}SearchField {\n}'),
    dict(cat="Kirigami — Content", name="ActionTextField", icon="edit-rename", module=KIRIGAMI,
         desc="Text field with buttons inside its frame, e.g. to add an item",
         qml='{K}ActionTextField {\n    placeholderText: {T}("Add an item")\n    rightActions: {K}Action {\n        icon.name: "list-add"\n        text: {T}("Add Item")\n    }\n}'),
    dict(cat="Kirigami — Content", name="Icon", icon="image-x-generic", module=KIRIGAMI,
         desc="Themed icon",
         qml='{K}Icon {\n    source: "kde"\n    implicitWidth: {K}Units.iconSizes.medium\n    implicitHeight: {K}Units.iconSizes.medium\n}'),
    dict(cat="Kirigami — Content", name="Separator", icon="format-justify-fill", module=KIRIGAMI,
         desc="Thin line separating content",
         qml='{K}Separator {\n    {L}Layout.fillWidth: true\n}'),
    dict(cat="Kirigami — Content", name="Chip", icon="tag", module=KIRIGAMI,
         desc="Compact element for tags or filters",
         qml='{K}Chip {\n    text: {T}("Tag")\n    closable: false\n}'),
    dict(cat="Kirigami — Content", name="ActionToolBar", icon="configure", module=KIRIGAMI,
         desc="Toolbar that collapses actions into an overflow menu",
         qml='{K}ActionToolBar {\n    {L}Layout.fillWidth: true\n    actions: [\n        {K}Action {\n            icon.name: "document-edit"\n            text: {T}("Edit")\n        }\n    ]\n}'),
    dict(cat="Kirigami — Content", name="CardsListView", icon="view-media-playlist", module=KIRIGAMI,
         desc="List view designed for cards",
         qml='{K}CardsListView {\n    model: 3\n    delegate: {K}AbstractCard {\n        contentItem: {C}Label {\n            text: {T}("Card %1", index + 1)\n        }\n    }\n}', stage="fill", height=11),
    dict(cat="Kirigami — Content", name="LinkButton", icon="edit-link", module=KIRIGAMI,
         desc="Text that behaves like a link",
         qml='{K}LinkButton {\n    text: {T}("Learn More")\n}'),
    dict(cat="Kirigami — Content", name="SelectableLabel", icon="edit-select", module=KIRIGAMI,
         desc="Read-only text the user can select and copy",
         qml='{K}SelectableLabel {\n    text: {T}("Selectable text")\n}'),
    # --- Controls
    dict(cat="Controls", name="Label", icon="draw-text", module=CONTROLS,
         desc="Theme-aware text (prefer over plain Text)",
         qml='{C}Label {\n    text: {T}("Label")\n}'),
    dict(cat="Controls", name="Button", icon="dialog-ok", module=CONTROLS,
         desc="Push button; use title case text and an icon",
         qml='{C}Button {\n    icon.name: "dialog-ok"\n    text: {T}("Button")\n}'),
    dict(cat="Controls", name="ToolButton", icon="configure", module=CONTROLS,
         desc="Flat button for toolbars",
         qml='{C}ToolButton {\n    icon.name: "configure"\n    text: {T}("Configure")\n    display: {C}AbstractButton.IconOnly\n    {C}ToolTip.text: text\n    {C}ToolTip.visible: hovered\n    {C}ToolTip.delay: {K}Units.toolTipDelay\n}'),
    dict(cat="Controls", name="TextField", icon="edit-rename", module=CONTROLS,
         desc="Single-line text input",
         qml='{C}TextField {\n    placeholderText: {T}("Enter text…")\n}'),
    dict(cat="Controls", name="TextArea", icon="text-plain", module=CONTROLS,
         desc="Multi-line text input",
         qml='{C}TextArea {\n    placeholderText: {T}("Enter text…")\n    wrapMode: TextEdit.Wrap\n}'),
    dict(cat="Controls", name="CheckBox", icon="checkbox", module=CONTROLS,
         desc="On/off option; use sentence case",
         qml='{C}CheckBox {\n    text: {T}("Enable option")\n}'),
    dict(cat="Controls", name="Switch", icon="checkbox", module=CONTROLS,
         desc="Toggles a setting that applies immediately",
         qml='{C}Switch {\n    text: {T}("Enable feature")\n}'),
    dict(cat="Controls", name="RadioButton", icon="radio", module=CONTROLS,
         desc="One choice from a set",
         qml='{C}RadioButton {\n    text: {T}("Option")\n}'),
    dict(cat="Controls", name="ComboBox", icon="view-list-text", module=CONTROLS,
         desc="Drop-down selection",
         qml='{C}ComboBox {\n    model: [{T}("First"), {T}("Second"), {T}("Third")]\n}'),
    dict(cat="Controls", name="SpinBox", icon="adjustlevels", module=CONTROLS,
         desc="Integer input with up/down buttons",
         qml='{C}SpinBox {\n    from: 0\n    to: 100\n}'),
    dict(cat="Controls", name="Slider", icon="adjustlevels", module=CONTROLS,
         desc="Choose a value from a range",
         qml='{C}Slider {\n    from: 0\n    to: 100\n    value: 50\n}'),
    dict(cat="Controls", name="ProgressBar", icon="kt-speed-limits", module=CONTROLS,
         desc="Shows progress of an operation",
         qml='{C}ProgressBar {\n    value: 0.5\n}'),
    dict(cat="Controls", name="BusyIndicator", icon="view-refresh", module=CONTROLS,
         desc="Indicates ongoing activity",
         qml='{C}BusyIndicator {\n    running: true\n}'),
    dict(cat="Controls", name="TabBar", icon="tab-new", module=CONTROLS,
         desc="Switch between views",
         qml='{C}TabBar {\n    {C}TabButton {\n        text: {T}("First")\n    }\n    {C}TabButton {\n        text: {T}("Second")\n    }\n}'),
    dict(cat="Controls", name="ScrollView", icon="transform-move", module=CONTROLS,
         desc="Scrollable area",
         qml='{C}ScrollView {\n}',
         demo='{C}ScrollView {\n    implicitWidth: {K}Units.gridUnit * 12\n'
              '    implicitHeight: {K}Units.gridUnit * 6\n    {C}Label {\n'
              '        text: Array.from({ length: 12 }, (_, i) => {T}("Line %1", i + 1)).join("\\n")\n    }\n}'),
    dict(cat="Controls", name="ItemDelegate", icon="view-list-details", module=CONTROLS,
         desc="List item",
         qml='{C}ItemDelegate {\n    text: {T}("Item")\n}', stage="wide"),
    dict(cat="Controls", name="CheckDelegate", icon="checkbox", module=CONTROLS,
         desc="List item with a check box",
         qml='{C}CheckDelegate {\n    text: {T}("Item")\n}', stage="wide"),
    dict(cat="Controls", name="ToolBar", icon="configure-toolbars", module=CONTROLS,
         desc="Bar for a page's header or footer; holds one item, e.g. a field or a row",
         qml='{C}ToolBar {\n}', stage="wide",
         demo='{C}ToolBar {\n    contentItem: RowLayout {\n        {C}ToolButton {\n'
              '            icon.name: "go-previous"\n        }\n        {C}Label {\n'
              '            Layout.fillWidth: true\n            text: {T}("Title")\n        }\n'
              '        {C}ToolButton {\n            icon.name: "application-menu"\n        }\n    }\n}'),
    # --- Layouts
    dict(cat="Layouts", name="ColumnLayout", icon="object-rows", module=LAYOUTS,
         desc="Arranges children vertically",
         qml='{L}ColumnLayout {\n    spacing: {K}Units.smallSpacing\n}',
         demo='ColumnLayout {\n    spacing: {K}Units.smallSpacing\n' + _boxes(3) + '}'),
    dict(cat="Layouts", name="RowLayout", icon="object-columns", module=LAYOUTS,
         desc="Arranges children horizontally",
         qml='{L}RowLayout {\n    spacing: {K}Units.smallSpacing\n}',
         demo='RowLayout {\n    spacing: {K}Units.smallSpacing\n' + _boxes(3) + '}'),
    dict(cat="Layouts", name="GridLayout", icon="view-grid", module=LAYOUTS,
         desc="Arranges children in a grid",
         qml='{L}GridLayout {\n    columns: 2\n    rowSpacing: {K}Units.smallSpacing\n    columnSpacing: {K}Units.smallSpacing\n}',
         demo='GridLayout {\n    columns: 2\n    rowSpacing: {K}Units.smallSpacing\n'
              '    columnSpacing: {K}Units.smallSpacing\n' + _boxes(4) + '}'),
    dict(cat="Layouts", name="StackLayout", icon="view-media-playlist", module=LAYOUTS,
         desc="Shows one child at a time",
         qml='{L}StackLayout {\n}', note="Only the current child is shown: here the first of three",
         demo='StackLayout {\n' + _boxes(3) + '}'),
    # --- QtQuick basics
    dict(cat="Qt Quick", name="Item", icon="draw-rectangle", module=QUICK,
         desc="Basic visual item / container",
         qml='Item {\n    implicitWidth: {K}Units.gridUnit * 10\n    implicitHeight: {K}Units.gridUnit * 5\n}', stage="none",
         note="Draws nothing itself: it groups and positions what is put into it"),
    dict(cat="Qt Quick", name="Rectangle", icon="draw-rectangle", module=QUICK,
         desc="Filled rectangle; use theme colours",
         qml='Rectangle {\n    implicitWidth: {K}Units.gridUnit * 5\n    implicitHeight: {K}Units.gridUnit * 5\n    color: {K}Theme.backgroundColor\n    border.color: {K}ColorUtils.linearInterpolation({K}Theme.backgroundColor, {K}Theme.textColor, {K}Theme.frameContrast)\n    radius: {K}Units.cornerRadius\n}'),
    dict(cat="Qt Quick", name="ListView", icon="view-list-details", module=QUICK,
         desc="Scrolling list of delegates",
         qml='ListView {\n    model: 5\n    delegate: {C}ItemDelegate {\n        required property int index\n        width: ListView.view.width\n        text: {T}("Item %1", index + 1)\n    }\n}', stage="fill", height=10),
    dict(cat="Qt Quick", name="Repeater", icon="media-playlist-repeat", module=QUICK,
         desc="Creates items from a model",
         qml='Repeater {\n    model: 3\n    delegate: {C}Label {\n        required property int index\n        text: {T}("Item %1", index + 1)\n    }\n}',
         demo='Column {\n    spacing: {K}Units.smallSpacing\n    Repeater {\n        model: 3\n'
              '        delegate: {C}Label {\n            required property int index\n'
              '            text: {T}("Item %1", index + 1)\n        }\n    }\n}'),
    dict(cat="Qt Quick", name="Image", icon="image-x-generic", module=QUICK,
         desc="Displays an image file",
         qml='Image {\n    fillMode: Image.PreserveAspectFit\n}',
         demo='Image {\n    fillMode: Image.PreserveAspectFit\n    source: "' + _PICTURE + '"\n}'),
    dict(cat="Qt Quick", name="MouseArea", icon="input-mouse", module=QUICK,
         desc="Handles mouse input",
         qml='MouseArea {\n    anchors.fill: parent\n}', stage="none",
         note="Draws nothing: the area it covers reacts to the mouse"),
    dict(cat="Qt Quick", name="Timer", icon="chronometer", module=QUICK,
         desc="Triggers an action after an interval",
         qml='Timer {\n    interval: 1000\n}', visual=False),
    # --- data and logic: objects that aren't drawn
    dict(cat="Data and Logic", name="ListModel", icon="view-list-text", module=QUICK,
         desc="A list of entries for a view to show; give it an id and add ListElements",
         qml='ListModel {\n}', visual=False),
    dict(cat="Data and Logic", name="ListElement", icon="list-add", module=QUICK,
         desc="One entry of a ListModel; its properties are the entry's fields",
         qml='ListElement {\n}', visual=False, id=False),
    dict(cat="Data and Logic", name="KSortFilterProxyModel", icon="view-filter", module=ITEM_MODELS,
         desc="Shows a model's rows filtered or sorted, without changing the model",
         qml='{M}KSortFilterProxyModel {\n    sourceModel: null\n}', visual=False),
    dict(cat="Data and Logic", name="Connections", icon="network-connect", module=QUICK,
         desc="Reacts to another object's signals (add onSignal functions in the source view)",
         qml='Connections {\n    target: null\n}', visual=False),
    dict(cat="Data and Logic", name="Settings", icon="configure", module=CORE,
         desc="Remembers the values of its properties between sessions",
         qml='Settings {\n    category: "General"\n}', visual=False),
]


# --------------------------------------------------------------------------- previews

_TR_WITH_ARGUMENT = re.compile(r'\{T\}\(("(?:[^"\\]|\\.)*"), ([^()]+)\)')

STANDALONE_IMPORTS = ("import QtQuick\nimport QtQuick.Controls as QQC2\nimport QtQuick.Layouts\n"
                      "import org.kde.kirigami as Kirigami\n")
NOT_DRAWN = "Not drawn: it works behind the scenes"


def standalone(snippet: str) -> str:
    """A snippet outside any document, for a file that has STANDALONE_IMPORTS."""
    snippet = _TR_WITH_ARGUMENT.sub(r"qsTr(\1).arg(\2)", snippet)
    for key, text in (("{T}", "qsTr"), ("{K}", "Kirigami."), ("{C}", "QQC2."), ("{L}", ""), ("{M}", "")):
        snippet = snippet.replace(key, text)
    return snippet


def _own(snippet: str, what: str) -> bool:
    """Does the snippet's object itself (not one inside it) set `what`…?"""
    return any(line.startswith("    " + what) for line in snippet.split("\n"))


def _with_members(snippet: str, *lines: str) -> str:
    head, brace, rest = snippet.partition("{\n")
    return head + brace + "".join(f"    {line}\n" for line in lines) + rest


def _indented(snippet: str, by: int) -> str:
    return "\n".join(" " * by + line if line else line for line in snippet.split("\n"))


def preview_stage(entry: dict) -> str:
    """How the Add tab shows a QML component (see the module's description)."""
    if "stage" in entry:
        return entry["stage"]
    if "demo" not in entry and not entry.get("visual", True):
        return "none"
    snippet = standalone(entry.get("demo", entry["qml"]))
    if _own(snippet, "anchors."):
        return "fill"
    return "wide" if _own(snippet, "Layout.fillWidth") else "center"


def preview_note(entry: dict) -> str:
    return entry.get("note", NOT_DRAWN if "qml" in entry and preview_stage(entry) == "none" else "")


# the stage: an item as large as the Add tab's preview makes it. Its implicit
# height is the height the preview takes (within limits). `Box` stands in for
# the contents of a layout.
_STAGE = STANDALONE_IMPORTS + """
Item {
    id: stage
%s
    component Box: Rectangle {
        property alias text: boxLabel.text
        implicitWidth: Kirigami.Units.gridUnit * 4
        implicitHeight: Kirigami.Units.gridUnit * 2
        radius: Kirigami.Units.cornerRadius
        color: Qt.alpha(Kirigami.Theme.highlightColor, 0.15)
        border.color: Qt.alpha(Kirigami.Theme.highlightColor, 0.6)
        QQC2.Label {
            id: boxLabel
            anchors.centerIn: parent
        }
    }
}
"""
_IN_COLUMN = """    implicitHeight: content.implicitHeight
    ColumnLayout {
        id: content
        anchors.centerIn: parent
        width: %s
        spacing: 0
%s
    }
"""


def preview_qml(entry: dict) -> str:
    """A QML file showing the component as the Add tab previews it: the
    snippet that is added (or the entry's `demo`) on a stage; "" if there is
    nothing to draw."""
    stage = preview_stage(entry)
    if stage == "none":
        return ""
    snippet = standalone(entry.get("demo", entry["qml"]))
    if stage == "popup":
        # open, but not taking over the window (nor the keyboard) like a real one
        snippet = _with_members(snippet, "id: demo", "parent: stage", "z: 2", "modal: false", "dim: false",
                                "focus: false", "closePolicy: QQC2.Popup.NoAutoClose",
                                "popupType: QQC2.Popup.Item", "visible: true")
        # (a height of its own: a dialog's depends on the room it has)
        body = f"    implicitHeight: Kirigami.Units.gridUnit * {entry.get('height', 9)}\n" + _indented(snippet, 4)
    elif stage == "fill":
        if not _own(snippet, "anchors."):
            snippet = _with_members(snippet, "anchors.fill: parent")
        body = f"    implicitHeight: Kirigami.Units.gridUnit * {entry.get('height', 10)}\n" + _indented(snippet, 4)
    else:
        if stage == "wide" and not _own(snippet, "Layout.fillWidth"):
            snippet = _with_members(snippet, "Layout.fillWidth: true")
        width = "parent.width" if stage == "wide" else "Math.min(implicitWidth, parent.width)"
        body = _IN_COLUMN % (width, _indented(snippet, 8))
    return _STAGE % body.rstrip("\n")


def _w(cls, cat, icon, desc, **props):
    return dict(cat=cat, name=cls, type=cls, icon=icon, desc=desc,
                props={k: v for k, v in props.items()})


UI_COMPONENTS = [
    _w("QVBoxLayout", "Layouts", "object-rows", "Vertical box layout"),
    _w("QHBoxLayout", "Layouts", "object-columns", "Horizontal box layout"),
    _w("QGridLayout", "Layouts", "view-grid", "Grid layout"),
    _w("QFormLayout", "Layouts", "view-form", "Label/field form layout (preferred for settings)"),
    dict(cat="Layouts", name="Vertical Spacer", type="Spacer", orientation="Qt::Vertical",
         icon="go-down", desc="Expanding vertical space"),
    dict(cat="Layouts", name="Horizontal Spacer", type="Spacer", orientation="Qt::Horizontal",
         icon="go-next", desc="Expanding horizontal space"),
    _w("QPushButton", "Buttons", "dialog-ok", "Push button; use title case",
       text=("string", "Button")),
    _w("QToolButton", "Buttons", "configure", "Tool button", text=("string", "…")),
    _w("QCheckBox", "Buttons", "checkbox", "Check box; use sentence case", text=("string", "Enable option")),
    _w("QRadioButton", "Buttons", "radio", "Radio button", text=("string", "Option")),
    _w("QDialogButtonBox", "Buttons", "dialog-ok", "Standard dialog buttons",
       standardButtons=("set", "QDialogButtonBox::Cancel|QDialogButtonBox::Ok")),
    _w("QLabel", "Display", "draw-text", "Text label", text=("string", "Label")),
    _w("QProgressBar", "Display", "kt-speed-limits", "Progress bar", value=("number", "24")),
    _w("QLineEdit", "Input", "edit-rename", "Single-line text input", placeholderText=("string", "Enter text…")),
    _w("QTextEdit", "Input", "text-plain", "Rich text editor"),
    _w("QPlainTextEdit", "Input", "text-plain", "Plain text editor"),
    _w("QSpinBox", "Input", "adjustlevels", "Integer input"),
    _w("QDoubleSpinBox", "Input", "adjustlevels", "Decimal input"),
    _w("QComboBox", "Input", "view-list-text", "Drop-down list"),
    _w("QSlider", "Input", "adjustlevels", "Slider", orientation=("enum", "Qt::Horizontal")),
    _w("QDateEdit", "Input", "view-calendar-day", "Date input"),
    _w("QGroupBox", "Containers", "object-group", "Titled group of controls", title=("string", "Group")),
    _w("QWidget", "Containers", "window", "Generic container"),
    _w("QFrame", "Containers", "draw-rectangle", "Frame", frameShape=("enum", "QFrame::StyledPanel")),
    _w("QTabWidget", "Containers", "tab-new", "Tabbed pages"),
    _w("QStackedWidget", "Containers", "view-media-playlist", "Stack of pages"),
    _w("QScrollArea", "Containers", "transform-move", "Scrollable area", widgetResizable=("bool", "true")),
    _w("QListWidget", "Item Views", "view-list-details", "Simple list"),
    _w("QTreeWidget", "Item Views", "view-list-tree", "Simple tree"),
    _w("QTableWidget", "Item Views", "view-grid", "Simple table"),
    _w("QListView", "Item Views", "view-list-details", "Model based list"),
    _w("QTreeView", "Item Views", "view-list-tree", "Model based tree"),
]
