// A menu-style picker: closed it reads as a single choice, open it lists them.
import QtQuick 2.15

import "../js/theme.js" as T

Item {
    id: picker
    property string label: ""
    property var options: []          // [{ id, name }]
    property string value: ""
    property string placeholder: "Let Motif choose"
    property bool open: false
    signal picked(string id)

    implicitHeight: col.implicitHeight
    z: open ? 50 : 1

    function displayName() {
        for (var i = 0; i < options.length; ++i)
            if (options[i].id === picker.value)
                return options[i].name;
        return picker.placeholder;
    }

    Column {
        id: col
        width: parent.width
        spacing: 6

        Text {
            text: picker.label
            color: T.textMuted
            font.family: T.sans
            font.pixelSize: T.fsTiny
            visible: picker.label.length > 0
        }

        Rectangle {
            id: field
            width: parent.width
            height: 34
            radius: T.radiusSm
            color: area.containsMouse || picker.open ? T.surfaceHover : T.surface
            border.width: 1
            border.color: picker.open ? T.borderFocus : T.border
            Behavior on color { ColorAnimation { duration: T.durFast } }

            Text {
                anchors { left: parent.left; leftMargin: 11; right: chev.left
                          verticalCenter: parent.verticalCenter }
                text: picker.displayName()
                color: picker.value.length ? T.text : T.textFaint
                font.family: T.sans
                font.pixelSize: T.fsSmall
                elide: Text.ElideRight
            }
            Text {
                id: chev
                anchors { right: parent.right; rightMargin: 11
                          verticalCenter: parent.verticalCenter }
                text: picker.open ? "⌃" : "⌄"
                color: T.textFaint
                font.pixelSize: 12
            }
            MouseArea {
                id: area
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: picker.open = !picker.open
            }
        }

        Rectangle {
            width: parent.width
            visible: picker.open
            height: visible ? Math.min(232, list.contentHeight + 8) : 0
            radius: T.radiusSm
            color: T.bgElevated
            border.width: 1
            border.color: T.border
            clip: true

            ListView {
                id: list
                anchors { fill: parent; margins: 4 }
                model: picker.options
                boundsBehavior: Flickable.StopAtBounds
                delegate: Rectangle {
                    width: list.width
                    height: 30
                    radius: T.radiusSm - 2
                    color: rowArea.containsMouse ? T.surfaceHover : "transparent"
                    Text {
                        anchors { left: parent.left; leftMargin: 8
                                  verticalCenter: parent.verticalCenter
                                  right: tick.left }
                        text: modelData.name
                        color: T.text
                        font.family: T.sans
                        font.pixelSize: T.fsSmall
                        elide: Text.ElideRight
                    }
                    Text {
                        id: tick
                        anchors { right: parent.right; rightMargin: 8
                                  verticalCenter: parent.verticalCenter }
                        text: "✓"
                        visible: modelData.id === picker.value
                        color: T.gold
                        font.pixelSize: 12
                    }
                    MouseArea {
                        id: rowArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            picker.value = modelData.id;
                            picker.open = false;
                            picker.picked(modelData.id);
                        }
                    }
                }
            }
        }
    }
}
