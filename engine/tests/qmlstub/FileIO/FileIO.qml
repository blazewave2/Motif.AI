import QtQuick 2.15
QtObject {
    property string source
    function homePath() { return stubHome; }
    function tempPath() { return "/tmp"; }
    function read() { return stubFiles.read(source); }
    function remove() { return true; }
}
