//=============================================================================
//  Motif.AI — your AI composing partner, inside MuseScore
//
//  Music arrives as MusicXML, which MuseScore imports far more faithfully than
//  a plugin can build a score note by note: slurs, pedalling, hairpins,
//  tuplets and multi-voice piano writing all survive intact.
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

    implicitWidth: 340
    implicitHeight: 900
    width: implicitWidth
    height: implicitHeight

    // -- connection -------------------------------------------------------
    property string serverUrl: "http://127.0.0.1:8765"
    property string apiToken: ""
    property string connState: "checking"      // checking | ready | offline
    property string versionText: ""
    property int wakeAttempts: 0

    // -- preferences ------------------------------------------------------
    property string ensembleOverride: ""
    property bool autoOpen: true
    property var ensembleOptions: []

    // -- session ----------------------------------------------------------
    property bool busy: false
    property int view: 0                       // 0 create, 1 conversation
    property bool settingsOpen: false
    property string lastPrompt: ""
    property int seedCounter: 0

    ListModel { id: conversation }

    FileIO { id: configFile }
    FileIO { id: scoreOut }
    FileIO { id: scoreIn }

    readonly property var examples: [
        { l1: "Compose a romantic piano piece",   l2: "in the style of Chopin",
          prompt: "Compose a romantic piano piece in the style of Chopin" },
        { l1: "Create a joyful and uplifting melody", l2: "in 6/8 time",
          prompt: "Create a joyful and uplifting melody in 6/8 time" },
        { l1: "Write a short film score",         l2: "for a mysterious forest scene",
          prompt: "Write a short film score for a mysterious forest scene" },
        { l1: "Continue this piece",              l2: "in a more dramatic way",
          prompt: "Continue this piece in a more dramatic way" },
        { l1: "Add a contrasting middle section", l2: "in a minor key",
          prompt: "Add a contrasting middle section in a minor key" }
    ]

    //=========================================================================
    //  Lifecycle
    //=========================================================================
    onRun: start()
    Component.onCompleted: start()

    function start() {
        loadSettings();
        wakeAttempts = 0;
        checkHealth();
    }

    function motifFolder() {
        var home = "";
        try { home = configFile.homePath(); } catch (e) { home = ""; }
        return home && home.length ? home + "/.motif" : "";
    }

    // Motif writes where it is listening the first time it runs, so the panel
    // configures itself and the musician never sees an address or a key.
    function loadSettings() {
        var dir = motifFolder();
        if (!dir.length)
            return;
        configFile.source = dir + "/config.json";
        var raw = "";
        try { raw = configFile.read(); } catch (e) { raw = ""; }
        if (!raw || !raw.length)
            return;
        var tok = Api.tokenFromConfig(raw);
        if (tok.length)
            root.apiToken = tok;
        root.serverUrl = "http://127.0.0.1:" + Api.portFromConfig(raw, 8765);
        var prefs = Api.prefsFromConfig(raw);
        if (prefs) {
            root.ensembleOverride = prefs.ensemble || "";
            if (prefs.auto_open !== undefined)
                root.autoOpen = !!prefs.auto_open;
        }
    }

    function savePreferences() {
        Api.savePrefs(root.serverUrl, root.apiToken, {
            ensemble: root.ensembleOverride,
            auto_open: root.autoOpen
        }, function (res) { /* preferences are a convenience, never a blocker */ });
    }

    // Motif starts with the computer, so a failed first call usually means it
    // is still coming up. Retry quietly for a while before saying anything.
    Timer {
        id: wakeTimer
        interval: 1200
        repeat: false
        onTriggered: root.checkHealth()
    }

    function checkHealth() {
        if (root.connState !== "ready")
            root.connState = "checking";
        Api.health(root.serverUrl, root.apiToken, function (res) {
            if (res && res.ok === true) {
                root.connState = "ready";
                root.wakeAttempts = 0;
                root.versionText = "Version " + res.version;
                loadChoices();
                return;
            }
            root.wakeAttempts += 1;
            if (root.wakeAttempts < 8) {
                wakeTimer.interval = Math.min(4000, 700 * root.wakeAttempts);
                wakeTimer.restart();
            } else {
                root.connState = "offline";
            }
        });
    }

    function loadChoices() {
        if (root.ensembleOptions.length > 0)
            return;
        Api.choices(root.serverUrl, root.apiToken, function (res) {
            if (!res || res.ok !== true)
                return;
            var ens = [{ id: "", name: "Let Motif choose" }];
            for (var j = 0; j < res.ensembles.length; ++j)
                ens.push({ id: res.ensembles[j].id, name: res.ensembles[j].name });
            root.ensembleOptions = ens;
        });
    }

    //=========================================================================
    //  Composing
    //=========================================================================
    function nextSeed() {
        root.seedCounter += 1;
        return Math.floor(Math.random() * 1000000) + root.seedCounter;
    }

    // Hand Motif whatever is open, so it can answer questions about it and
    // carry on from it.
    function currentScoreXml() {
        if (typeof curScore === "undefined" || curScore === null)
            return "";
        try {
            var path = scoreOut.tempPath() + "/motif-context-" + Date.now() + ".musicxml";
            if (writeScore(curScore, path, "musicxml") === false)
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
        appendMessage("pending", "", "", false);

        // The composer is never a setting — it comes from what you type, the
        // same way you'd ask a person: "in the style of Chopin", "a Bach
        // fugue". Only the instrumentation preference can override the
        // prompt's own reading.
        var payload = { prompt: promptText, seed: nextSeed(),
                        score_xml: currentScoreXml() };
        if (root.ensembleOverride.length)
            payload.ensemble = root.ensembleOverride;

        Api.compose(root.serverUrl, root.apiToken, payload, function (res) {
            root.busy = false;
            removePending();
            if (!res || res.ok !== true) {
                if (res && res.offline) {
                    root.connState = "offline";
                    appendMessage("error",
                        "Motif isn’t answering just now. Give it a moment and try again.",
                        "", false);
                } else {
                    appendMessage("error",
                        (res && res.error) ? res.error
                                           : "Motif couldn’t finish that one. Try rewording it.",
                        "", false);
                }
                return;
            }
            root.connState = "ready";
            appendMessage("assistant", res.message || "Done.",
                          describe(res.plan), !!res.musicxml_path);
            conversation.setProperty(conversation.count - 1, "xmlPath",
                                     res.musicxml_path || "");
            if (root.autoOpen && res.musicxml_path && res.musicxml_path.length)
                openScore(res.musicxml_path);
        });
    }

    // A plain-language summary of the choices Motif made, shown on request.
    function describe(plan) {
        if (!plan)
            return "";
        var lines = [];
        lines.push("Key         " + plan.key);
        lines.push("Time        " + plan.time[0] + "/" + plan.time[1]);
        lines.push("Tempo       " + plan.tempo
                   + (plan.tempo_text ? "   " + plan.tempo_text : ""));
        lines.push("Form        " + prettify(plan.form));
        lines.push("Written for " + prettify(plan.ensemble));
        lines.push("");
        for (var i = 0; i < plan.sections.length; ++i) {
            var s = plan.sections[i];
            lines.push("  " + pad(s.label, 12) + pad(s.bars + " bars", 10) + s.key);
        }
        return lines.join("\n");
    }

    function prettify(id) {
        if (!id) return "";
        var t = id.replace(/_/g, " ");
        return t.charAt(0).toUpperCase() + t.slice(1);
    }

    function pad(text, n) {
        var s = String(text);
        while (s.length < n) s += " ";
        return s;
    }

    function openScore(path) {
        var opened = false;
        try {
            var s = readScore(path);
            if (s) {
                opened = true;
                try { setScore(s); } catch (e2) { /* some hosts open it directly */ }
            }
        } catch (e) {
            opened = false;
        }
        if (!opened)
            appendMessage("system",
                "Your score is saved in the Motif folder in your Documents. "
                + "Open it from there if it didn’t appear.", "", false);
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

    function showHelp() {
        appendMessage("system",
            "Motif starts by itself when you sign in, so it is normally ready "
            + "whenever MuseScore is.<br><br>"
            + "If it stays quiet, open <b>Motif Setup</b> from your Applications "
            + "folder and choose <b>Repair</b>. That takes a few seconds and "
            + "puts everything back.", "", false);
        root.view = 1;
    }

    //=========================================================================
    //  Layout
    //=========================================================================
    Rectangle {
        anchors.fill: parent
        color: T.bg

        // ---- preferences -------------------------------------------------
        Flickable {
            anchors { fill: parent; margins: T.pad }
            visible: root.settingsOpen
            contentHeight: settings.implicitHeight + T.pad
            clip: true
            SettingsPanel {
                id: settings
                width: parent.width
                ensembleOptions: root.ensembleOptions
                ensembleOverride: root.ensembleOverride
                autoOpen: root.autoOpen
                versionText: root.versionText
                connected: root.connState === "ready"
                onChanged: function (ensembleId, openAutomatically) {
                    root.ensembleOverride = ensembleId;
                    root.autoOpen = openAutomatically;
                    root.savePreferences();
                }
                onClosed: root.settingsOpen = false
            }
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 0
            visible: !root.settingsOpen

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

                    BrandHeader {
                        width: parent.width
                        visible: root.view === 0
                    }

                    StatusStrip {
                        width: parent.width
                        status: root.connState
                        onRetryRequested: { root.wakeAttempts = 0; root.checkHealth(); }
                        onHelpRequested: root.showHelp()
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
                                    Thinking { active: root.busy }
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

            // ---- follow-up ----------------------------------------------
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

            // ---- new chat -------------------------------------------------
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 46

                Rectangle {
                    anchors { left: parent.left; right: parent.right; top: parent.top
                              leftMargin: T.pad; rightMargin: T.pad }
                    height: 1
                    color: T.border
                }
                Row {
                    anchors.centerIn: parent
                    spacing: 9
                    PhraseMark {
                        width: 20; height: 9
                        color: newChatArea.containsMouse ? T.gold : T.goldDim
                        weight: 1.5
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: "New piece"
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

        // ---- preferences affordance --------------------------------------
        Rectangle {
            anchors { top: parent.top; right: parent.right; margins: 8 }
            width: 28; height: 28
            radius: T.radiusSm
            color: gearArea.containsMouse ? T.surface : "transparent"
            visible: !root.settingsOpen
            Behavior on color { ColorAnimation { duration: T.durFast } }
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
}
