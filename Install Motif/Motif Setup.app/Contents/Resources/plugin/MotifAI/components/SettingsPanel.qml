// Preferences. There is deliberately very little here.
//
// Neither the composer nor the instrumentation is chosen from a list: both
// come straight out of what you type — "in the style of Chopin", "for a
// string quartet", "continue in the same style" — because a picker can only
// ever offer a fixed set of choices, and asking is always more flexible than
// choosing from a menu that will always be missing something.
//
// What *is* here is how much care the composer takes.
import QtQuick 2.9

import "../js/theme.js" as T

Item {
    id: panel
    property bool autoOpen: true
    property string versionText: ""
    property bool connected: false
    property string quality: "best"

    // What was just chosen, for the handlers in MotifAI.qml to read:
    // MuseScore 3 runs on a Qt too old to pass a signal's value to a handler
    // by name, so the signals below carry it only for newer ones.
    property alias pickedQuality: qualityChoice.picked

    signal changed(bool openAutomatically)
    signal closed()
    signal qualityChosen(string value)

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

        // -- the composer ------------------------------------------------
        Column {
            width: parent.width
            spacing: 12

            ChoiceRow {
                id: qualityChoice
                width: parent.width
                label: "Care"
                value: panel.quality
                options: [
                    { value: "maximum", title: "Maximum",
                      hint: "Tries the most ideas and revises the longest. The finest music; "
                            + "a long piece can take several minutes." },
                    { value: "best", title: "Best",
                      hint: "Weighs many themes, harmonisations and textures, keeps the "
                            + "strongest, and reviews what it wrote. The default." },
                    { value: "balanced", title: "Balanced",
                      hint: "Fewer ideas tried, one review. Noticeably quicker." },
                    { value: "sketch", title: "Quick sketch",
                      hint: "Takes the first good idea, for trying things out." }
                ]
                onChosen: panel.qualityChosen(qualityChoice.picked)
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                color: T.textFaint
                font.family: T.sans
                font.pixelSize: T.fsTiny
                lineHeight: 1.3
                text: "Motif's composer runs entirely on this computer. Nothing you ask "
                      + "for, and no score you have open, is ever sent anywhere."
            }
        }

        Rectangle { width: parent.width; height: 1; color: T.border }

        Toggle {
            id: autoOpenToggle
            width: parent.width
            label: "Open new scores automatically"
            hint: "Turn this off to keep the score in the panel until you ask for it."
            checked: panel.autoOpen
            onToggled: {
                panel.autoOpen = autoOpenToggle.checked;
                panel.changed(autoOpenToggle.checked);
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
