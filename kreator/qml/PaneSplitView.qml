import QtQuick
import QtQuick.Controls as QQC2
import org.kde.qqc2desktopstyle.private as StylePrivate

// A SplitView whose handles don't steal clicks from scrollbars. The desktop
// style widens each handle's grab area 6 px (12 px while hovered) to both
// sides, which covers the vertical scrollbar at the right edge of the pane on
// its left. Panes here keep their scrollbars on the trailing edge, so the
// extra grab area goes only towards the leading edge of the next pane.
QQC2.SplitView {
    id: control

    handle: StylePrivate.StyleItem {
        id: handle
        elementType: "splitter"
        horizontal: control.orientation === Qt.Horizontal

        readonly property int extra: 4
        readonly property bool rtl: Qt.application.layoutDirection === Qt.RightToLeft

        containmentMask: Item {
            x: handle.horizontal && handle.rtl ? -handle.extra : 0
            y: 0
            width: handle.width + (handle.horizontal ? handle.extra : 0)
            height: handle.height + (handle.horizontal ? 0 : handle.extra)
        }
    }
}
