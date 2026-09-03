// One turn in the conversation.  User turns are compact and right-weighted;
// Motif's turns carry the score summary and the actions that follow from it.
import QtQuick 2.15

Item {
    id: bubble
    property var theme
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
        radius: theme.radiusMd
        color: bubble.isUser ? theme.surface
             : bubble.role === "error" ? Qt.rgba(0.88, 0.47, 0.42, 0.10)
             : theme.bgElevated
        border.width: 1
        border.color: bubble.role === "error" ? Qt.rgba(0.88, 0.47, 0.42, 0.35)
                    : theme.border
        implicitHeight: content.implicitHeight + 22

        Column {
            id: content
            anchors {
                left: parent.left; right: parent.right; top: parent.top
                leftMargin: 13; rightMargin: 13; topMargin: 11
            }
            spacing: 8

            Row {
                spacing: 6
                visible: !bubble.isUser
                Sparkle {
                    width: 9; height: 9
                    color: bubble.role === "error" ? theme.danger : theme.gold
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: bubble.role === "error" ? "Motif.AI — problem" : "Motif.AI"
                    color: bubble.role === "error" ? theme.danger : theme.goldDim
                    font.family: theme.sans
                    font.pixelSize: theme.fsTiny
                    font.letterSpacing: 0.5
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            Text {
                width: parent.width
                text: bubble.text
                color: theme.text
                font.family: theme.sans
                font.pixelSize: theme.fsBody
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
                radius: theme.radiusSm
                color: theme.inputBg
                border.width: 1
                border.color: theme.border
                Text {
                    id: detailText
                    anchors { fill: parent; margins: 8 }
                    text: bubble.detail
                    color: theme.textMuted
                    font.family: theme.mono
                    font.pixelSize: theme.fsTiny
                    wrapMode: Text.WrapAnywhere
                }
            }

            Row {
                spacing: 7
                visible: bubble.showActions && bubble.hasScore

                SmallButton {
                    theme: bubble.theme
                    label: "Open in MuseScore"
                    primary: true
                    onClicked: bubble.openRequested()
                }
                SmallButton {
                    theme: bubble.theme
                    label: "Try again"
                    onClicked: bubble.regenerateRequested()
                }
                SmallButton {
                    theme: bubble.theme
                    label: bubble.detailOpen ? "Hide plan" : "Plan"
                    visible: bubble.detail.length > 0
                    onClicked: bubble.detailOpen = !bubble.detailOpen
                }
            }
        }
    }
}
