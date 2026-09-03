// The prompt field: a rounded input that grows with the text, with a submit
// affordance that only lights up when there is something to send.
import QtQuick 2.15

import "../js/theme.js" as T

Item {
    id: box
    property string placeholder: "Describe what you want to compose..."
    property alias text: input.text
    property bool busy: false
    property bool interactive: true
    signal submitted(string value)

    implicitHeight: Math.max(96, input.implicitHeight + 46)

    function clear() { input.text = ""; }
    function focusInput() { input.forceActiveFocus(); }
    function send() {
        var v = input.text.trim();
        if (v.length === 0 || busy || !interactive) return;
        box.submitted(v);
    }

    Rectangle {
        id: frame
        anchors.fill: parent
        radius: T.radiusMd
        color: T.inputBg
        border.width: 1
        border.color: input.activeFocus ? T.borderFocus : T.border
        Behavior on border.color { ColorAnimation { duration: T.durFast } }

        TextEdit {
            id: input
            anchors {
                left: parent.left; right: parent.right; top: parent.top
                leftMargin: 12; rightMargin: 12; topMargin: 11
            }
            color: T.text
            font.family: T.sans
            font.pixelSize: T.fsBody
            selectionColor: T.goldDim
            selectedTextColor: T.textInverse
            wrapMode: TextEdit.Wrap
            selectByMouse: true
            enabled: box.interactive
            textFormat: TextEdit.PlainText

            // Enter sends; Shift+Enter inserts a newline, as in any chat field.
            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    if (event.modifiers & Qt.ShiftModifier) {
                        event.accepted = false;
                    } else {
                        event.accepted = true;
                        box.send();
                    }
                }
            }
        }

        Text {
            anchors.fill: input
            text: box.placeholder
            color: T.textFaint
            font.family: T.sans
            font.pixelSize: T.fsBody
            visible: input.text.length === 0 && !input.activeFocus
            elide: Text.ElideRight
        }

        Rectangle {
            id: submit
            width: 30; height: 26
            radius: T.radiusSm
            anchors { right: parent.right; bottom: parent.bottom; margins: 9 }
            color: submitArea.containsMouse && active ? T.surfaceActive
                 : active ? T.surface : "transparent"
            border.width: 1
            border.color: active ? T.borderStrong : T.border
            readonly property bool active: input.text.trim().length > 0 && !box.busy
            opacity: active ? 1.0 : 0.45
            Behavior on opacity { NumberAnimation { duration: T.durFast } }
            Behavior on color { ColorAnimation { duration: T.durFast } }

            Text {
                anchors.centerIn: parent
                text: box.busy ? "⋯" : "↵"
                color: submit.active ? T.text : T.textFaint
                font.family: T.sans
                font.pixelSize: 15
            }
            MouseArea {
                id: submitArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: submit.active ? Qt.PointingHandCursor : Qt.ArrowCursor
                onClicked: box.send()
            }
        }
    }
}
