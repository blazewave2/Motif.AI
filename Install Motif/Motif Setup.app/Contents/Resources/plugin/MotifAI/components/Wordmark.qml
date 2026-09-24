// The Motif.AI wordmark, drawn from the supplied artwork.
import QtQuick 2.9

Image {
    id: mark
    property real markWidth: 168

    // The artwork's own proportion, kept as a constant rather than read from
    // sourceSize: assigning sourceSize.width makes sourceSize report the
    // *requested* size, whose height is zero, collapsing this item to nothing.
    readonly property real aspect: 0.30667

    width: markWidth
    height: Math.round(markWidth * aspect)

    source: Qt.resolvedUrl("../assets/wordmark.png")
    fillMode: Image.PreserveAspectFit
    smooth: true
    antialiasing: true
    // Decode at the size we draw, doubled so it stays crisp on dense displays.
    sourceSize.width: Math.round(markWidth * 2)
}
