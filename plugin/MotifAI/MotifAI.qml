//=============================================================================
//  Motif.AI — a generative, agentic composing partner for MuseScore
//
//  The panel talks to a local Motif engine over HTTP on the loopback
//  interface.  Generated music arrives as MusicXML, which MuseScore imports
//  with far higher fidelity than a plugin can achieve through the cursor API:
//  slurs, pedalling, hairpins, tuplets and multi-voice piano writing all
//  survive intact.
//=============================================================================
import QtQuick 2.15
import QtQuick.Layouts 1.15
import MuseScore 3.0
import FileIO 3.0

import "components"
import "js/api.js" as Api
import "js/theme.js" as T

MuseScore {
    id: root

    title: "Motif.AI"
    description: "Your AI composing partner — describe a piece and Motif writes it."
    version: "1.0.0"
    pluginType: "dock"
    dockArea: "left"
    requiresScore: false
    thumbnailName: "assets/thumbnail.png"

    implicitWidth: 330
    implicitHeight: 900
    width: implicitWidth
    height: implicitHeight

    // -- state ------------------------------------------------------------
    property string serverUrl: "http://127.0.0.1:8765"
    property string apiToken: ""
    property string styleOverride: ""
    property string ensembleOverride: ""
    property string connState: "checking"      // checking | ready | offline | error
    property string connDetail: ""
    property string engineInfo: ""
    property bool busy: false
    property int view: 0                       // 0 create, 1 chat
    property bool settingsOpen: false
    property string lastPrompt: ""
    property string pendingXmlPath: ""
    property int seedCounter: 0

    ListModel { id: conversation }

    FileIO { id: configFile }
    FileIO { id: scoreOut }
    FileIO { id: scoreIn }

    readonly property var examples: [
        { l1: "Compose a romantic piano piece",  l2: "in the style of Chopin",
          prompt: "Compose a romantic piano piece in the style of Chopin" },
        { l1: "Create a joyful and uplifting melody", l2: "in 6/8 time",
          prompt: "Create a joyful and uplifting melody in 6/8 time" },
        { l1: "Write a short film score",        l2: "for a mysterious forest scene",
          prompt: "Write a short film score for a mysterious forest scene" },
        { l1: "Continue this piece",             l2: "in a more dramatic way",
          prompt: "Continue this piece in a more dramatic way" },
        { l1: "Add a contrasting middle section", l2: "in a minor key",
          prompt: "Add a contrasting middle section in a minor key" }
    ]

    //=========================================================================
    //  Lifecycle
    //=========================================================================
    onRun: {
        loadConfig();
        checkHealth();
    }
    Component.onCompleted: {
        loadConfig();
        checkHealth();
    }

    function configDir() {
        var home = "";
        try { home = configFile.homePath(); } catch (e) { home = ""; }
        if (!home || home.length === 0)
            return "";
        return home + "/.motif";
    }

    // The engine writes its port and token to ~/.motif/config.json on first
    // run, so the panel configures itself with nothing for the user to copy.
    function loadConfig() {
        var dir = configDir();
        if (dir.length === 0)
            return;
        configFile.source = dir + "/config.json";
        var raw = "";
        try { raw = configFile.read(); } catch (e) { raw = ""; }
        if (!raw || raw.length === 0)
            return;
        var tok = Api.tokenFromConfig(raw);
        var port = Api.portFromConfig(raw, 8765);
        if (tok.length > 0)
            root.apiToken = tok;
        root.serverUrl = "http://127.0.0.1:" + port;
    }

    function checkHealth() {
        root.connState = "checking";
        Api.health(root.serverUrl, root.apiToken, function (res) {
            if (!res || res.ok !== true) {
                root.connState = res && res.offline ? "offline" : "error";
                root.connDetail = (res && res.error)
                    ? res.error : "The Motif engine did not respond.";
                root.engineInfo = "";
                return;
            }
            root.connState = "ready";
            root.connDetail = "";
            root.engineInfo = "Motif engine " + res.version
                + "\nmode: " + res.engine
                + "\nplanner: " + res.planner
                + (res.model_error ? "\nmodel: " + res.model_error : "");
        });
    }

    //=========================================================================
    //  Composing
    //=========================================================================
    function nextSeed() {
        root.seedCounter += 1;
        return Math.floor(Math.random() * 1000000) + root.seedCounter;
    }

    // Export whatever is open so the engine can answer questions about it.
    function currentScoreXml() {
        if (typeof curScore === "undefined" || curScore === null)
            return "";
        var path = "";
        try {
            path = scoreOut.tempPath() + "/motif-context-" + Date.now() + ".musicxml";
            var wrote = writeScore(curScore, path, "musicxml");
            if (wrote === false)
                return "";
            scoreIn.source = path;
            var text = scoreIn.read();
            scoreIn.remove();
            return text || "";
        } catch (e) {
            return "";
        }
    }

    function send(promptText, isRetry) {
        if (root.busy || promptText.trim().length === 0)
            return;
        root.lastPrompt = promptText;
        root.busy = true;
        root.view = 1;
        if (!isRetry)
            appendMessage("user", promptText, "", false);
        appendMessage("pending", "Composing…", "", false);

        var payload = {
            prompt: promptText,
            seed: nextSeed(),
            score_xml: currentScoreXml()
        };
        if (root.styleOverride.length > 0) payload.style = root.styleOverride;
        if (root.ensembleOverride.length > 0) payload.ensemble = root.ensembleOverride;

        Api.compose(root.serverUrl, root.apiToken, payload, function (res) {
            root.busy = false;
            removePending();
            if (!res || res.ok !== true) {
                var msg = (res && res.error) ? res.error
                                             : "Motif could not complete that request.";
                if (res && res.offline) {
                    root.connState = "offline";
                    msg = "The Motif engine is not running. Start it with "
                        + "<b>motif serve</b> and try again.";
                }
                appendMessage("error", msg, "", false);
                return;
            }
            root.connState = "ready";
            var detail = planSummary(res.plan);
            appendMessage("assistant", res.message || "Done.", detail,
                          !!res.musicxml_path);
            conversation.setProperty(conversation.count - 1, "xmlPath",
                                     res.musicxml_path || "");
            if (res.musicxml_path && res.musicxml_path.length > 0) {
                root.pendingXmlPath = res.musicxml_path;
                openScore(res.musicxml_path);
            }
        });
    }

    function planSummary(plan) {
        if (!plan)
            return "";
        var lines = [];
        lines.push("style     " + plan.style);
        lines.push("key       " + plan.key);
        lines.push("metre     " + plan.time[0] + "/" + plan.time[1]);
        lines.push("tempo     " + plan.tempo + (plan.tempo_text ? "  " + plan.tempo_text : ""));
        lines.push("form      " + plan.form);
        lines.push("forces    " + plan.ensemble);
        lines.push("seed      " + plan.seed);
        var secs = [];
        for (var i = 0; i < plan.sections.length; ++i) {
            var s = plan.sections[i];
            secs.push(s.label + " " + s.bars + "b " + s.key
                      + " [" + s.texture_lh + "]");
        }
        lines.push("");
        lines.push(secs.join("\n"));
        return lines.join("\n");
    }

    // MuseScore opens the generated MusicXML in a new tab.  If the host build
    // does not expose readScore to plugins we say where the file is instead of
    // failing silently.
    function openScore(path) {
        var opened = false;
        try {
            var s = readScore(path);
            if (s) {
                opened = true;
                try { setScore(s); } catch (e2) { /* older hosts open it directly */ }
            }
        } catch (e) {
            opened = false;
        }
        if (!opened) {
            appendMessage("system",
                "The score is saved at <b>" + path + "</b>. "
                + "Open it with File ▸ Open if it did not appear automatically.",
                "", false);
        }
    }

    function appendMessage(role, text, detail, hasScore) {
        conversation.append({ role: role, text: text, detail: detail || "",
                              hasScore: !!hasScore, xmlPath: "" });
    }

    function removePending() {
        for (var i = conversation.count - 1; i >= 0; --i) {
            if (conversation.get(i).role === "pending") {
                conversation.remove(i);
                return;
            }
        }
    }

    function newChat() {
        conversation.clear();
        root.view = 0;
        root.lastPrompt = "";
        promptBox.clear();
    }

    //=========================================================================
    //  Layout
    //=========================================================================
    Rectangle {
        anchors.fill: parent
        color: T.bg

        // ---- settings ---------------------------------------------------
        Flickable {
            anchors { fill: parent; margins: T.pad }
            visible: root.settingsOpen
            contentHeight: settings.implicitHeight
            clip: true
            SettingsPanel {
                id: settings
                width: parent.width
                serverUrl: root.serverUrl
                token: root.apiToken
                styleOverride: root.styleOverride
                ensembleOverride: root.ensembleOverride
                engineInfo: root.engineInfo
                configPath: root.configDir() + "/config.json"
                onSaved: function (url, tok, styleId, ensembleId) {
                    root.serverUrl = url;
                    root.apiToken = tok;
                    root.styleOverride = styleId;
                    root.ensembleOverride = ensembleId;
                    root.checkHealth();
                }
                onClosed: root.settingsOpen = false
            }
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 0
            visible: !root.settingsOpen

            // ---- scrolling body -----------------------------------------
            Flickable {
                id: scroller
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentHeight: body.implicitHeight + T.pad * 2
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                Column {
                    id: body
                    x: T.pad
                    y: T.pad
                    width: scroller.width - T.pad * 2
                    spacing: 16

                    // -- landing ------------------------------------------
                    BrandHeader {
                        width: parent.width
                        visible: root.view === 0
                    }

                    StatusStrip {
                        width: parent.width
                        status: root.connState
                        detail: root.connDetail
                        onRetryRequested: root.checkHealth()
                        onHelpRequested: root.showStartHelp()
                    }

                    Text {
                        width: parent.width
                        text: "What are we composing today?"
                        color: T.text
                        font.family: T.sans
                        font.pixelSize: T.fsTitle
                        visible: root.view === 0
                    }

                    PromptBox {
                        id: promptBox
                        width: parent.width
                        busy: root.busy
                        interactive: !root.busy
                        visible: root.view === 0
                        onSubmitted: function (value) { root.send(value, false); }
                    }

                    Text {
                        text: "Try these examples"
                        color: T.textMuted
                        font.family: T.sans
                        font.pixelSize: T.fsSmall
                        visible: root.view === 0
                    }

                    Column {
                        id: exampleColumn
                        width: body.width
                        spacing: T.gap
                        visible: root.view === 0
                        Repeater {
                            model: root.examples
                            delegate: ExampleCard {
                                width: exampleColumn.width
                                line1: modelData.l1
                                line2: modelData.l2
                                onActivated: root.send(modelData.prompt, false)
                            }
                        }
                    }

                    // -- conversation -------------------------------------
                    Column {
                        id: chatColumn
                        width: body.width
                        spacing: T.gap
                        visible: root.view === 1

                        Repeater {
                            model: conversation
                            delegate: Loader {
                                width: chatColumn.width
                                sourceComponent: model.role === "pending"
                                                 ? pendingRow : bubbleComponent

                                property string mRole: model.role
                                property string mText: model.text
                                property string mDetail: model.detail
                                property bool mHasScore: model.hasScore
                                property string mPath: model.xmlPath

                                Component {
                                    id: bubbleComponent
                                    MessageBubble {
                                        role: mRole
                                        text: mText
                                        detail: mDetail
                                        hasScore: mHasScore
                                        showActions: true
                                        onOpenRequested: root.openScore(mPath)
                                        onRegenerateRequested: root.send(root.lastPrompt, true)
                                    }
                                }
                                Component {
                                    id: pendingRow
                                    Row {
                                        spacing: 8
                                        Sparkle {
                                            width: 11; height: 11
                                            color: T.gold
                                            anchors.verticalCenter: parent.verticalCenter
                                            RotationAnimator on rotation {
                                                from: 0; to: 360
                                                duration: 2600
                                                loops: Animation.Infinite
                                                running: root.busy
                                            }
                                        }
                                        Text {
                                            text: "Composing…"
                                            color: T.textMuted
                                            font.family: T.sans
                                            font.pixelSize: T.fsBody
                                            anchors.verticalCenter: parent.verticalCenter
                                            SequentialAnimation on opacity {
                                                loops: Animation.Infinite
                                                running: root.busy
                                                NumberAnimation { to: 0.45; duration: 700 }
                                                NumberAnimation { to: 1.0;  duration: 700 }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                onContentHeightChanged: {
                    if (root.view === 1)
                        contentY = Math.max(0, contentHeight - height);
                }
            }

            // ---- follow-up composer (chat view) --------------------------
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: followUp.implicitHeight + T.pad
                color: T.bg
                visible: root.view === 1
                Rectangle {
                    anchors { left: parent.left; right: parent.right; top: parent.top }
                    height: 1
                    color: T.border
                }
                PromptBox {
                    id: followUp
                    anchors {
                        left: parent.left; right: parent.right; top: parent.top
                        leftMargin: T.pad; rightMargin: T.pad
                        topMargin: T.pad * 0.6
                    }
                    placeholder: "Ask for a change, or something new…"
                    busy: root.busy
                    interactive: !root.busy
                    onSubmitted: function (value) { root.send(value, false); followUp.clear(); }
                }
            }

            // ---- new chat ------------------------------------------------
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 46

                Rectangle {
                    anchors { left: parent.left; right: parent.right; top: parent.top }
                    anchors.leftMargin: T.pad
                    anchors.rightMargin: T.pad
                    height: 1
                    color: T.border
                }
                Row {
                    anchors.centerIn: parent
                    spacing: 7
                    Sparkle {
                        width: 11; height: 11
                        color: T.gold
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: "New chat"
                        color: newChatArea.containsMouse ? T.text : T.textMuted
                        font.family: T.sans
                        font.pixelSize: T.fsBody
                        anchors.verticalCenter: parent.verticalCenter
                        Behavior on color { ColorAnimation { duration: T.durFast } }
                    }
                }
                MouseArea {
                    id: newChatArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.newChat()
                }
            }

            TabBar {
                id: tabs
                Layout.fillWidth: true
                currentIndex: root.view
                onCurrentIndexChanged: root.view = currentIndex
            }
        }

        // ---- settings affordance ----------------------------------------
        Rectangle {
            anchors { top: parent.top; right: parent.right; margins: 8 }
            width: 26; height: 26
            radius: T.radiusSm
            color: gearArea.containsMouse ? T.surface : "transparent"
            visible: !root.settingsOpen
            Text {
                anchors.centerIn: parent
                text: "⚙"
                color: gearArea.containsMouse ? T.text : T.textFaint
                font.pixelSize: 14
            }
            MouseArea {
                id: gearArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.settingsOpen = true
            }
        }
    }

    function showStartHelp() {
        appendMessage("system",
            "Start the engine from a terminal:<br><br>"
            + "<b>python3 -m motif serve</b><br><br>"
            + "It listens on 127.0.0.1 only and writes its port and token to "
            + "<b>~/.motif/config.json</b>, which this panel reads automatically. "
            + "Then press Retry.", "", false);
        root.view = 1;
    }
}
