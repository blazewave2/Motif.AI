//=============================================================================
//  Motif.AI — your AI composing partner, inside MuseScore
//
//  You describe the music; Motif's own composer, running on this computer,
//  writes it the way a composer does — planning the form, inventing and
//  developing its themes, trying ideas and keeping the best — and engraves
//  it. Nothing is sent anywhere. Music arrives as MusicXML,
//  which MuseScore imports far more faithfully than a plugin can build a
//  score note by note: slurs, pedalling, hairpins, tuplets and multi-voice
//  piano writing all survive intact.
//=============================================================================
import QtQuick 2.9
import QtQuick.Layouts 1.3
import MuseScore 3.0
import FileIO 3.0

import "components"
import "js/api.js" as Api
import "js/theme.js" as T

MuseScore {
    id: root

    // MuseScore Studio 4.4 and later read a plugin's title, thumbnail and
    // category straight from this file, and read lines marked //4.4 as if
    // the marker weren't there. MuseScore 3 has no such properties and
    // refuses to load a plugin that sets one, so to it these stay comments.
    //4.4 title: "Motif.AI"
    //4.4 thumbnailName: "assets/thumbnail.png"
    //4.4 categoryCode: "composing-arranging-tools"
    // MuseScore 3 lists a plugin in its menu only under its menuPath, and
    // titles its window with whatever follows the last full stop there, so
    // the name is spelled with a one-dot leader (U+2024), which looks the same.
    menuPath: "Plugins.Motif\u2024AI"
    description: "Your AI composing partner — describe a piece and Motif writes it."
    version: "2.0.0"
    // MuseScore 4 dropped dockable plugin panels in its UI rewrite:
    // pluginType "dock" silently never opens there, which is why this has to
    // be a window. dockArea is kept for MuseScore 3, which still honours it
    // and puts the panel on the right.
    pluginType: "dialog"
    dockArea: "right"
    requiresScore: false

    // Tall and narrow, so it sits beside the score rather than over it.
    implicitWidth: 400
    implicitHeight: 840
    width: implicitWidth
    height: implicitHeight

    // -- connection -------------------------------------------------------
    property string serverUrl: "http://127.0.0.1:8765"
    property string apiToken: ""
    property string connState: "checking"      // checking | ready | offline
    property string versionText: ""
    property int wakeAttempts: 0

    // -- the composer -----------------------------------------------------
    // How much care it takes: how many ideas it tries before it settles.
    property string composerQuality: "best"

    // -- preferences ------------------------------------------------------
    // Composer and instrumentation are never settings — see the prompt box.
    property bool autoOpen: true

    // -- session ----------------------------------------------------------
    property bool busy: false
    property int view: 0                       // 0 create, 1 conversation
    property bool settingsOpen: false
    property string lastPrompt: ""
    property int seedCounter: 0
    property string sessionId: ""
    property string jobId: ""
    property bool stopping: false
    property string progressLabel: "Composing…"
    property string progressDetail: ""
    property real progressFraction: 0.0
    property real progressElapsed: 0

    ListModel { id: conversation }

    FileIO { id: configFile }
    FileIO { id: scoreOut }
    FileIO { id: scoreIn }

    readonly property var examples: [
        { l1: "A Rachmaninoff prelude",        l2: "in C♯ minor, with tolling bells and a great climax",
          prompt: "Compose a Rachmaninoff-style piano prelude in C sharp minor, with tolling bells and a great climax" },
        { l1: "A Chopin nocturne",             l2: "tender and singing, with ornamented returns",
          prompt: "Write a nocturne in the style of Chopin, tender and singing, with ornamented returns of the theme" },
        { l1: "A Rachmaninoff piano concerto", l2: "piano and orchestra, with a cadenza",
          prompt: "Compose a piano concerto movement in the style of Rachmaninoff in C minor, with a cadenza" },
        { l1: "Variations on a theme",         l2: "six of them, in the style of Mozart",
          prompt: "Six variations on a theme in the style of Mozart" },
        { l1: "Continue my piece",             l2: "and build it to a climax",
          prompt: "Continue the piece I have open, developing its ideas and building to a climax" },
        { l1: "Arrange this for string quartet", l2: "keeping the melody in the first violin",
          prompt: "Arrange the piece I have open for string quartet, keeping the melody in the first violin" }
    ]

    //=========================================================================
    //  Lifecycle
    //=========================================================================
    // MuseScore calls onRun when the panel is opened. MuseScore 3 also
    // creates every plugin once at startup just to read its name and
    // version, then destroys it, so the start is deferred to the event loop
    // where that throwaway copy never arrives, and it only ever runs once.
    onRun: start()
    Component.onCompleted: deferredStart.start()
    property bool started: false

    Timer {
        id: deferredStart
        interval: 0
        repeat: false
        onTriggered: root.start()
    }

    function start() {
        if (root.started)
            return;
        root.started = true;
        loadSettings();
        if (!root.sessionId.length)
            root.sessionId = newSessionId();
        wakeAttempts = 0;
        checkHealth();
    }

    function newSessionId() {
        return "s" + Date.now().toString(36) + Math.floor(Math.random() * 1e8).toString(36);
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
        if (prefs && prefs.auto_open !== undefined)
            root.autoOpen = !!prefs.auto_open;
    }

    function savePreferences() {
        Api.savePrefs(root.serverUrl, root.apiToken, {
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

    function applyQuality(q) {
        if (q)
            root.composerQuality = q;
    }

    function checkHealth() {
        if (root.connState !== "ready")
            root.connState = "checking";
        Api.health(root.serverUrl, root.apiToken, function (res) {
            if (res && res.ok === true) {
                root.connState = "ready";
                root.wakeAttempts = 0;
                root.versionText = "Version " + res.version;
                applyQuality(res.quality);
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

    function refreshSettings() {
        Api.settings(root.serverUrl, root.apiToken, function (res) {
            if (res && res.ok === true)
                applyQuality(res.quality);
        });
    }

    function saveQuality(value) {
        root.composerQuality = value;
        Api.saveSettings(root.serverUrl, root.apiToken, { composer_quality: value },
                         function (res) {
            if (res && res.ok === true)
                applyQuality(res.quality);
        });
    }

    //=========================================================================
    //  Composing
    //=========================================================================
    function nextSeed() {
        root.seedCounter += 1;
        return Math.floor(Math.random() * 1000000) + root.seedCounter;
    }

    // Hand Motif whatever is open, so it can read it, discuss it and carry on
    // from it.
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

    function recentHistory() {
        var out = [];
        for (var i = 0; i < conversation.count; ++i) {
            var m = conversation.get(i);
            if (m.role === "user")
                out.push({ role: "musician", text: m.text });
            else if (m.role === "assistant")
                out.push({ role: "motif", text: m.text });
        }
        return out.slice(-12);
    }

    function send(promptText, isRetry) {
        if (root.busy || promptText.trim().length === 0)
            return;
        root.lastPrompt = promptText;
        root.busy = true;
        root.stopping = false;
        root.view = 1;
        root.progressLabel = "Starting…";
        root.progressDetail = "";
        root.progressFraction = 0.0;
        root.progressElapsed = 0;
        if (!isRetry)
            appendMessage("user", promptText, "", false);
        appendMessage("pending", "", "", false);

        // Neither the composer nor the instrumentation is ever a setting —
        // both come from what you type, the same way you'd ask a person.
        var scorePath = "";
        try {
            if (typeof curScore !== "undefined" && curScore !== null)
                scorePath = curScore.path || "";
        } catch (e) { scorePath = ""; }

        var payload = { prompt: promptText, seed: nextSeed(),
                        score_xml: currentScoreXml(), score_path: scorePath,
                        session_id: root.sessionId, history: recentHistory() };

        Api.startJob(root.serverUrl, root.apiToken, payload, function (res) {
            if (!res || res.ok !== true || !res.job_id) {
                finishWithError(res);
                return;
            }
            root.jobId = res.job_id;
            jobTimer.restart();
        });
    }

    // Composing with care takes minutes; the card shows the stage, what the
    // composer is thinking about or which bar it is writing, and how far along.
    Timer {
        id: jobTimer
        interval: 650
        repeat: true
        running: false
        onTriggered: root.pollJob()
    }

    function pollJob() {
        if (!root.jobId.length) {
            jobTimer.stop();
            return;
        }
        Api.job(root.serverUrl, root.apiToken, root.jobId, function (res) {
            if (!res || res.ok !== true) {
                if (res && res.offline) {
                    jobTimer.stop();
                    root.jobId = "";
                    finishWithError(res);
                }
                return;              // a missed poll is not a failure
            }
            var p = res.progress || {};
            root.progressLabel = p.label || root.progressLabel;
            root.progressDetail = p.detail || "";
            root.progressFraction = p.fraction || root.progressFraction;
            root.progressElapsed = res.elapsed || 0;
            if (res.state === "done") {
                jobTimer.stop();
                root.jobId = "";
                finishWithResult(res.result);
            } else if (res.state === "error" || res.state === "cancelled") {
                jobTimer.stop();
                root.jobId = "";
                if (res.state === "cancelled") {
                    root.busy = false;
                    root.stopping = false;
                    removePending();
                    appendMessage("system", "Stopped. Nothing was changed.", "", false);
                } else {
                    finishWithError(res.result || { error: res.error });
                }
            }
        });
    }

    function stopJob() {
        if (!root.jobId.length || root.stopping)
            return;
        root.stopping = true;
        Api.cancelJob(root.serverUrl, root.apiToken, root.jobId, function (res) { });
    }

    function finishWithError(res) {
        root.busy = false;
        root.stopping = false;
        removePending();
        if (res && res.offline) {
            root.connState = "offline";
            appendMessage("error",
                "Motif isn’t answering just now. Give it a moment and try again.", "", false);
            return;
        }
        var text = (res && (res.message || res.error))
                   ? (res.message || res.error)
                   : "Motif couldn’t finish that one. Try rewording it.";
        appendMessage("error", text, "", false);
    }

    function finishWithResult(res) {
        root.busy = false;
        root.stopping = false;
        removePending();
        if (!res || res.ok !== true) {
            finishWithError(res);
            return;
        }
        root.connState = "ready";
        if (res.session_id)
            root.sessionId = res.session_id;
        appendMessage("assistant", res.message || "Done.", describe(res),
                      !!res.musicxml_path);
        conversation.setProperty(conversation.count - 1, "xmlPath",
                                 res.musicxml_path || "");
        // A change to the piece already open must be shown right away
        // regardless of the auto-open preference: leaving the old version on
        // screen while the file underneath it has changed risks the
        // musician's next save overwriting what Motif wrote.
        if (res.same_file && res.musicxml_path)
            openScore(res.musicxml_path, true);
        else if (root.autoOpen && res.musicxml_path && res.musicxml_path.length)
            openScore(res.musicxml_path, false);
    }

    // What Motif decided, shown on request: the plan and its working notes.
    function describe(res) {
        var plan = res.plan;
        var lines = [];
        if (plan) {
            if (plan.form)
                lines.push("Form        " + plan.form);
            if (plan.key)
                lines.push("Key         " + plan.key);
            if (plan.time)
                lines.push("Time        " + plan.time[0] + "/" + plan.time[1]);
            if (plan.tempo)
                lines.push("Tempo       " + Math.round(plan.tempo)
                           + (plan.tempo_text ? "   " + plan.tempo_text : ""));
            if (plan.parts && plan.parts.length) {
                var names = [];
                for (var p = 0; p < plan.parts.length; ++p)
                    names.push(plan.parts[p].name || plan.parts[p].instrument);
                lines.push("Written for " + names.join(", "));
            } else if (plan.ensemble) {
                lines.push("Written for " + prettify(plan.ensemble));
            }
            if (plan.sections && plan.sections.length) {
                lines.push("");
                for (var i = 0; i < plan.sections.length; ++i) {
                    var s = plan.sections[i];
                    var span = s.first ? ("m" + s.first + "–" + s.last) : (s.bars + " bars");
                    lines.push("  " + pad(span, 11) + (s.label || "") + (s.key ? "  · " + s.key : ""));
                }
            }
        }
        if (res.notes && res.notes.length) {
            lines.push("");
            lines.push("While composing");
            for (var n = 0; n < res.notes.length; ++n)
                lines.push("  · " + res.notes[n]);
        }
        if (res.elapsed_ms) {
            lines.push("");
            lines.push("Composed in " + clock(res.elapsed_ms / 1000));
        }
        return lines.join("\n");
    }

    function clock(seconds) {
        var s = Math.max(0, Math.floor(seconds));
        var m = Math.floor(s / 60);
        var r = s % 60;
        return m + ":" + (r < 10 ? "0" : "") + r;
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

    function openScore(path, sameFile) {
        var opened = false;
        // MuseScore 4 has no readScore for plugins (it only logs "not
        // implemented"), so there the engine opens the score instead.
        if (mscoreMajorVersion < 4) {
            try {
                var s = readScore(path);
                if (s) {
                    opened = true;
                    try { setScore(s); } catch (e2) { /* some hosts open it directly */ }
                }
            } catch (e) {
                opened = false;
            }
        }
        if (!opened)
            openWithHost(path, sameFile);
    }

    // Ask the engine to open the score in this very MuseScore (the program
    // running the panel), or with whatever the system opens scores with.
    function openWithHost(path, sameFile) {
        var app = "";
        try { app = String(Qt.application.arguments[0] || ""); } catch (e) { app = ""; }
        Api.openScore(root.serverUrl, root.apiToken, { path: path, app: app }, function (res) {
            if (res && res.ok)
                return;
            appendMessage("system", sameFile
                ? "Motif updated your score, but couldn’t refresh the page on "
                  + "screen. Close and reopen it to see the change."
                : "Your score is saved in the Motif folder (.motif/scores in your "
                  + "home folder). Open it from there if it didn’t appear.", "", false);
        });
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
        if (root.busy)
            return;
        conversation.clear();
        root.view = 0;
        root.lastPrompt = "";
        root.sessionId = newSessionId();
        promptBox.clear();
    }

    function showHelp() {
        appendMessage("system",
            "Motif starts by itself when you sign in, so it is normally ready "
            + "whenever MuseScore is.<br><br>"
            + "If it stays quiet, open <b>Motif Setup</b> and choose <b>Repair</b>. "
            + "That takes a few seconds and puts everything back.", "", false);
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
                autoOpen: root.autoOpen
                versionText: root.versionText
                connected: root.connState === "ready"
                quality: root.composerQuality
                // Values are read from the panel rather than taken from the
                // signals: see the note on SettingsPanel.pickedQuality.
                onChanged: {
                    root.autoOpen = settings.autoOpen;
                    root.savePreferences();
                }
                onClosed: root.settingsOpen = false
                onQualityChosen: root.saveQuality(settings.pickedQuality)
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
                        placeholder: "Describe the music — a composer, a mood, a form, "
                                     + "or what to do with the score you have open…"
                        onSubmitted: root.send(promptBox.lastSubmitted, false)
                    }

                    Text {
                        text: "Try these"
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
                                    ComposingCard {
                                        label: root.progressLabel
                                        detail: root.progressDetail
                                        fraction: root.progressFraction
                                        elapsed: root.progressElapsed
                                        stopping: root.stopping
                                        canStop: root.jobId.length > 0
                                        onStopRequested: root.stopJob()
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
                    placeholder: "Ask for a change, more music, or something new…"
                    busy: root.busy
                    interactive: !root.busy
                    onSubmitted: {
                        root.send(followUp.lastSubmitted, false);
                        followUp.clear();
                    }
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
                    opacity: root.busy ? 0.4 : 1.0
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
                    cursorShape: root.busy ? Qt.ArrowCursor : Qt.PointingHandCursor
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
                onClicked: { root.settingsOpen = true; root.refreshSettings(); }
            }
        }
    }
}
