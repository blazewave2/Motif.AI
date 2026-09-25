"""The local HTTP service: in-place editing of an already-open file, and the
progress endpoint the panel polls while composing."""
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from motif.server.app import Handler, MotifState
from http.server import ThreadingHTTPServer


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("MOTIF_HOME", str(tmp_path / ".motif"))
    from motif.server import app as app_module
    monkeypatch.setattr(app_module, "CONFIG_DIR", tmp_path / ".motif")
    monkeypatch.setattr(app_module, "OUT_DIR", tmp_path / ".motif" / "scores")
    app_module.OUT_DIR.mkdir(parents=True, exist_ok=True)

    cfg = {"token": "", "port": 0, "model_path": "", "composer_quality": "sketch"}
    state = MotifState(cfg)
    Handler.state = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    thread.join(timeout=5)


def _post(base, path, payload):
    req = urllib.request.Request(
        base + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _strip_notes(xml: str) -> str:
    """Turn a score into the blank page MuseScore gives you on File > New."""
    import re
    # Notes carry attributes ("<note dynamics=...>"), so the tag has to be
    # matched loosely or almost nothing is removed.
    return re.sub(r"<note(?:\s[^>]*)?>.*?</note>", "", xml, flags=re.S)


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


class TestInPlaceEditing:
    def test_a_new_piece_gets_its_own_file(self, server):
        res = _post(server, "/compose", {"prompt": "Compose a joyful piano piece"})
        assert res["ok"] is True
        assert res["same_file"] is False
        assert Path(res["musicxml_path"]).exists()

    def test_continuing_an_open_score_writes_back_to_it(self, server, tmp_path):
        first = _post(server, "/compose", {"prompt": "Compose a short piano piece"})
        own_path = tmp_path / "My Piece.musicxml"
        own_path.write_text(first["musicxml"], encoding="utf-8")

        res = _post(server, "/compose", {
            "prompt": "Continue in the same style",
            "score_xml": first["musicxml"],
            "score_path": str(own_path),
        })
        assert res["ok"] is True
        assert res["same_file"] is True
        assert res["musicxml_path"] == str(own_path)
        # The file the musician already had open now holds the continuation,
        # not a second file they'd have to go find.
        assert own_path.read_text(encoding="utf-8") == res["musicxml"]

    def test_an_unrelated_new_piece_does_not_overwrite_the_open_file(
            self, server, tmp_path):
        first = _post(server, "/compose", {"prompt": "Compose a short piano piece"})
        own_path = tmp_path / "My Piece.musicxml"
        own_path.write_text(first["musicxml"], encoding="utf-8")

        res = _post(server, "/compose", {
            "prompt": "Compose a completely different waltz",
            "score_xml": first["musicxml"],
            "score_path": str(own_path),
        })
        assert res["ok"] is True
        assert res["same_file"] is False
        assert res["musicxml_path"] != str(own_path)
        assert own_path.read_text(encoding="utf-8") == first["musicxml"]

    def test_a_new_piece_fills_the_blank_score_already_open(self, server, tmp_path):
        # Starting a blank score and asking for a piece should put the piece
        # on that page, not open a second tab next to it.
        blank = _post(server, "/compose", {"prompt": "x"})   # any score, to get a shell
        empty_xml = _strip_notes(blank["musicxml"])
        own_path = tmp_path / "Blank.musicxml"
        own_path.write_text(empty_xml, encoding="utf-8")

        res = _post(server, "/compose", {
            "prompt": "Compose a gentle piano piece",
            "score_xml": empty_xml,
            "score_path": str(own_path),
        })
        assert res["ok"] is True
        assert res["same_file"] is True
        assert res["musicxml_path"] == str(own_path)

    def test_a_nonexistent_score_path_is_never_trusted(self, server, tmp_path):
        first = _post(server, "/compose", {"prompt": "Compose a short piano piece"})
        res = _post(server, "/compose", {
            "prompt": "Continue in the same style",
            "score_xml": first["musicxml"],
            "score_path": str(tmp_path / "does-not-exist.musicxml"),
        })
        assert res["ok"] is True
        assert res["same_file"] is False


class TestProgressEndpoint:
    def test_progress_is_available_and_clears_after_a_request(self, server):
        before = _get(server, "/progress")
        assert before["ok"] is True
        _post(server, "/compose", {"prompt": "Compose a short piano piece"})
        after = _get(server, "/progress")
        assert after["text"] == ""          # reset once the request finishes


class TestOpeningScores:
    """MuseScore 4's plugins cannot open a score, so the engine does."""

    def test_only_its_own_scores_with_a_musescore(self, server, tmp_path, monkeypatch):
        from motif.server import opener
        from motif.server import app as app_module
        opened = []
        monkeypatch.setattr(opener, "open_score",
                            lambda path, app=None: opened.append((path, app)) or (True, "musescore"))
        outside = tmp_path / "elsewhere.musicxml"
        outside.write_text("<score-partwise/>")
        with pytest.raises(urllib.error.HTTPError):
            _post(server, "/open", {"path": str(outside)})
        mine = app_module.OUT_DIR / "Nocturne.musicxml"
        mine.write_text("<score-partwise/>")
        assert _post(server, "/open", {"path": str(mine), "app": "/usr/bin/mscore"})["ok"]
        assert opened == [(mine, "/usr/bin/mscore")]
        assert opener.is_musescore("/Applications/MuseScore 4.app/Contents/MacOS/mscore")
        assert opener.is_musescore("C:/Program Files/MuseScore 4/bin/MuseScore4.exe")
        assert not opener.is_musescore("/bin/sh")

    def test_an_appimage_musescore_is_started_through_its_image(self, tmp_path):
        from motif.server.opener import program
        inner = tmp_path / "squashfs-root" / "bin" / "mscore4portable"
        inner.parent.mkdir(parents=True)
        inner.write_text("")
        apprun = tmp_path / "squashfs-root" / "AppRun"
        apprun.write_text("#!/bin/sh\n")
        apprun.chmod(0o755)
        # the inner program cannot find its libraries by itself
        assert program(str(inner)) == [str(apprun)]
        image = tmp_path / "MuseScore-Studio-4.6.AppImage"
        image.write_text("")
        image.chmod(0o755)
        assert program(str(inner), {"APPIMAGE": str(image)}) == [str(image)]
        assert program("/usr/bin/mscore") == ["/usr/bin/mscore"]

    def test_the_new_window_goes_on_the_musicians_screen(self, monkeypatch):
        from motif.server.opener import session_env
        monkeypatch.delenv("DISPLAY", raising=False)
        env = session_env({"DISPLAY": ":1", "HOME": "/somewhere/else"})
        assert env["DISPLAY"] == ":1"
        assert env.get("HOME") != "/somewhere/else"
        assert session_env({}) is None

    @pytest.mark.skipif(not hasattr(__import__("os"), "fork"), reason="POSIX programs")
    def test_a_musescore_that_cannot_start_hands_over_to_the_system(self, tmp_path, monkeypatch):
        from motif.server import opener
        monkeypatch.setattr(opener, "_SETTLE", 0.5)
        monkeypatch.setattr(opener, "environment_of", lambda app: {})
        score = tmp_path / "Waltz.musicxml"
        score.write_text("<score-partwise/>")
        broken = tmp_path / "bin" / "mscore"
        broken.parent.mkdir()
        broken.write_text("#!/bin/sh\nexit 127\n")
        broken.chmod(0o755)
        handed = []
        monkeypatch.setattr(opener, "_system_open",
                            lambda path, env=None: handed.append(path) or (True, "system"))
        assert opener.open_score(score, str(broken)) == (True, "system")
        assert handed == [score]
        # one that starts and stays open is MuseScore at work
        seen = tmp_path / "seen"
        working = tmp_path / "bin" / "MuseScore4"
        working.write_text(f'#!/bin/sh\necho "$1" > "{seen}"\nsleep 3\n')
        working.chmod(0o755)
        assert opener.open_score(score, str(working)) == (True, "musescore")
        assert seen.read_text().strip() == str(score)
