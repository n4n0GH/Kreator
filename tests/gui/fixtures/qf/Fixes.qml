import QtQuick
import QtQuick.Controls

ApplicationWindow {
    id: root
    property int counter: 0

    ListView {
        model: 3
        delegate: Label {
            text: "row " + counter
        }
    }
    Button {
        onClicked: (mouse) => console.log(mouse)
        Component.onCompleted: { counter = 1 }
    }
    Item {
        width: parent.width
        heigth: 20
    }
    Label {
        text: modelData
    }
}
