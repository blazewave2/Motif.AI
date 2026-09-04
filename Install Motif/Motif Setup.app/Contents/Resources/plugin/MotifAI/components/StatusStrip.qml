// Connection state.  A plugin that silently fails is worse than one that says
// exactly what is wrong and how to fix it, so this strip is explicit.
import QtQuick 2.15

import "../js/theme.js" as T

Rectangle {
    id: strip
    property string status: "checking"     // checking | ready | offline | error
    property string engine: ""
    property string detail: ""
    signal retryRequested()
    signal helpRequested()

    visible: status !== "ready"
    height: visible ? col.implicitHeight + 18 : 0
    radius: T.radiusSm
    color: status === "offline" || status === "error"
           ? Qt.rgba(0.88, 0.47, 0.42, 0.10) : T.surface
    border.width: 1
    border.color: status === "offline" || status === "error"
                  ? Qt.rgba(0.88, 0.47, 0.42, 0.32) : T.border

    Column {
        id: col
        anchors { left: parent.left; right: parent.right; top: parent.top
                  leftMargin: 11; rightMargin: 11; topMargin: 9 }
        spacing: 7

        Text {
            width: parent.width
            wrapMode: Text.WordWrap
            color: strip.status === "checking" ? T.textMuted : T.text
            font.family: T.sans
            font.pixelSize: T.fsTiny
            lineHeight: 1.3
            text: strip.status === "checking"
                  ? "Waking Motif…"
                  : strip.status === "offline"
                  ? "Motif isn\'t answering yet. It usually starts on its own a "
                    + "moment after you sign in."
                  : strip.detail
            textFormat: Text.StyledText
        }
        Row {
            spacing: 7
            visible: strip.status !== "checking"
            SmallButton { label: "Try again"; primary: true
                          onClicked: strip.retryRequested() }
            SmallButton { label: "Help"; onClicked: strip.helpRequested() }
        }
    }
}
