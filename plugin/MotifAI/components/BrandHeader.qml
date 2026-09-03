// The Motif.ai wordmark and tagline.
import QtQuick 2.15

Item {
    id: header
    property var theme
    implicitHeight: column.implicitHeight

    Column {
        id: column
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 6

        Item {
            width: wordmark.implicitWidth + 26
            height: wordmark.implicitHeight
            anchors.horizontalCenter: parent.horizontalCenter

            Text {
                id: wordmark
                text: "Motif.AI"
                color: theme.text
                font.family: theme.serif
                font.pixelSize: theme.fsDisplay
                font.letterSpacing: 0.4
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
            }
            Sparkle {
                width: 13; height: 13
                color: theme.gold
                anchors.left: wordmark.right
                anchors.leftMargin: 3
                anchors.top: wordmark.top
                anchors.topMargin: 1
                opacity: 0.95
            }
            Sparkle {
                width: 7; height: 7
                color: theme.gold
                anchors.left: wordmark.right
                anchors.leftMargin: 15
                anchors.top: wordmark.top
                anchors.topMargin: 11
                opacity: 0.7
            }
        }

        Text {
            text: "Your AI composing partner"
            color: theme.textMuted
            font.family: theme.sans
            font.pixelSize: theme.fsSmall
            anchors.horizontalCenter: parent.horizontalCenter
        }
    }
}
