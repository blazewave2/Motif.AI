import QtQuick 2.15

import "../js/theme.js" as T

Item {
    id: toggle
    property string label: ""
    property string hint: ""
    property bool checked: true
    signal toggled(bool value)

    implicitHeight: Math.max(text.implicitHeight, 24)

    Column {
        id: text
        anchors { left: parent.left; right: knob.left; rightMargin: 12
                  verticalCenter: parent.verticalCenter }
        spacing: 2
        Text {
            text: toggle.label
            color: T.text
            font.family: T.sans
            font.pixelSize: T.fsSmall
            width: parent.width
            wrapMode: Text.WordWrap
        }
        Text {
            text: toggle.hint
            visible: toggle.hint.length > 0
            color: T.textFaint
            font.family: T.sans
            font.pixelSize: T.fsTiny
            width: parent.width
            wrapMode: Text.WordWrap
        }
    }

    Rectangle {
        id: knob
        anchors { right: parent.right; verticalCenter: parent.verticalCenter }
        width: 38; height: 22; radius: 11
        color: toggle.checked ? T.gold : T.surfaceActive
        Behavior on color { ColorAnimation { duration: T.durFast } }
        Rectangle {
            width: 18; height: 18; radius: 9
            color: toggle.checked ? T.textInverse : T.textMuted
            anchors.verticalCenter: parent.verticalCenter
            x: toggle.checked ? parent.width - width - 2 : 2
            Behavior on x { NumberAnimation { duration: T.durFast
                                              easing.type: Easing.OutCubic } }
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: { toggle.checked = !toggle.checked; toggle.toggled(toggle.checked); }
        }
    }
}
