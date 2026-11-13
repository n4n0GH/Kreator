import QtQuick

// A file of the module org.example.notes: it uses the module's C++ singleton
// `Store`, and its other files, without importing anything for that.
Item {
    width: 300
    height: 200

    property string storeTitle: Store.title
    property int noteCount: Store.notes.length
    property bool hasUndo: typeof Store.undo === "function"

    NoteList {
        objectName: "list"
        anchors.fill: parent
    }
}
