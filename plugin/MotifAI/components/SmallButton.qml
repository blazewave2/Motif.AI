import QtQuick 2.15

Rectangle {
    id: btn
    property var theme
    property string label: ""
    property bool primary: false
    property bool enabled: true
    signal clicked()

    implicitWidth: t.implicitWidth + 20
    implicitHeight: 26
    radius: theme.radiusSm
    opacity: enabled ? 1 : 0.45
    color: !enabled ? theme.surface
         : primary ? (area.containsMouse ? Qt.lighter(theme.gold, 1.08) : theme.gold)
         : (area.containsMouse ? theme.surfaceHover : theme.surface)
    border.width: 1
    border.color: primary ? "transparent"
                : (area.containsMouse ? theme.borderStrong : theme.border)
    Behavior on color { ColorAnimation { duration: theme.durFast } }

    Text {
        id: t
        anchors.centerIn: parent
        text: btn.label
        color: btn.primary ? theme.textInverse : theme.text
        font.family: theme.sans
        font.pixelSize: theme.fsTiny
        font.weight: btn.primary ? Font.DemiBold : Font.Normal
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        enabled: btn.enabled
        cursorShape: btn.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: btn.clicked()
    }
}
