// One suggestion in the "Try these examples" list.
import QtQuick 2.15

Rectangle {
    id: card
    property var theme
    property string line1: ""
    property string line2: ""
    signal activated()

    height: label.implicitHeight + 26
    radius: theme.radiusMd
    color: area.containsMouse ? theme.surfaceHover : theme.surface
    border.width: 1
    border.color: area.containsMouse ? theme.borderStrong : theme.border
    Behavior on color { ColorAnimation { duration: theme.durFast } }
    Behavior on border.color { ColorAnimation { duration: theme.durFast } }

    Text {
        id: label
        anchors {
            left: parent.left; right: chevron.left; verticalCenter: parent.verticalCenter
            leftMargin: 13; rightMargin: 8
        }
        text: card.line2.length ? (card.line1 + "\n" + card.line2) : card.line1
        color: theme.text
        font.family: theme.sans
        font.pixelSize: theme.fsSmall
        lineHeight: 1.32
        wrapMode: Text.WordWrap
    }

    Text {
        id: chevron
        anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
        text: "›"
        color: area.containsMouse ? theme.text : theme.textFaint
        font.family: theme.sans
        font.pixelSize: 17
        Behavior on color { ColorAnimation { duration: theme.durFast } }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: card.activated()
    }
}
