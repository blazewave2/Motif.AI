// The prompt field: a rounded input that grows with the text, with a submit
// affordance that only lights up when there is something to send.
import QtQuick 2.15

Item {
    id: box
    property var theme
    property string placeholder: "Describe what you want to compose..."
    property alias text: input.text
    property bool busy: false
    property bool enabled: true
    signal submitted(string value)

    implicitHeight: Math.max(96, input.implicitHeight + 46)

    function clear() { input.text = ""; }
    function focusInput() { input.forceActiveFocus(); }
    function send() {
        var v = input.text.trim();
        if (v.length === 0 || busy || !enabled) return;
        box.submitted(v);
    }

    Rectangle {
        id: frame
        anchors.fill: parent
        radius: theme.radiusMd
        color: theme.inputBg
        border.width: 1
        border.color: input.activeFocus ? theme.borderFocus : theme.border
        Behavior on border.color { ColorAnimation { duration: theme.durFast } }

        TextEdit {
            id: input
            anchors {
                left: parent.left; right: parent.right; top: parent.top
                leftMargin: 12; rightMargin: 12; topMargin: 11
            }
            color: theme.text
            font.family: theme.sans
            font.pixelSize: theme.fsBody
            selectionColor: theme.goldDim
            selectedTextColor: theme.textInverse
            wrapMode: TextEdit.Wrap
            selectByMouse: true
            enabled: box.enabled
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
            color: theme.textFaint
            font.family: theme.sans
            font.pixelSize: theme.fsBody
            visible: input.text.length === 0 && !input.activeFocus
            elide: Text.ElideRight
        }

        Rectangle {
            id: submit
            width: 30; height: 26
            radius: theme.radiusSm
            anchors { right: parent.right; bottom: parent.bottom; margins: 9 }
            color: submitArea.containsMouse && active ? theme.surfaceActive
                 : active ? theme.surface : "transparent"
            border.width: 1
            border.color: active ? theme.borderStrong : theme.border
            readonly property bool active: input.text.trim().length > 0 && !box.busy
            opacity: active ? 1.0 : 0.45
            Behavior on opacity { NumberAnimation { duration: theme.durFast } }
            Behavior on color { ColorAnimation { duration: theme.durFast } }

            Text {
                anchors.centerIn: parent
                text: box.busy ? "⋯" : "↵"
                color: submit.active ? theme.text : theme.textFaint
                font.family: theme.sans
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
