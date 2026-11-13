import QtQuick
import QtQuick.Controls

ApplicationWindow {
    visible: true
    MyButton {
        caption: "First"
    }
    MyButton {
        caption: "Second"
        onClicked: console.log(caption)
    }
}
