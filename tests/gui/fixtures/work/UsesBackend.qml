import QtQuick

// An application with objects named like Kreator's own.
Item {
    width: 200
    height: 100

    property bool seesBackend: typeof Backend !== "undefined"
    property bool seesLsp: typeof Lsp !== "undefined"
    property bool seesTextLayout: typeof TextLayout !== "undefined"

    Text {
        // (what a missing object reads as: an error, not Kreator's file name)
        text: Backend.fileName
    }
}
