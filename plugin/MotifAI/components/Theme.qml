// Motif.ai design tokens.  One place for every colour, radius and easing so the
// panel reads as a single designed surface rather than assembled controls.
import QtQuick 2.15

QtObject {
    id: theme

    // -- surfaces ---------------------------------------------------------
    readonly property color bg:            "#16181C"
    readonly property color bgElevated:    "#1C1F24"
    readonly property color surface:       "#22262C"
    readonly property color surfaceHover:  "#2A2F36"
    readonly property color surfaceActive: "#32383F"
    readonly property color inputBg:       "#1A1D22"

    // -- lines ------------------------------------------------------------
    readonly property color border:        "#2E333A"
    readonly property color borderStrong:  "#3D444D"
    readonly property color borderFocus:   "#6E7B8F"

    // -- text -------------------------------------------------------------
    readonly property color text:          "#F2F4F7"
    readonly property color textMuted:     "#A7AFBC"
    readonly property color textFaint:     "#6C7583"
    readonly property color textInverse:   "#12141A"

    // -- accents ----------------------------------------------------------
    readonly property color accent:        "#D8C48F"
    readonly property color gold:          "#D8C48F"
    readonly property color goldDim:       "#9C8B5E"
    readonly property color danger:        "#E0776B"
    readonly property color success:       "#7FBF8A"
    readonly property color info:          "#7FA8D9"

    // -- metrics ----------------------------------------------------------
    readonly property int radiusSm: 6
    readonly property int radiusMd: 10
    readonly property int radiusLg: 14
    readonly property int pad: 16
    readonly property int gap: 10

    readonly property int durFast: 120
    readonly property int durBase: 200
    readonly property int durSlow: 340

    // -- type -------------------------------------------------------------
    readonly property string serif: pickFont([
        "Edwin", "Georgia", "Palatino Linotype", "Book Antiqua", "Palatino",
        "Times New Roman", "Cambria", "Charter", "DejaVu Serif", "serif"])
    readonly property string sans: pickFont([
        "Inter", "Segoe UI Variable Text", "Segoe UI", "SF Pro Text",
        "Helvetica Neue", "Ubuntu", "Noto Sans", "DejaVu Sans", "sans-serif"])
    readonly property string mono: pickFont([
        "JetBrains Mono", "Cascadia Code", "Consolas", "SF Mono", "Menlo",
        "DejaVu Sans Mono", "monospace"])

    readonly property int fsDisplay: 30
    readonly property int fsTitle: 15
    readonly property int fsBody: 13
    readonly property int fsSmall: 12
    readonly property int fsTiny: 11

    // Pick the first family the host actually has, so the panel looks the
    // same on Windows, macOS and Linux instead of falling back to a default.
    function pickFont(candidates) {
        var available = Qt.fontFamilies();
        for (var i = 0; i < candidates.length; ++i) {
            if (available.indexOf(candidates[i]) !== -1)
                return candidates[i];
        }
        return candidates[candidates.length - 1];
    }
}
