import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// Kate-style quick open: a search field over a list, at the top of the window.
// Used for files (Ctrl+Alt+O) and symbols (Ctrl+Alt+P).
QQC2.Popup {
    id: picker

    // items: [{ title, subtitle, icon, … }]; anything else is passed back on pick
    property var items: []
    property string placeholder: qsTr("Search…")
    property string emptyText: qsTr("Nothing found")
    property var shown: []
    signal picked(var item)

    parent: QQC2.Overlay.overlay
    x: Math.round((parent.width - width) / 2)
    y: Kirigami.Units.gridUnit * 2
    width: Math.min(parent.width - Kirigami.Units.gridUnit * 4, Kirigami.Units.gridUnit * 36)
    height: Math.min(parent.height - y - Kirigami.Units.gridUnit * 2, field.height + list.contentHeight + Kirigami.Units.smallSpacing * 3 + (list.count ? 0 : Kirigami.Units.gridUnit * 2))
    padding: Kirigami.Units.smallSpacing
    modal: true
    focus: true
    closePolicy: QQC2.Popup.CloseOnEscape | QQC2.Popup.CloseOnPressOutside

    function show(newItems) {
        items = newItems
        field.text = ""
        refilter()
        open()
        field.forceActiveFocus()
    }

    // subsequence match; contiguous and title matches rank first
    function score(q, s) {
        if (!q)
            return 1
        s = s.toLowerCase()
        const i = s.indexOf(q)
        if (i >= 0)
            return 1000 - i
        let k = 0, gaps = 0
        for (let j = 0; j < s.length && k < q.length; ++j) {
            if (s[j] === q[k])
                ++k
            else if (k)
                ++gaps
        }
        return k === q.length ? Math.max(1, 100 - gaps) : 0
    }
    function refilter() {
        const q = field.text.trim().toLowerCase()
        const out = []
        for (const it of items) {
            const sc = Math.max(score(q, it.title) * 2, score(q, (it.subtitle || "") + "/" + it.title))
            if (sc > 0)
                out.push({ item: it, sc: sc })
        }
        if (q)
            out.sort((a, b) => b.sc - a.sc)
        shown = out.slice(0, 200).map(x => x.item)
        list.currentIndex = 0
    }
    function accept() {
        const it = shown[list.currentIndex]
        if (!it)
            return
        close()
        picked(it)
    }

    contentItem: ColumnLayout {
        spacing: Kirigami.Units.smallSpacing

        Kirigami.SearchField {
            id: field
            Layout.fillWidth: true
            placeholderText: picker.placeholder
            focusSequences: []
            onTextChanged: picker.refilter()
            Keys.onPressed: event => {
                if (event.key === Qt.Key_Down || event.key === Qt.Key_Up) {
                    list.currentIndex = Math.max(0, Math.min(list.count - 1, list.currentIndex + (event.key === Qt.Key_Down ? 1 : -1)))
                    event.accepted = true
                } else if (event.key === Qt.Key_PageDown || event.key === Qt.Key_PageUp) {
                    list.currentIndex = Math.max(0, Math.min(list.count - 1, list.currentIndex + (event.key === Qt.Key_PageDown ? 10 : -10)))
                    event.accepted = true
                } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    picker.accept()
                    event.accepted = true
                }
            }
        }
        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: picker.shown
            highlightMoveDuration: 0
            QQC2.ScrollBar.vertical: QQC2.ScrollBar {}
            delegate: QQC2.ItemDelegate {
                id: row
                required property var modelData
                required property int index
                width: ListView.view.width
                highlighted: ListView.isCurrentItem
                icon.name: modelData.icon || ""
                text: modelData.title
                onClicked: {
                    list.currentIndex = index
                    picker.accept()
                }
                contentItem: RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.Icon {
                        source: row.modelData.icon || ""
                        visible: source !== ""
                        implicitWidth: Kirigami.Units.iconSizes.smallMedium
                        implicitHeight: Kirigami.Units.iconSizes.smallMedium
                    }
                    QQC2.Label {
                        text: row.modelData.title
                        font.bold: row.modelData.bold === true
                        color: row.highlighted ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor
                        elide: Text.ElideRight
                        Layout.maximumWidth: row.width * 0.6
                    }
                    QQC2.Label {
                        Layout.fillWidth: true
                        text: row.modelData.subtitle || ""
                        elide: Text.ElideMiddle
                        color: row.highlighted ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.disabledTextColor
                        font: Kirigami.Theme.smallFont
                    }
                }
            }
            Kirigami.PlaceholderMessage {
                anchors.centerIn: parent
                width: parent.width - Kirigami.Units.largeSpacing * 4
                visible: list.count === 0
                text: picker.emptyText
            }
        }
    }
}
