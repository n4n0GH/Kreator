import QtQuick

ListView {
    property bool seesStore: typeof Store !== "undefined"

    model: Store.notes
    header: Footnote {
    }
    delegate: Text {
        required property string modelData
        text: modelData
    }
}
