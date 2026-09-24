// A small set of choices shown side by side, one of them selected.
import QtQuick 2.9

import "../js/theme.js" as T

Column {
    id: row
    property string label: ""
    property var options: []            // [{ value, title, hint }]
    property string value: ""
    // The option just clicked, for handlers to read (see PromptBox).
    property string picked: ""
    signal chosen(string value)

    spacing: 7

    function hintFor(v) {
        for (var i = 0; i < options.length; ++i)
            if (options[i].value === v)
                return options[i].hint || "";
        return "";
    }

    Text {
        text: row.label
        color: T.text
        font.family: T.sans
        font.pixelSize: T.fsSmall
        visible: row.label.length > 0
    }

    Flow {
        width: row.width
        spacing: 6
        Repeater {
            model: row.options
            delegate: Rectangle {
                readonly property bool selected: modelData.value === row.value
                width: title.implicitWidth + 20
                height: 26
                radius: T.radiusSm
                color: selected ? Qt.rgba(0.85, 0.77, 0.56, 0.14)
                     : (area.containsMouse ? T.surfaceHover : T.surface)
                border.width: 1
                border.color: selected ? T.gold : T.border
                Behavior on color { ColorAnimation { duration: T.durFast } }
                Text {
                    id: title
                    anchors.centerIn: parent
                    text: modelData.title
                    color: selected ? T.gold : T.text
                    font.family: T.sans
                    font.pixelSize: T.fsTiny
                }
                MouseArea {
                    id: area
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: { row.picked = modelData.value; row.chosen(modelData.value); }
                }
            }
        }
    }

    Text {
        width: row.width
        text: row.hintFor(row.value)
        visible: text.length > 0
        color: T.textFaint
        font.family: T.sans
        font.pixelSize: T.fsTiny
        wrapMode: Text.WordWrap
    }
}
