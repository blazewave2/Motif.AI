"""The local Motif service the MuseScore plugin talks to.

Built on the standard library, so the engine installs with nothing to set
up, and everything it does happens on this computer: the composer is Motif's
own, and no request or score is ever sent anywhere.

Composing carefully takes time, so the panel starts a job and polls it:
``POST /jobs`` returns at once, ``GET /jobs/<id>`` reports the stage and what
the composer is working on, and ``POST /jobs/<id>/cancel`` stops it.
``POST /compose`` runs the same work and waits, for scripts and the command
line.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

VERSION = "2.0.0"
DEFAULT_PORT = 8765
MAX_BODY = 32 * 1024 * 1024        # 32 MB: large orchestral scores round-trip

CONFIG_DIR = Path(os.environ.get("MOTIF_HOME") or (Path.home() / ".motif"))
OUT_DIR = CONFIG_DIR / "scores"

#: How much care the composer takes: how many ideas it tries and how many
#: times it reviews and rewrites before it settles. See docs/COMPOSER.md.
QUALITIES = ("maximum", "best", "balanced", "sketch")

#: Settings earlier versions kept that no longer mean anything, removed from
#: the config file on sight (an old API key most of all).
_RETIRED = ("anthropic_api_key", "planner", "composer_model", "spend_cap_usd",
            "api_base_url")

from ..agent.agent import MotifAgent, Request  # noqa: E402
from ..agent.session import SessionStore  # noqa: E402
from ..compose.orchestration import ENSEMBLES  # noqa: E402
from ..compose.styles import STYLES  # noqa: E402
from .jobs import JobManager  # noqa: E402


def ensure_config() -> dict:
    """Create the config directory and a shared token on first run."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIG_DIR / "config.json"
    cfg: dict = {}
    if path.exists():
        try:
            cfg = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            cfg = {}
    changed = False
    if not cfg.get("token"):
        cfg["token"] = secrets.token_urlsafe(24)
        changed = True
    for k, v in (("port", DEFAULT_PORT), ("model_path", ""), ("composer_quality", "best")):
        if k not in cfg:
            cfg[k] = v
            changed = True
    for k in _RETIRED:
        if k in cfg:
            del cfg[k]
            changed = True
    if changed or not path.exists():
        _write_config(cfg)
    return cfg


def _write_config(cfg: dict) -> None:
    path = CONFIG_DIR / "config.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2))
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path)


class MotifState:
    """Process-wide singletons: the agent, the optional model, the config."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.model = None
        self.model_error = ""
        self.lock = threading.Lock()
        self.progress_text = ""
        self.jobs = JobManager()
        self.sessions = SessionStore(CONFIG_DIR / "sessions")
        self._load_model()
        self.build_agent()

    def quality(self) -> str:
        q = self.cfg.get("composer_quality")
        return q if q in QUALITIES else "best"

    def build_agent(self) -> None:
        self.agent = MotifAgent(model=self.model, sessions=self.sessions,
                                options={"quality": self.quality()})

    # -- optional extras -------------------------------------------------
    def _load_model(self) -> None:
        # A checkpoint dropped into the Motif folder is picked up with no
        # configuration at all: download it, put it there, restart.
        default = CONFIG_DIR / "model.pt"
        path = (self.cfg.get("model_path") or os.environ.get("MOTIF_MODEL", "")
                or (str(default) if default.exists() else ""))
        if not path:
            return
        if not Path(path).exists():
            self.model_error = f"model file not found: {path}"
            return
        try:
            from ..model.runtime import NeuralComposer
            self.model = NeuralComposer(path)
        except Exception as exc:
            self.model_error = f"{type(exc).__name__}: {exc}"
            self.model = None


class Handler(BaseHTTPRequestHandler):
    server_version = f"Motif/{VERSION}"
    state: MotifState = None            # injected by serve()

    # -- plumbing ---------------------------------------------------------
    def log_message(self, fmt, *args):          # keep the console readable
        if os.environ.get("MOTIF_VERBOSE"):
            sys.stderr.write("  %s\n" % (fmt % args))

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _authorised(self) -> bool:
        # A browser always sends Origin on a cross-site POST; MuseScore's QML
        # XHR does not.  Rejecting Origin blocks drive-by requests from web
        # pages outright, and the token covers everything else on the machine.
        if self.headers.get("Origin"):
            return False
        token = self.state.cfg.get("token", "")
        if not token:
            return True
        sent = self.headers.get("X-Motif-Token", "")
        return secrets.compare_digest(sent, token)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ValueError("request body too large")
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("request body must be a JSON object")
        return data

    # -- routes -----------------------------------------------------------
    def do_GET(self) -> None:
        route = urlparse(self.path).path.rstrip("/") or "/"
        if route == "/health":
            return self._json(200, {
                "ok": True, "service": "motif", "version": VERSION,
                "model_loaded": self.state.model is not None,
                "model_error": self.state.model_error,
                "engine": "motif+neural" if self.state.model else "motif",
                "quality": self.state.quality(),
            })
        if not self._authorised():
            return self._json(401, {"ok": False, "error": "unauthorised"})
        if route == "/styles":
            return self._json(200, {"ok": True, "styles": [
                {"id": n, "name": p.display, "era": p.era,
                 "forms": list(p.forms), "keywords": list(p.keywords)[:6]}
                for n, p in sorted(STYLES.items(), key=lambda kv: kv[1].display)]})
        if route == "/ensembles":
            return self._json(200, {"ok": True, "ensembles": [
                {"id": k, "instruments": v} for k, v in ENSEMBLES.items()]})
        if route == "/progress":
            # Kept for older panels, which poll this rather than a job.
            return self._json(200, {"ok": True, "text": self.state.progress_text})
        if route == "/settings":
            return self._json(200, {"ok": True, **self._settings_view()})
        if route.startswith("/jobs/"):
            job = self.state.jobs.get(route.split("/")[2])
            if job is None:
                return self._json(404, {"ok": False, "error": "no such job"})
            return self._json(200, job.view())
        return self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        route = urlparse(self.path).path.rstrip("/") or "/"
        if not self._authorised():
            return self._json(401, {"ok": False, "error": "unauthorised"})
        try:
            body = self._read_body()
        except json.JSONDecodeError:
            return self._json(400, {"ok": False, "error": "invalid JSON body"})
        except ValueError as exc:
            return self._json(400, {"ok": False, "error": str(exc)})

        if route == "/compose":
            return self._compose(body)
        if route == "/jobs":
            return self._start_job(body)
        if route.startswith("/jobs/") and route.endswith("/cancel"):
            job = self.state.jobs.cancel(route.split("/")[2])
            if job is None:
                return self._json(404, {"ok": False, "error": "no such job"})
            return self._json(200, job.view())
        if route == "/plan":
            return self._plan(body)
        if route == "/preferences":
            return self._preferences(body)
        if route == "/settings":
            return self._settings(body)
        if route == "/open":
            return self._open(body)
        if route == "/shutdown":
            threading.Timer(0.2, self.server.shutdown).start()
            return self._json(200, {"ok": True, "message": "shutting down"})
        return self._json(404, {"ok": False, "error": "not found"})

    # -- composing --------------------------------------------------------
    def _compose(self, body: dict) -> None:
        """Compose and wait — for the command line and older panels."""
        if not (body.get("prompt") or "").strip():
            return self._json(400, {"ok": False, "error": "prompt is required"})
        job = self.state.jobs.submit(lambda j: _run(self.state, body, j))
        self.state.jobs.wait(job)
        if job.payload is not None:
            return self._json(200, job.payload)
        return self._json(200, {"ok": False, "error": job.error or "failed",
                                "message": job.error or "Motif could not complete that."})

    def _start_job(self, body: dict) -> None:
        if not (body.get("prompt") or "").strip():
            return self._json(400, {"ok": False, "error": "prompt is required"})
        job = self.state.jobs.submit(lambda j: _run(self.state, body, j))
        return self._json(200, job.view())

    # -- opening a score -----------------------------------------------------
    def _open(self, body: dict) -> None:
        """Open a finished score in MuseScore, for hosts whose plugins can't."""
        from .opener import OPENABLE, inside, open_score
        path = Path(str(body.get("path") or ""))
        if not path.is_file() or path.suffix.lower() not in OPENABLE or \
                not inside(path, OUT_DIR):
            return self._json(400, {"ok": False, "error": "not a score Motif wrote"})
        try:
            ok, how = open_score(path, str(body.get("app") or "") or None)
        except OSError as exc:
            return self._json(200, {"ok": False, "error": str(exc)})
        return self._json(200, {"ok": ok, "how": how} if ok else {"ok": False, "error": how})

    # -- settings ---------------------------------------------------------
    def _settings_view(self) -> dict:
        return {"quality": self.state.quality(), "qualities": list(QUALITIES),
                "preferences": self.state.cfg.get("preferences", {})}

    def _settings(self, body: dict) -> None:
        """Store the composer settings chosen in the panel."""
        cfg = self.state.cfg
        if body.get("composer_quality") in QUALITIES:
            cfg["composer_quality"] = body["composer_quality"]
        try:
            _write_config(cfg)
        except OSError as exc:
            return self._json(200, {"ok": False, "error": str(exc)})
        self.state.build_agent()
        return self._json(200, {"ok": True, **self._settings_view()})

    def _preferences(self, body: dict) -> None:
        """Remember the musician's choices between sessions.

        There is deliberately no stored composer or instrumentation
        preference: both come from the prompt every time — "in the style of
        Chopin", "for a string quartet", "continue in the same style" — so
        neither can go stale sitting in a config file, and a piece already
        open always wins unless the request names something different.
        """
        prefs = self.state.cfg.setdefault("preferences", {})
        prefs.pop("style", None)
        prefs.pop("ensemble", None)
        if "auto_open" in body:
            prefs["auto_open"] = bool(body["auto_open"])
        try:
            _write_config(self.state.cfg)
        except OSError as exc:
            return self._json(200, {"ok": False, "error": str(exc)})
        return self._json(200, {"ok": True, "preferences": prefs})

    def _plan(self, body: dict) -> None:
        from ..agent.prompt_parser import parse_prompt
        prompt = (body.get("prompt") or "").strip()
        if not prompt:
            return self._json(400, {"ok": False, "error": "prompt is required"})
        plan = parse_prompt(prompt[:4000], seed=body.get("seed"))
        return self._json(200, {"ok": True, "plan": json.loads(plan.to_json())})


# ---------------------------------------------------------------------------
# the work itself (runs on the job worker)
# ---------------------------------------------------------------------------
_EDITS_OPEN_PIECE = ("continue", "develop", "harmonize", "edit", "revise", "arrange",
                     "accompany", "transform")


def _run(state: MotifState, body: dict, job) -> dict:
    prompt = (body.get("prompt") or "").strip()[:8000]
    history = body.get("history") if isinstance(body.get("history"), list) else []
    # Neither the composer nor the instrumentation is ever taken from a
    # stored preference — only from what the musician actually typed, or an
    # explicit override passed by a caller (the CLI's --style/--ensemble).
    req = Request(
        prompt=prompt,
        score_xml=body.get("score_xml") or None,
        score_path=body.get("score_path") or None,
        seed=body.get("seed"),
        style=body.get("style") or None,
        ensemble=body.get("ensemble") or None,
        history=history[-24:],
        use_model=bool(body.get("use_model", True)),
        session_id=str(body.get("session_id") or "") or None,
        cancel=job.cancel)

    def progress(update) -> None:
        if isinstance(update, str):
            job.progress = {"stage": "working", "label": update, "detail": "",
                            "fraction": job.progress.get("fraction", 0.0)}
            state.progress_text = update
            return
        job.progress = {"stage": update.stage, "label": update.label,
                        "detail": update.detail, "fraction": update.fraction}
        state.progress_text = update.label + (f" — {update.detail}" if update.detail else "")

    started = time.time()
    with state.lock:
        state.progress_text = ""
        try:
            result = state.agent.run(req, progress=progress)
        finally:
            state.progress_text = ""
    if not result.ok:
        return {"ok": False, "error": result.error, "message": result.message,
                "detail": result.analysis, "engine": result.engine,
                "cancelled": result.intent == "cancelled"}

    payload = {
        "ok": True, "intent": result.intent, "message": result.message,
        "preview": result.preview, "analysis": result.analysis,
        "elapsed_ms": int((time.time() - started) * 1000),
        "warnings": result.warnings, "engine": result.engine,
        "notes": result.notes,
        "session_id": result.session_id or req.session_id or "",
        "based_on": result.based_on,
        "changed": list(result.changed) if result.changed else None,
    }
    if result.musicxml:
        existing = body.get("score_path") or ""
        edits_open = result.intent in _EDITS_OPEN_PIECE and result.based_on != "last_piece"
        in_place = ((edits_open or result.open_score_empty) and _writable_score(existing))
        if in_place:
            xml_path = Path(existing)
            midi_path = xml_path.with_suffix(".mid")
        else:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            title = _safe_name(result.title or (result.plan.title if result.plan else "")
                               or "Motif")
            xml_path = OUT_DIR / f"{title}-{stamp}.musicxml"
            midi_path = OUT_DIR / f"{title}-{stamp}.mid"
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        xml_path.write_text(result.musicxml, encoding="utf-8")
        payload["musicxml"] = result.musicxml
        payload["musicxml_path"] = str(xml_path)
        payload["same_file"] = in_place
        if result.midi:
            midi_path.write_bytes(result.midi)
            payload["midi_path"] = str(midi_path)
            payload["midi_base64"] = base64.b64encode(result.midi).decode("ascii")
    if result.plan:
        payload["plan"] = json.loads(result.plan.to_json())
    payload["title"] = result.title or (result.plan.title if result.plan else "")
    if result.musicxml and result.session_id:
        session = state.sessions.get(result.session_id)
        session.last_file = payload.get("musicxml_path", "")
        state.sessions.save(session)
    return payload


def _writable_score(path: str) -> bool:
    """Only a MusicXML file may be written back in place.

    MuseScore reports an open score's own path, which is usually its .mscz —
    a compressed MuseScore file that must never be overwritten with MusicXML
    text. Anything that isn't plainly a MusicXML file gets a new file instead.
    """
    if not path:
        return False
    p = Path(path)
    return p.is_file() and p.suffix.lower() in (".musicxml", ".xml")


# Accidentals spelled out, so "Nocturne in E♭ major" is not saved as E major.
_SPELLED = (("𝄫", " double flat"), ("𝄪", " double sharp"), ("♭", " flat"), ("♯", " sharp"))


def _safe_name(text: str) -> str:
    for sign, word in _SPELLED:
        text = text.replace(sign, word)
    keep = "".join(c if (c.isalnum() or c in " -_") else " " for c in text)
    name = "-".join(keep.split())[:48].strip("-_")
    return name or "Motif"


def _port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def serve(port: int | None = None, host: str = "127.0.0.1", quiet: bool = False) -> None:
    cfg = ensure_config()
    port = port or int(os.environ.get("MOTIF_PORT") or cfg.get("port") or DEFAULT_PORT)
    if not _port_free(port, host):
        for candidate in range(port + 1, port + 12):
            if _port_free(candidate, host):
                port = candidate
                break
        else:
            raise SystemExit(f"no free port near {port}")
    cfg["port"] = port
    _write_config(cfg)

    state = MotifState(cfg)
    Handler.state = state
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    if not quiet:
        print(f"\n  Motif.AI {VERSION}")
        print(f"  listening on http://{host}:{port}")
        print(f"  composer: Motif ({state.quality()} care)")
        if state.model_error:
            print(f"  model:    {state.model_error}")
        print(f"  config:   {CONFIG_DIR / 'config.json'}")
        print(f"  scores:   {OUT_DIR}\n  (ctrl-c to stop)\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()
