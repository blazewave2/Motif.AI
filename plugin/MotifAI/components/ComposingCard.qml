// While Motif composes: which stage it is at, what it is thinking about or
// which bar it is writing, how far through it is, and a way to stop.
import QtQuick 2.9

import "../js/theme.js" as T

Rectangle {
    id: card
    property string label: "Composing…"
    property string detail: ""
    property real fraction: 0.0
    property real elapsed: 0
    property bool stopping: false
    property bool canStop: true
    signal stopRequested()

    width: parent ? parent.width : 320
    implicitHeight: body.implicitHeight + 24
    radius: T.radiusMd
    color: T.bgElevated
    border.width: 1
    border.color: T.border

    function clock(seconds) {
        var s = Math.max(0, Math.floor(seconds));
        var m = Math.floor(s / 60);
        var r = s % 60;
        return m + ":" + (r < 10 ? "0" : "") + r;
    }

    Column {
        id: body
        anchors {
            left: parent.left; right: parent.right; top: parent.top
            leftMargin: 13; rightMargin: 13; topMargin: 12
        }
        spacing: 9

        Row {
            spacing: 10
            width: parent.width

            PhraseMark {
                id: mark
                width: 26
                height: 12
                color: T.gold
                weight: 1.7
                anchors.verticalCenter: parent.verticalCenter
                progress: 0.0
                SequentialAnimation on progress {
                    running: !card.stopping
                    loops: Animation.Infinite
                    NumberAnimation { from: 0.0; to: 1.0; duration: 1100
                                      easing.type: Easing.InOutQuad }
                    PauseAnimation { duration: 260 }
                    NumberAnimation { from: 1.0; to: 0.0; duration: 500
                                      easing.type: Easing.InOutQuad }
                }
            }

            Text {
                width: parent.width - mark.width - 10
                text: card.stopping ? "Stopping…" : card.label
                color: T.text
                font.family: T.sans
                font.pixelSize: T.fsBody
                elide: Text.ElideRight
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        // What the composer is thinking about, or the bar it is writing.
        Text {
            width: parent.width
            text: card.detail
            visible: card.detail.length > 0 && !card.stopping
            color: T.textMuted
            font.family: T.serif
            font.italic: true
            font.pixelSize: T.fsSmall
            wrapMode: Text.WordWrap
            maximumLineCount: 3
            elide: Text.ElideRight
            lineHeight: 1.3
        }

        Rectangle {
            width: parent.width
            height: 3
            radius: 2
            color: T.surface
            Rectangle {
                width: parent.width * Math.max(0.02, Math.min(1.0, card.fraction))
                height: parent.height
                radius: 2
                color: T.gold
                Behavior on width { NumberAnimation { duration: T.durSlow
                                                      easing.type: Easing.OutCubic } }
            }
        }

        Item {
            width: parent.width
            height: stop.implicitHeight
            Text {
                text: card.clock(card.elapsed)
                color: T.textFaint
                font.family: T.sans
                font.pixelSize: T.fsTiny
                anchors.verticalCenter: parent.verticalCenter
            }
            SmallButton {
                id: stop
                label: card.stopping ? "Stopping" : "Stop"
                interactive: card.canStop && !card.stopping
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                onClicked: card.stopRequested()
            }
        }
    }
}
