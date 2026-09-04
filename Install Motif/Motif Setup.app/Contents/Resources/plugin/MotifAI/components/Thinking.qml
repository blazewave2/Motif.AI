// What Motif shows while it is composing: its own phrase mark, drawing itself.
import QtQuick 2.15

import "../js/theme.js" as T

Row {
    id: row
    property bool active: true
    property string label: "Composing…"
    spacing: 10

    PhraseMark {
        id: mark
        width: 26
        height: 12
        color: T.gold
        weight: 1.7
        anchors.verticalCenter: parent.verticalCenter
        progress: 0.0

        SequentialAnimation on progress {
            running: row.active
            loops: Animation.Infinite
            NumberAnimation { from: 0.0; to: 1.0; duration: 1100
                              easing.type: Easing.InOutQuad }
            PauseAnimation { duration: 260 }
            NumberAnimation { from: 1.0; to: 0.0; duration: 500
                              easing.type: Easing.InOutQuad }
        }
    }

    Text {
        text: row.label
        color: T.textMuted
        font.family: T.sans
        font.pixelSize: T.fsBody
        anchors.verticalCenter: parent.verticalCenter
        SequentialAnimation on opacity {
            running: row.active
            loops: Animation.Infinite
            NumberAnimation { to: 0.5; duration: 900; easing.type: Easing.InOutSine }
            NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutSine }
        }
    }
}
