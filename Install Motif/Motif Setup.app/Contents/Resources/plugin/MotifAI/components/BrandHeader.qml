// The wordmark and tagline that open the panel.
import QtQuick 2.9

import "../js/theme.js" as T

Item {
    id: header
    implicitHeight: column.implicitHeight

    Column {
        id: column
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 9

        Wordmark {
            markWidth: Math.max(120, Math.min(190, header.width * 0.64))
            anchors.horizontalCenter: parent.horizontalCenter
        }

        Text {
            text: "Your AI composing partner"
            color: T.textMuted
            font.family: T.sans
            font.pixelSize: T.fsSmall
            font.letterSpacing: 0.2
            anchors.horizontalCenter: parent.horizontalCenter
        }
    }
}
