// Connection state.  A plugin that silently fails is worse than one that says
// exactly what is wrong and how to fix it, so this strip is explicit.
import QtQuick 2.15

Rectangle {
    id: strip
    property var theme
    property string state: "checking"      // checking | ready | offline | error
    property string engine: ""
    property string detail: ""
    signal retryRequested()
    signal helpRequested()

    visible: state !== "ready"
    height: visible ? col.implicitHeight + 18 : 0
    radius: theme.radiusSm
    color: state === "offline" || state === "error"
           ? Qt.rgba(0.88, 0.47, 0.42, 0.10) : theme.surface
    border.width: 1
    border.color: state === "offline" || state === "error"
                  ? Qt.rgba(0.88, 0.47, 0.42, 0.32) : theme.border

    Column {
        id: col
        anchors { left: parent.left; right: parent.right; top: parent.top
                  leftMargin: 11; rightMargin: 11; topMargin: 9 }
        spacing: 7

        Text {
            width: parent.width
            wrapMode: Text.WordWrap
            color: strip.state === "checking" ? theme.textMuted : theme.text
            font.family: theme.sans
            font.pixelSize: theme.fsTiny
            lineHeight: 1.3
            text: strip.state === "checking"
                  ? "Connecting to the Motif engine…"
                  : strip.state === "offline"
                  ? "The Motif engine is not running. Start it with <b>motif serve</b> "
                    + "in a terminal, then press Retry."
                  : strip.detail
            textFormat: Text.StyledText
        }
        Row {
            spacing: 7
            visible: strip.state !== "checking"
            SmallButton { theme: strip.theme; label: "Retry"; onClicked: strip.retryRequested() }
            SmallButton { theme: strip.theme; label: "How to start it"
                          onClicked: strip.helpRequested() }
        }
    }
}
