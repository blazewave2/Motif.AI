// Preferences. There is deliberately very little here.
//
// Neither the composer nor the instrumentation is chosen from a list: both
// come straight out of what you type — "in the style of Chopin", "for a
// string quartet", "continue in the same style" — because a picker can only
// ever offer a fixed set of choices, and asking is always more flexible than
// choosing from a menu that will always be missing something.
import QtQuick 2.15

import "../js/theme.js" as T

Item {
    id: panel
    property bool autoOpen: true
    property string versionText: ""
    property bool connected: false
    signal changed(bool openAutomatically)
    signal closed()

    implicitHeight: col.implicitHeight

    Column {
        id: col
        width: parent.width
        spacing: 20

        Item {
            width: parent.width
            height: Math.max(title.implicitHeight, done.implicitHeight)
            Text {
                id: title
                text: "Preferences"
                color: T.text
                font.family: T.serif
                font.pixelSize: 19
                anchors.verticalCenter: parent.verticalCenter
            }
            SmallButton {
                id: done
                label: "Done"
                primary: true
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                onClicked: panel.closed()
            }
        }

        Toggle {
            width: parent.width
            label: "Open new scores automatically"
            hint: "Turn this off to keep the score in the panel until you ask for it."
            checked: panel.autoOpen
            onToggled: function (v) {
                panel.autoOpen = v;
                panel.changed(v);
            }
        }

        Rectangle { width: parent.width; height: 1; color: T.border }

        Column {
            width: parent.width
            spacing: 6
            Text {
                text: "Quick access"
                color: T.text
                font.family: T.sans
                font.pixelSize: T.fsSmall
                font.bold: true
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "MuseScore doesn't let a plugin add its own toolbar button, "
                      + "but you can give Motif a one-key shortcut instead: open "
                      + "Plugins → Manage Plugins, select Motif.AI, and choose "
                      + "Define Shortcut."
                color: T.textMuted
                font.family: T.sans
                font.pixelSize: T.fsSmall
            }
        }

        Rectangle { width: parent.width; height: 1; color: T.border }

        Column {
            width: parent.width
            spacing: 8
            Row {
                spacing: 8
                Rectangle {
                    width: 7; height: 7; radius: 4
                    color: panel.connected ? T.success : T.textFaint
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: panel.connected ? "Motif is ready" : "Motif is waking up"
                    color: T.textMuted
                    font.family: T.sans
                    font.pixelSize: T.fsSmall
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
            Text {
                text: panel.versionText
                color: T.textFaint
                font.family: T.sans
                font.pixelSize: T.fsTiny
                visible: panel.versionText.length > 0
            }
        }
    }
}
