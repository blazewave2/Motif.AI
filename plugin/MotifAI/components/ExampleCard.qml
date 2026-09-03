// One suggestion in the "Try these examples" list.
import QtQuick 2.15

import "../js/theme.js" as T

Rectangle {
    id: card
    property string line1: ""
    property string line2: ""
    signal activated()

    height: label.implicitHeight + 26
    radius: T.radiusMd
    color: area.containsMouse ? T.surfaceHover : T.surface
    border.width: 1
    border.color: area.containsMouse ? T.borderStrong : T.border
    Behavior on color { ColorAnimation { duration: T.durFast } }
    Behavior on border.color { ColorAnimation { duration: T.durFast } }

    Text {
        id: label
        anchors {
            left: parent.left; right: chevron.left; verticalCenter: parent.verticalCenter
            leftMargin: 13; rightMargin: 8
        }
        text: card.line2.length ? (card.line1 + "\n" + card.line2) : card.line1
        color: T.text
        font.family: T.sans
        font.pixelSize: T.fsSmall
        lineHeight: 1.32
        wrapMode: Text.WordWrap
    }

    Text {
        id: chevron
        anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
        text: "›"
        color: area.containsMouse ? T.text : T.textFaint
        font.family: T.sans
        font.pixelSize: 17
        Behavior on color { ColorAnimation { duration: T.durFast } }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: card.activated()
    }
}
