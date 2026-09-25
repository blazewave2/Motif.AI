"""The MuseScore panel itself, loaded under Qt and driven end to end.

MuseScore's own QML modules (``MuseScore 3.0``, ``FileIO 3.0``) are replaced
by small stand-ins in ``qmlstub/``; everything else is the real plugin,
talking over HTTP to a real engine whose composer is scripted. Skipped
where Qt for Python (PySide6) or its system libraries aren't installed.
"""
import json
import os
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import (Q_ARG, QCoreApplication, QMetaObject, QObject, Qt, QUrl,
                                Slot)
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
except Exception as exc:                     # PySide6 missing, or no libEGL etc.
    pytest.skip(f"Qt for Python unavailable: {exc}", allow_module_level=True)

from motif.agent.agent import Result  # noqa: E402
from motif.control import Cancelled, Progress  # noqa: E402

PLUGIN = Path(__file__).resolve().parents[2] / "plugin" / "MotifAI" / "MotifAI.qml"
STUBS = Path(__file__).parent / "qmlstub"


class _Files(QObject):
    @Slot(str, result=str)
    def read(self, path):
        try:
            return Path(path).read_text()
        except OSError:
            return ""


@pytest.fixture(scope="module")
def qt_app():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture
def panel(qt_app, tmp_path, monkeypatch):
    from motif.server import app as app_module
    home = tmp_path
    mh = home / ".motif"
    mh.mkdir()
    monkeypatch.setattr(app_module, "CONFIG_DIR", mh)
    monkeypatch.setattr(app_module, "OUT_DIR", mh / "scores")
    from motif.server.app import Handler, MotifState
    cfg = {"token": "tok123", "port": 0, "model_path": "", "composer_quality": "sketch"}
    state = MotifState(cfg)
    Handler.state = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    cfg["port"] = httpd.server_address[1]
    (mh / "config.json").write_text(json.dumps(cfg))

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(STUBS))
    files = _Files()
    engine.rootContext().setContextProperty("stubHome", str(home))
    engine.rootContext().setContextProperty("stubFiles", files)
    problems: list[str] = []
    engine.warnings.connect(lambda ws: problems.extend(w.toString() for w in ws))
    engine.load(QUrl.fromLocalFile(str(PLUGIN)))
    assert engine.rootObjects(), "\n".join(problems)
    root = engine.rootObjects()[0]

    class Panel:
        def js(self, expr):
            v = QQmlExpression(engine.contextForObject(root), root, expr).evaluate()
            return v[0] if isinstance(v, tuple) else v

        def spin(self, cond, timeout=20):
            end = time.time() + timeout
            while time.time() < end:
                QCoreApplication.processEvents()
                if cond():
                    return True
                time.sleep(0.01)
            return False

        def call(self, name, *args):
            QMetaObject.invokeMethod(root, name, Qt.DirectConnection,
                                     *[Q_ARG("QVariant", a) for a in args])

        prop = staticmethod(lambda name: root.property(name))

    p = Panel()
    p.state, p.problems, p.files, p.engine = state, problems, files, engine
    assert p.spin(lambda: root.property("connState") == "ready")
    yield p
    httpd.shutdown()
    engine.deleteLater()


def test_compose_through_the_panel(panel):
    panel.call("send", "Write me a short nocturne", False)
    assert panel.spin(lambda: not panel.prop("busy"), 120)
    assert int(panel.js("conversation.count")) == 2
    assert panel.js("conversation.get(1).role") == "assistant"
    assert "Nocturne" in panel.js("conversation.get(1).text")
    assert "Form" in panel.js("conversation.get(1).detail")
    assert int(panel.js("root.openedPaths.length")) == 1
    assert not [p for p in panel.problems if "stub" not in p.lower()]


class _Slow:
    """An agent that composes until it is told to stop."""
    options = {}

    def run(self, req, progress=None):
        try:
            while True:
                if req.cancel.is_set():
                    raise Cancelled()
                progress(Progress("writing", "Writing the theme", "bar 3", 0.3))
                time.sleep(0.05)
        except Cancelled:
            return Result(ok=False, intent="cancelled", error="cancelled",
                          message="Stopped. Nothing was changed.")


def test_stop_cancels_the_job(panel):
    panel.state.agent = _Slow()
    panel.call("send", "Something long", False)
    assert panel.spin(lambda: panel.prop("progressLabel") == "Writing the theme", 10)
    panel.call("stopJob")
    assert panel.spin(lambda: not panel.prop("busy"), 15)
    n = int(panel.js("conversation.count"))
    assert panel.js(f"conversation.get({n - 1}).text").startswith("Stopped")


def test_the_care_setting_is_saved(panel):
    panel.call("saveQuality", "maximum")
    assert panel.spin(lambda: panel.state.cfg.get("composer_quality") == "maximum", 10)
    assert panel.prop("composerQuality") == "maximum"


def test_the_prompt_box_sends_what_was_typed(panel):
    panel.js('(function () { promptBox.text = "A short waltz"; promptBox.send(); })()')
    assert panel.spin(lambda: not panel.prop("busy"), 120)
    assert panel.js("conversation.get(0).text") == "A short waltz"
    assert panel.js("conversation.get(1).role") == "assistant"


def test_the_settings_panel_reports_the_choice(panel):
    """Choices are read from the panel, not from signal arguments, so they
    work on the Qt 5.9 inside MuseScore 3 as well as on Qt 6."""
    panel.js('(function () { settings.pickedQuality = "balanced";'
             ' settings.qualityChosen("balanced"); })()')
    assert panel.spin(lambda: panel.state.cfg.get("composer_quality") == "balanced", 10)


def test_replies_are_shown_as_text_not_markup(qt_app):
    from PySide6.QtQml import QJSEngine
    source = (PLUGIN.parent / "js" / "text.js").read_text().replace(".pragma library", "")
    engine = QJSEngine()
    engine.evaluate(source)
    rich = engine.globalObject().property("rich")
    show = lambda s: rich.call([s]).toString()                      # noqa: E731
    assert show("**Nocturne in E minor**: a *quiet* piece") == \
        "<b>Nocturne in E minor</b>: a <i>quiet</i> piece"
    assert show("bars 12 < 16 & the coda") == "bars 12 &lt; 16 &amp; the coda"
    assert show("3 * 4 * 5") == "3 * 4 * 5"
    assert show("first line\nsecond") == "first line<br>second"
    assert show("<b>not markup</b>") == "&lt;b&gt;not markup&lt;/b&gt;"


def test_only_the_panel_itself_looks_like_a_plugin():
    """MuseScore 4 lists every .qml file that names it as a plugin of its
    own, so the panel's components must not mention it, even in a comment."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "plugin" / "MotifAI"
    named = [p.name for p in root.rglob("*.qml") if "MuseScore" in p.read_text()]
    assert named == ["MotifAI.qml"]


def test_on_musescore_4_the_engine_opens_the_score(panel, monkeypatch):
    """MuseScore 4's plugins cannot open a score themselves, so the panel
    asks the engine to open it with the program the panel runs in."""
    from motif.server import opener
    opened: list = []
    monkeypatch.setattr(opener, "open_score",
                        lambda path, app=None: (opened.append((path, app)) or (True, "musescore")))
    panel.js("root.mscoreMajorVersion = 4")
    panel.call("send", "Write me a short nocturne", False)
    assert panel.spin(lambda: not panel.prop("busy"), 120)
    assert panel.spin(lambda: bool(opened), 10)
    assert int(panel.js("root.openedPaths.length")) == 0
    path, app = opened[0]
    assert path.suffix == ".musicxml" and path.exists()
    # and no apology for a score that did open
    texts = [panel.js(f"conversation.get({i}).text") for i in range(int(panel.js("conversation.count")))]
    assert not [t for t in texts if "didn’t appear" in t]



# A two-bar piano score as MuseScore's plugin API presents it: bars, parts
# and a cursor that steps through each track's chords and rests.
_FAKE_SCORE = """
(function () {
    var events = {
        0: [[0, 960, [[72, 14, 0, 0]]], [960, 960, [[74, 16, 1, 0]]],
            [1920, 960, [[74, 16, 0, 1]]], [2880, 960, [[76, 18, 0, 0]]]],
        4: [[0, 1920, [[48, 14, 0, 0], [55, 15, 0, 0]]], [1920, 1920, [[43, 15, 0, 0]]]]
    };
    function frac(t) { return { ticks: t, numerator: t / 120, denominator: 16 }; }
    var m2 = { firstSegment: { tick: 1920 }, timesigActual: frac(1920),
               timesigNominal: { numerator: 4, denominator: 4, ticks: 1920 }, nextMeasure: null };
    var m1 = { firstSegment: { tick: 0 }, timesigActual: frac(1920),
               timesigNominal: { numerator: 4, denominator: 4, ticks: 1920 }, nextMeasure: m2 };
    function cursor() {
        return {
            track: 0, i: 0, list: [], segment: null, element: null, tick: 0, keySignature: 0,
            rewind: function () { this.list = events[this.track] || []; this.i = 0; this.sync(); },
            sync: function () {
                var e = this.list[this.i];
                if (!e) { this.segment = null; this.element = null; return; }
                this.tick = e[0];
                var tempo = { type: Element.TEMPO_TEXT, track: 0, tempo: 1.5,
                              text: "<b>Andante</b> = 90" };
                this.segment = { annotations: (e[0] === 0 && this.track === 0) ? [tempo] : [] };
                this.element = { type: Element.CHORD, tuplet: null, duration: frac(e[1]),
                                 actualDuration: frac(e[1]),
                                 notes: e[2].map(function (n) {
                                     return { pitch: n[0], tpc: n[1], tieForward: !!n[2],
                                              tieBack: !!n[3] }; }) };
            },
            next: function () { this.i += 1; this.sync(); return !!this.segment; },
            nextMeasure: function () {
                var end = (Math.floor(this.tick / 1920) + 1) * 1920;
                while (this.segment && this.tick < end) { this.i += 1; this.sync(); }
                return !!this.segment;
            }
        };
    }
    root.curScore = {
        title: "Two Bars", metaTag: function () { return ""; }, ntracks: 8,
        parts: [{ longName: "Piano", partName: "Piano", shortName: "Pno.", instrumentId: "piano",
                  midiProgram: 0, startTrack: 0, endTrack: 8 }],
        firstMeasure: m1, newCursor: cursor
    };
})()
"""


def test_on_musescore_4_the_panel_reads_the_open_score_itself(panel):
    """MuseScore 4 cannot save the score for the panel, so the panel walks
    it with the cursor and sends what it finds."""
    seen = []
    real = panel.state.agent.run

    def run(req, progress=None):
        seen.append(req)
        return real(req, progress)
    panel.state.agent.run = run
    panel.js("root.mscoreMajorVersion = 4")
    panel.js(_FAKE_SCORE)
    panel.call("send", "Continue this piece", False)
    assert panel.spin(lambda: not panel.prop("busy"), 120)
    req = seen[0]
    assert not req.score_xml
    snap = req.score_snapshot
    assert snap["format"] == "motif-snapshot-1" and snap["title"] == "Two Bars"
    assert [e[1] for e in snap["events"] if e[0] == 0] == [0, 960, 1920, 2880]
    assert snap["tempos"] == [[0, 90, "<b>Andante</b> = 90"]]
    assert snap["keys"] == [[0, 0], [1920, 0]]
    n = int(panel.js("conversation.count"))
    assert panel.js(f"conversation.get({n - 1}).role") == "assistant"
    assert "Two Bars" in panel.js(f"conversation.get({n - 1}).text")
