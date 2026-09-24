"""The service as the panel uses it: jobs, settings, sessions and files."""
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from motif.agent.agent import Result
from motif.control import Cancelled
from motif.server.app import Handler, MotifState


@pytest.fixture
def service(tmp_path, monkeypatch):
    from motif.server import app as app_module
    home = tmp_path / ".motif"
    home.mkdir()
    monkeypatch.setattr(app_module, "CONFIG_DIR", home)
    monkeypatch.setattr(app_module, "OUT_DIR", home / "scores")
    cfg = {"token": "t0ken", "port": 0, "model_path": "", "composer_quality": "sketch"}
    state = MotifState(cfg)
    Handler.state = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, state, home
    httpd.shutdown()


def call(base, path, payload=None, token="t0ken", method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, method=method or (
        "POST" if payload is not None else "GET"))
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Motif-Token", token)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def wait_for(base, job_id, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        view = call(base, f"/jobs/{job_id}")
        if view["state"] not in ("queued", "running"):
            return view
        time.sleep(0.05)
    raise AssertionError("job did not finish")


class TestHealthAndSettings:
    def test_health_reports_the_composer(self, service):
        base, _, _ = service
        h = call(base, "/health", token="")
        assert h["ok"] and h["version"].startswith("2.")
        assert h["engine"].startswith("motif") and h["quality"] == "sketch"

    def test_the_care_setting_is_stored(self, service):
        base, state, home = service
        res = call(base, "/settings", {"composer_quality": "maximum"})
        assert res["ok"] and res["quality"] == "maximum"
        assert json.loads((home / "config.json").read_text())["composer_quality"] == "maximum"
        assert state.agent.options["quality"] == "maximum"

    def test_unknown_care_levels_are_ignored(self, service):
        base, _, _ = service
        assert call(base, "/settings", {"composer_quality": "ultra"})["quality"] == "sketch"

    def test_settings_need_the_token(self, service):
        base, _, _ = service
        with pytest.raises(urllib.error.HTTPError) as e:
            call(base, "/settings", {"composer_quality": "best"}, token="wrong")
        assert e.value.code == 401

    def test_settings_from_older_versions_are_cleared_away(self, tmp_path, monkeypatch):
        from motif.server import app as app_module
        home = tmp_path / "old"
        home.mkdir()
        (home / "config.json").write_text(json.dumps({
            "token": "x", "port": 8765, "anthropic_api_key": "sk-ant-old-secret",
            "planner": "claude", "composer_model": "claude-opus-5", "spend_cap_usd": 25}))
        monkeypatch.setattr(app_module, "CONFIG_DIR", home)
        monkeypatch.setattr(app_module, "OUT_DIR", home / "scores")
        cfg = app_module.ensure_config()
        stored = (home / "config.json").read_text()
        assert "sk-ant" not in stored and "anthropic" not in stored
        assert cfg["token"] == "x" and cfg["composer_quality"] == "best"


class TestJobs:
    def test_a_job_runs_and_reports(self, service):
        base, _, _ = service
        started = call(base, "/jobs", {"prompt": "Compose a short piano piece",
                                       "session_id": "conv1"})
        assert started["state"] in ("queued", "running", "done")
        view = wait_for(base, started["job_id"])
        assert view["state"] == "done"
        result = view["result"]
        assert result["ok"] and Path(result["musicxml_path"]).exists()
        assert result["title"] and result["session_id"] == "conv1"

    def test_unknown_job(self, service):
        base, _, _ = service
        with pytest.raises(urllib.error.HTTPError) as e:
            call(base, "/jobs/nope")
        assert e.value.code == 404

    def test_a_queued_job_can_be_cancelled(self, service):
        base, state, _ = service
        gate = threading.Event()
        # Occupy the worker so the next job waits in the queue.
        state.jobs.submit(lambda j: gate.wait(5) or {"ok": True})
        queued = call(base, "/jobs", {"prompt": "Compose a waltz"})
        cancelled = call(base, f"/jobs/{queued['job_id']}/cancel", {})
        assert cancelled["state"] == "cancelled"
        gate.set()

    def test_stop_reaches_a_piece_being_written(self, service):
        base, state, _ = service

        class Slow:
            options = {}

            def run(self, req, progress=None):
                while not req.cancel.wait(0.05):
                    progress("Writing…")
                try:
                    state_agent_report(req)
                except Cancelled:
                    return Result(ok=False, intent="cancelled", error="cancelled",
                                  message="Stopped. Nothing was changed.")
                return Result(ok=True)

        def state_agent_report(req):
            if req.cancel.is_set():
                raise Cancelled()

        state.agent = Slow()
        job = call(base, "/jobs", {"prompt": "A long symphony"})
        time.sleep(0.3)
        call(base, f"/jobs/{job['job_id']}/cancel", {})
        view = wait_for(base, job["job_id"])
        assert view["state"] in ("cancelled", "done")
        if view.get("result"):
            assert view["result"]["ok"] is False and view["result"]["cancelled"] is True

    def test_the_composer_honours_stop(self, service):
        """Stop is noticed at the next progress report inside the composer."""
        from motif.agent.agent import MotifAgent, Request
        agent = MotifAgent(options={"quality": "sketch"})
        cancel = threading.Event()
        reports = []

        def progress(update):
            reports.append(update)
            cancel.set()                      # the musician presses Stop at once

        result = agent.run(Request(prompt="A long Rachmaninoff prelude", cancel=cancel),
                           progress=progress)
        assert result.ok is False and result.intent == "cancelled"
        assert len(reports) <= 2


class TestSessionsAndFiles:
    def test_a_conversation_is_remembered(self, service):
        base, state, home = service
        first = wait_for(base, call(base, "/jobs", {"prompt": "A short nocturne",
                                                    "session_id": "talk"})["job_id"])
        assert first["result"]["ok"]
        saved = json.loads((home / "sessions" / "talk.json").read_text())
        assert [t["role"] for t in saved["history"]] == ["musician", "motif"]
        assert saved["last_file"] == first["result"]["musicxml_path"]

    def test_a_musescore_file_is_never_overwritten(self, service, tmp_path):
        base, _, _ = service
        mscz = tmp_path / "mine.mscz"
        mscz.write_bytes(b"PK\x03\x04 not really a zip")
        first = wait_for(base, call(base, "/jobs", {"prompt": "A short waltz"})["job_id"])
        xml = Path(first["result"]["musicxml_path"]).read_text()
        view = wait_for(base, call(base, "/jobs", {
            "prompt": "Transpose it to D major", "score_xml": xml,
            "score_path": str(mscz)})["job_id"])
        res = view["result"]
        assert res["ok"] and res["same_file"] is False
        assert mscz.read_bytes() == b"PK\x03\x04 not really a zip"
        assert Path(res["musicxml_path"]).suffix == ".musicxml"

    def test_an_open_musicxml_file_is_edited_in_place(self, service, tmp_path):
        base, _, _ = service
        first = wait_for(base, call(base, "/jobs", {"prompt": "A short waltz"})["job_id"])
        mine = tmp_path / "mine.musicxml"
        mine.write_text(Path(first["result"]["musicxml_path"]).read_text())
        view = wait_for(base, call(base, "/jobs", {
            "prompt": "Transpose it to D major", "score_xml": mine.read_text(),
            "score_path": str(mine)})["job_id"])
        res = view["result"]
        assert res["ok"] and res["same_file"] is True
        assert res["musicxml_path"] == str(mine)
