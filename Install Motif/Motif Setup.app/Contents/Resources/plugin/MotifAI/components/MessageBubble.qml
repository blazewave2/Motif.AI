// One turn in the conversation.  User turns are compact and right-weighted;
// Motif's turns carry the score summary and the actions that follow from it.
import QtQuick 2.15

import "../js/theme.js" as T

Item {
    id: bubble
    property string role: "assistant"     // user | assistant | system | error
    property string text: ""
    property string detail: ""
    property bool hasScore: false
    property bool showActions: false
    signal openRequested()
    signal regenerateRequested()
    signal detailToggled()

    property bool detailOpen: false
    readonly property bool isUser: role === "user"

    width: parent ? parent.width : 320
    implicitHeight: frame.implicitHeight

    Rectangle {
        id: frame
        width: parent.width
        radius: T.radiusMd
        color: bubble.isUser ? T.surface
             : bubble.role === "error" ? Qt.rgba(0.88, 0.47, 0.42, 0.10)
             : T.bgElevated
        border.width: 1
        border.color: bubble.role === "error" ? Qt.rgba(0.88, 0.47, 0.42, 0.35)
                    : T.border
        implicitHeight: content.implicitHeight + 22

        Column {
            id: content
            anchors {
                left: parent.left; right: parent.right; top: parent.top
                leftMargin: 13; rightMargin: 13; topMargin: 11
            }
            spacing: 8

            Row {
                spacing: 7
                visible: !bubble.isUser
                PhraseMark {
                    width: 18; height: 8
                    color: bubble.role === "error" ? T.danger : T.gold
                    weight: 1.4
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: "Motif.AI"
                    color: bubble.role === "error" ? T.danger : T.goldDim
                    font.family: T.serif
                    font.pixelSize: T.fsSmall
                    font.letterSpacing: 0.3
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            Text {
                width: parent.width
                text: bubble.text
                color: T.text
                font.family: T.sans
                font.pixelSize: T.fsBody
                wrapMode: Text.WordWrap
                lineHeight: 1.36
                textFormat: Text.StyledText
                onLinkActivated: bubble.detailToggled()
            }

            // The structural summary, folded away until asked for.
            Rectangle {
                width: parent.width
                visible: bubble.detailOpen && bubble.detail.length > 0
                height: visible ? detailText.implicitHeight + 16 : 0
                radius: T.radiusSm
                color: T.inputBg
                border.width: 1
                border.color: T.border
                Text {
                    id: detailText
                    anchors { fill: parent; margins: 8 }
                    text: bubble.detail
                    color: T.textMuted
                    font.family: T.mono
                    font.pixelSize: T.fsTiny
                    wrapMode: Text.WrapAnywhere
                }
            }

            Row {
                spacing: 7
                visible: bubble.showActions && bubble.hasScore

                SmallButton {
                    label: "Open the score"
                    primary: true
                    onClicked: bubble.openRequested()
                }
                SmallButton {
                    label: "Another take"
                    onClicked: bubble.regenerateRequested()
                }
                SmallButton {
                    label: bubble.detailOpen ? "Hide details" : "Details"
                    visible: bubble.detail.length > 0
                    onClicked: bubble.detailOpen = !bubble.detailOpen
                }
            }
        }
    }
}
