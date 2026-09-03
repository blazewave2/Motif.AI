// The Create / Chat switch pinned to the bottom of the panel.
import QtQuick 2.15

Item {
    id: bar
    property var theme
    property int currentIndex: 0
    property var labels: ["Create", "Chat"]
    property var glyphs: ["✎", "💬"]

    implicitHeight: 46

    Rectangle {
        anchors.fill: parent
        color: theme.bg
        Rectangle {
            anchors { left: parent.left; right: parent.right; top: parent.top }
            height: 1
            color: theme.border
        }
    }

    Row {
        anchors.fill: parent
        Repeater {
            model: bar.labels.length
            delegate: Item {
                width: bar.width / bar.labels.length
                height: bar.height
                readonly property bool active: bar.currentIndex === index

                Row {
                    anchors.centerIn: parent
                    spacing: 7
                    Text {
                        text: bar.glyphs[index]
                        color: active ? theme.text : theme.textFaint
                        font.family: theme.sans
                        font.pixelSize: 13
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: bar.labels[index]
                        color: active ? theme.text : theme.textFaint
                        font.family: theme.sans
                        font.pixelSize: theme.fsSmall
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                Rectangle {
                    anchors { bottom: parent.bottom; horizontalCenter: parent.horizontalCenter }
                    width: parent.width * 0.5
                    height: 2
                    radius: 1
                    color: theme.gold
                    opacity: active ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: theme.durFast } }
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: bar.currentIndex = index
                }
            }
        }
    }
}
