// Server address, token and style override.  Everything the panel needs to
// talk to the engine is visible and editable here.
import QtQuick 2.15

Item {
    id: panel
    property var theme
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
                color: theme.text
                font.family: theme.serif
                font.pixelSize: 18
                width: parent.width - back.width
            }
            SmallButton {
                id: back
                theme: panel.theme
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
            theme: panel.theme
            width: parent.width
            label: "Engine address"
            value: panel.serverUrl
            hint: "Where the local Motif service is listening."
        }
        Field {
            id: tokenField
            theme: panel.theme
            width: parent.width
            label: "API token"
            value: panel.token
            hint: panel.configPath.length
                  ? "Read automatically from " + panel.configPath
                  : "Found in ~/.motif/config.json"
        }
        Field {
            id: styleField
            theme: panel.theme
            width: parent.width
            label: "Force a style (optional)"
            value: panel.styleOverride
            hint: "e.g. chopin, rachmaninoff, bach. Leave empty to infer it."
        }
        Field {
            id: ensembleField
            theme: panel.theme
            width: parent.width
            label: "Force an ensemble (optional)"
            value: panel.ensembleOverride
            hint: "e.g. solo_piano, piano_concerto, string_quartet."
        }

        Rectangle {
            width: parent.width
            height: info.implicitHeight + 16
            radius: theme.radiusSm
            color: theme.surface
            border.width: 1
            border.color: theme.border
            visible: panel.engineInfo.length > 0
            Text {
                id: info
                anchors { fill: parent; margins: 8 }
                text: panel.engineInfo
                color: theme.textMuted
                font.family: theme.mono
                font.pixelSize: theme.fsTiny
                wrapMode: Text.WordWrap
            }
        }
    }
}
