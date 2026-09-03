// Server address, token and style override.  Everything the panel needs to
// talk to the engine is visible and editable here.
import QtQuick 2.15

import "../js/theme.js" as T

Item {
    id: panel
    property string serverUrl: ""
    property string token: ""
    property string styleOverride: ""
    property string ensembleOverride: ""
    property string engineInfo: ""
    property string configPath: ""
    signal saved(string url, string tok, string styleId, string ensembleId)
    signal closed()

    implicitHeight: col.implicitHeight

    Column {
        id: col
        width: parent.width
        spacing: 12

        Row {
            width: parent.width
            Text {
                text: "Settings"
                color: T.text
                font.family: T.serif
                font.pixelSize: 18
                width: parent.width - back.width
            }
            SmallButton {
                id: back
                label: "Done"
                onClicked: {
                    panel.saved(urlField.value, tokenField.value,
                                styleField.value, ensembleField.value);
                    panel.closed();
                }
            }
        }

        Field {
            id: urlField
            width: parent.width
            label: "Engine address"
            value: panel.serverUrl
            hint: "Where the local Motif service is listening."
        }
        Field {
            id: tokenField
            width: parent.width
            label: "API token"
            value: panel.token
            hint: panel.configPath.length
                  ? "Read automatically from " + panel.configPath
                  : "Found in ~/.motif/config.json"
        }
        Field {
            id: styleField
            width: parent.width
            label: "Force a style (optional)"
            value: panel.styleOverride
            hint: "e.g. chopin, rachmaninoff, bach. Leave empty to infer it."
        }
        Field {
            id: ensembleField
            width: parent.width
            label: "Force an ensemble (optional)"
            value: panel.ensembleOverride
            hint: "e.g. solo_piano, piano_concerto, string_quartet."
        }

        Rectangle {
            width: parent.width
            height: info.implicitHeight + 16
            radius: T.radiusSm
            color: T.surface
            border.width: 1
            border.color: T.border
            visible: panel.engineInfo.length > 0
            Text {
                id: info
                anchors { fill: parent; margins: 8 }
                text: panel.engineInfo
                color: T.textMuted
                font.family: T.mono
                font.pixelSize: T.fsTiny
                wrapMode: Text.WordWrap
            }
        }
    }
}
