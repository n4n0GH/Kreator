import QtQuick
import QtQuick.Controls

Item {
    id: root
    property int count: 0
    Button {
        text: "go"
        onClicked: root.count++
    }
}
