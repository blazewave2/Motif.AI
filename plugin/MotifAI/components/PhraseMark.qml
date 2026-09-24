// A phrase mark — the curve from the wordmark — used as Motif's own mark
// wherever a small brand accent is needed, and animated while it composes.
import QtQuick 2.9

import "../js/theme.js" as T

Canvas {
    id: curve
    property color color: T.gold
    property real progress: 1.0      // 0..1, how much of the curve is drawn
    property real weight: 1.6

    antialiasing: true
    onColorChanged: requestPaint()
    onProgressChanged: requestPaint()

    onPaint: {
        var ctx = getContext("2d");
        ctx.reset();
        var w = width, h = height;
        if (w <= 0 || h <= 0)
            return;
        ctx.lineCap = "round";
        ctx.strokeStyle = curve.color;
        ctx.lineWidth = curve.weight;
        // A shallow arc that mirrors the swash beneath the wordmark.
        var steps = 48;
        var last = Math.max(1, Math.round(steps * Math.max(0, Math.min(1, curve.progress))));
        ctx.beginPath();
        for (var i = 0; i <= last; ++i) {
            var t = i / steps;
            var x = t * w;
            // Quadratic dip, deepest slightly left of centre as in the artwork.
            var y = h * 0.18 + Math.pow(Math.abs(t - 0.46) * 2.0, 1.9) * h * -0.0 +
                    (1 - Math.pow((t - 0.46) / 0.54, 2)) * h * 0.62;
            if (i === 0)
                ctx.moveTo(x, y);
            else
                ctx.lineTo(x, y);
        }
        ctx.stroke();
    }
}
