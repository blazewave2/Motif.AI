// Preferences. Everything here is a musical choice; nothing technical is
// exposed, because nothing technical is ever the musician's problem.
//
// There is no composer picker: Motif reads the composer straight out of what
// you type — "in the style of Chopin", "a Bach fugue" — so asking is always
// faster than choosing from a list, and it never goes stale as styles are
// added.
import QtQuick 2.15

import "../js/theme.js" as T

Item {
    id: panel
    property var ensembleOptions: []
    property string ensembleOverride: ""
    property bool autoOpen: true
    property string versionText: ""
    property bool connected: false
    signal changed(string ensembleId, bool openAutomatically)
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

        Picker {
            id: ensemblePicker
            width: parent.width
            label: "Instruments"
            placeholder: "Let Motif choose"
            options: panel.ensembleOptions
            value: panel.ensembleOverride
            onPicked: function (id) {
                panel.ensembleOverride = id;
                panel.changed(id, panel.autoOpen);
            }
        }

        Rectangle { width: parent.width; height: 1; color: T.border }

        Toggle {
            width: parent.width
            label: "Open new scores automatically"
            hint: "Turn this off to keep the score in the panel until you ask for it."
            checked: panel.autoOpen
            onToggled: function (v) {
                panel.autoOpen = v;
                panel.changed(panel.ensembleOverride, v);
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
