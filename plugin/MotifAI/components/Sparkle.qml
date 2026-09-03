// The four-pointed star from the Motif.ai wordmark, drawn rather than shipped
// as a bitmap so it stays crisp at any panel scale.
import QtQuick 2.15

Canvas {
    id: star
    property color color: "#D8C48F"
    property real waist: 0.30        // 0 = needle-thin points, 0.5 = diamond
    antialiasing: true
    onColorChanged: requestPaint()
    onWaistChanged: requestPaint()

    onPaint: {
        var ctx = getContext("2d");
        ctx.reset();
        var w = width, h = height, cx = w / 2, cy = h / 2;
        var kx = cx * waist, ky = cy * waist;
        ctx.beginPath();
        ctx.moveTo(cx, 0);
        ctx.quadraticCurveTo(cx + kx, cy - ky, w, cy);
        ctx.quadraticCurveTo(cx + kx, cy + ky, cx, h);
        ctx.quadraticCurveTo(cx - kx, cy + ky, 0, cy);
        ctx.quadraticCurveTo(cx - kx, cy - ky, cx, 0);
        ctx.closePath();
        ctx.fillStyle = star.color;
        ctx.fill();
    }
}
