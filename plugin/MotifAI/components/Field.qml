import QtQuick 2.15

Item {
    id: field
    property var theme
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
            color: theme.textMuted
            font.family: theme.sans
            font.pixelSize: theme.fsTiny
        }
        Rectangle {
            width: parent.width
            height: 32
            radius: theme.radiusSm
            color: theme.inputBg
            border.width: 1
            border.color: edit.activeFocus ? theme.borderFocus : theme.border
            Behavior on border.color { ColorAnimation { duration: theme.durFast } }
            TextInput {
                id: edit
                anchors { fill: parent; leftMargin: 9; rightMargin: 9 }
                verticalAlignment: TextInput.AlignVCenter
                color: theme.text
                font.family: theme.mono
                font.pixelSize: theme.fsTiny
                selectionColor: theme.goldDim
                selectedTextColor: theme.textInverse
                selectByMouse: true
                clip: true
            }
        }
        Text {
            width: parent.width
            text: field.hint
            visible: field.hint.length > 0
            color: theme.textFaint
            font.family: theme.sans
            font.pixelSize: theme.fsTiny
            wrapMode: Text.WordWrap
        }
    }
}
