import QtQuick 2.15

import "../js/theme.js" as T

Rectangle {
    id: btn
    property string label: ""
    property bool primary: false
    property bool interactive: true
    signal clicked()

    implicitWidth: t.implicitWidth + 20
    implicitHeight: 26
    radius: T.radiusSm
    opacity: interactive ? 1 : 0.45
    color: !interactive ? T.surface
         : primary ? (area.containsMouse ? Qt.lighter(T.gold, 1.08) : T.gold)
         : (area.containsMouse ? T.surfaceHover : T.surface)
    border.width: 1
    border.color: primary ? "transparent"
                : (area.containsMouse ? T.borderStrong : T.border)
    Behavior on color { ColorAnimation { duration: T.durFast } }

    Text {
        id: t
        anchors.centerIn: parent
        text: btn.label
        color: btn.primary ? T.textInverse : T.text
        font.family: T.sans
        font.pixelSize: T.fsTiny
        font.weight: btn.primary ? Font.DemiBold : Font.Normal
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        enabled: btn.interactive
        cursorShape: btn.interactive ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: btn.clicked()
    }
}
