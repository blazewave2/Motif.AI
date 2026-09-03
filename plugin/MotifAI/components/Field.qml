import QtQuick 2.15

import "../js/theme.js" as T

Item {
    id: field
    property string label: ""
    property string hint: ""
    property alias value: edit.text

    implicitHeight: col.implicitHeight

    Column {
        id: col
        width: parent.width
        spacing: 5

        Text {
            text: field.label
            color: T.textMuted
            font.family: T.sans
            font.pixelSize: T.fsTiny
        }
        Rectangle {
            width: parent.width
            height: 32
            radius: T.radiusSm
            color: T.inputBg
            border.width: 1
            border.color: edit.activeFocus ? T.borderFocus : T.border
            Behavior on border.color { ColorAnimation { duration: T.durFast } }
            TextInput {
                id: edit
                anchors { fill: parent; leftMargin: 9; rightMargin: 9 }
                verticalAlignment: TextInput.AlignVCenter
                color: T.text
                font.family: T.mono
                font.pixelSize: T.fsTiny
                selectionColor: T.goldDim
                selectedTextColor: T.textInverse
                selectByMouse: true
                clip: true
            }
        }
        Text {
            width: parent.width
            text: field.hint
            visible: field.hint.length > 0
            color: T.textFaint
            font.family: T.sans
            font.pixelSize: T.fsTiny
            wrapMode: Text.WordWrap
        }
    }
}
