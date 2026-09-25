pragma Singleton
import QtQuick 2.15
// The element type numbers a plugin compares against (MuseScore 3's values).
QtObject {
    enum Kind { REST = 25, DYNAMIC = 32, TEMPO_TEXT = 41, CHORD = 93 }
}
