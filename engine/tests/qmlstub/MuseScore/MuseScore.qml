import QtQuick 2.15
// Only what MuseScore 3 and MuseScore 4 both provide: MuseScore 3 refuses a
// plugin that sets any property it lacks (title, thumbnailName and
// categoryCode are MuseScore 4 only), so the stub refuses them too.
Item {
    property string menuPath
    property string description
    property string version
    property string pluginType
    property string dockArea
    property bool requiresScore
    property var curScore: null
    property var openedPaths: []
    signal run()
    function readScore(path) { openedPaths.push(path); return { path: path }; }
    function setScore(s) {}
    function writeScore(s, path, ext) { return false; }
}
