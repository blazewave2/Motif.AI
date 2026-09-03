.pragma library

// Motif.ai design tokens.
//
// A JS library rather than a QML object: library values exist before the first
// binding pass, so no component can ever read a half-constructed theme, and
// nothing has to be threaded down through every nested item.

// -- surfaces ---------------------------------------------------------------
var bg            = "#16181C";
var bgElevated    = "#1C1F24";
var surface       = "#22262C";
var surfaceHover  = "#2A2F36";
var surfaceActive = "#32383F";
var inputBg       = "#1A1D22";

// -- lines ------------------------------------------------------------------
var border        = "#2E333A";
var borderStrong  = "#3D444D";
var borderFocus   = "#6E7B8F";

// -- text -------------------------------------------------------------------
var text          = "#F2F4F7";
var textMuted     = "#A7AFBC";
var textFaint     = "#6C7583";
var textInverse   = "#12141A";

// -- accents ----------------------------------------------------------------
var gold          = "#D8C48F";
var goldDim       = "#9C8B5E";
var danger        = "#E0776B";
var dangerWash    = "#241A1A";
var success       = "#7FBF8A";

// -- metrics ----------------------------------------------------------------
var radiusSm = 6;
var radiusMd = 10;
var radiusLg = 14;
var pad = 16;
var gap = 10;

var durFast = 120;
var durBase = 200;
var durSlow = 340;

// -- type -------------------------------------------------------------------
function pickFont(candidates) {
    var available = Qt.fontFamilies();
    for (var i = 0; i < candidates.length; ++i) {
        if (available.indexOf(candidates[i]) !== -1)
            return candidates[i];
    }
    return candidates[candidates.length - 1];
}

var serif = pickFont(["Edwin", "Georgia", "Palatino Linotype", "Book Antiqua",
                      "Palatino", "Cambria", "Charter", "Times New Roman",
                      "DejaVu Serif", "serif"]);
var sans  = pickFont(["Inter", "Segoe UI Variable Text", "Segoe UI", "SF Pro Text",
                      "Helvetica Neue", "Ubuntu", "Noto Sans", "DejaVu Sans",
                      "sans-serif"]);
var mono  = pickFont(["JetBrains Mono", "Cascadia Code", "Consolas", "SF Mono",
                      "Menlo", "DejaVu Sans Mono", "monospace"]);

var fsDisplay = 30;
var fsTitle   = 15;
var fsBody    = 13;
var fsSmall   = 12;
var fsTiny    = 11;
