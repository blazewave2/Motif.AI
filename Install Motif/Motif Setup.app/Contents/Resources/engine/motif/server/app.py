"""The local Motif service the MuseScore plugin talks to.

Deliberately built on the standard library: a musician installing a MuseScore
plugin should not have to create a virtualenv.  Optional extras (a trained
model, an LLM planner) are loaded only if they are present.
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

from ..agent.agent import MotifAgent, Request
from ..compose.orchestration import ENSEMBLES
from ..compose.styles import STYLES

VERSION = "1.0.0"
DEFAULT_PORT = 8765
MAX_BODY = 32 * 1024 * 1024        # 32 MB: large orchestral scores round-trip

CONFIG_DIR = Path(os.environ.get("MOTIF_HOME") or (Path.home() / ".motif"))
OUT_DIR = CONFIG_DIR / "scores"


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
    cfg.setdefault("port", DEFAULT_PORT)
    cfg.setdefault("model_path", "")
    cfg.setdefault("anthropic_api_key", "")
    cfg.setdefault("planner", "auto")
    if changed or not path.exists():
        path.write_text(json.dumps(cfg, indent=2))
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return cfg


class MotifState:
    """Process-wide singletons: the agent, the optional model, the config."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.model = None
        self.model_error = ""
        self.planner = None
        self.planner_name = "heuristic"
        self.lock = threading.Lock()
        self.progress_text = ""
        self._load_model()
        self._load_planner()
        self.agent = MotifAgent(model=self.model, planner=self.planner)

    def _load_model(self) -> None:
        # A checkpoint dropped into the Motif folder is picked up with no
        # configuration at all: download it, put it there, restart. That is
        # the whole install step for the trained composer.
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

    def _load_planner(self) -> None:
        mode = self.cfg.get("planner", "auto")
        if mode == "off":
            return
        key = (self.cfg.get("anthropic_api_key")
               or os.environ.get("ANTHROPIC_API_KEY", ""))
        if not key:
            return
        try:
            from ..agent.llm_planner import LLMPlanner
            self.planner = LLMPlanner(api_key=key)
            self.planner_name = "claude"
        except Exception:
            self.planner = None


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
        return json.loads(raw.decode("utf-8"))

    # -- routes -----------------------------------------------------------
    def do_GET(self) -> None:
        route = urlparse(self.path).path.rstrip("/") or "/"
        if route == "/health":
            return self._json(200, {
                "ok": True, "service": "motif", "version": VERSION,
                "model_loaded": self.state.model is not None,
                "model_error": self.state.model_error,
                "planner": self.state.planner_name,
                "engine": "symbolic+neural" if self.state.model else "symbolic",
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
            # Polled while the panel is waiting, so the musician sees what
            # Motif is actually doing rather than a generic spinner.
            return self._json(200, {"ok": True, "text": self.state.progress_text})
        return self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        route = urlparse(self.path).path.rstrip("/") or "/"
        if not self._authorised():
            return self._json(401, {"ok": False, "error": "unauthorised"})
        try:
            body = self._read_body()
        except ValueError as exc:
            return self._json(400, {"ok": False, "error": str(exc)})
        except json.JSONDecodeError:
            return self._json(400, {"ok": False, "error": "invalid JSON body"})

        if route == "/compose":
            return self._compose(body)
        if route == "/plan":
            return self._plan(body)
        if route == "/preferences":
            return self._preferences(body)
        if route == "/shutdown":
            threading.Timer(0.2, self.server.shutdown).start()
            return self._json(200, {"ok": True, "message": "shutting down"})
        return self._json(404, {"ok": False, "error": "not found"})

    # -- handlers ---------------------------------------------------------
    def _compose(self, body: dict) -> None:
        prompt = (body.get("prompt") or "").strip()
        if not prompt:
            return self._json(400, {"ok": False, "error": "prompt is required"})
        # Neither the composer nor the instrumentation is ever taken from a
        # stored preference — only ever from what the musician actually typed
        # in the prompt, or an explicit override passed by a caller (the
        # CLI's --style/--ensemble flags, for instance). When a score is open
        # and neither is named, the agent matches what is already on the page.
        req = Request(
            prompt=prompt[:4000],
            score_xml=body.get("score_xml") or None,
            score_path=body.get("score_path") or None,
            seed=body.get("seed"),
            style=body.get("style") or None,
            ensemble=body.get("ensemble") or None,
            history=body.get("history") or [],
            use_model=bool(body.get("use_model", True)))
        started = time.time()
        with self.state.lock:
            self.state.progress_text = ""
            try:
                result = self.state.agent.run(
                    req, progress=lambda text: setattr(self.state, "progress_text", text))
            finally:
                self.state.progress_text = ""
        if not result.ok:
            return self._json(200, {"ok": False, "error": result.error,
                                    "message": result.message,
                                    "detail": result.analysis})

        payload = {
            "ok": True, "intent": result.intent, "message": result.message,
            "preview": result.preview, "analysis": result.analysis,
            "elapsed_ms": int((time.time() - started) * 1000),
            "warnings": result.warnings,
        }
        if result.musicxml:
            # A continuation, development, harmonisation or edit is a change
            # to the piece the musician already has open — it belongs back
            # in that same file, not in a new one they'd have to go find.
            # A "create" is a genuinely new, unrelated piece even when a
            # score happens to be open, so it always gets its own file.
            existing_path = body.get("score_path") or ""
            # A blank score the musician just opened is where they are
            # working: a new piece belongs on that empty page, not in a
            # second tab beside it.
            edits_open_piece = result.intent in ("continue", "develop", "harmonize", "edit")
            in_place = ((edits_open_piece or result.open_score_empty)
                       and existing_path and Path(existing_path).is_file())
            if in_place:
                xml_path = Path(existing_path)
                midi_path = xml_path.with_suffix(".mid")
            else:
                stamp = time.strftime("%Y%m%d-%H%M%S")
                title = _safe_name(result.plan.title if result.plan else "Motif")
                xml_path = OUT_DIR / f"{title}-{stamp}.musicxml"
                midi_path = OUT_DIR / f"{title}-{stamp}.mid"
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
            payload["title"] = result.plan.title
        return self._json(200, payload)

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
            (CONFIG_DIR / "config.json").write_text(json.dumps(self.state.cfg, indent=2))
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


def _safe_name(text: str) -> str:
    keep = "".join(c if (c.isalnum() or c in " -_") else "" for c in text).strip()
    return (keep or "Motif").replace(" ", "-")[:48]


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
    (CONFIG_DIR / "config.json").write_text(json.dumps(cfg, indent=2))

    state = MotifState(cfg)
    Handler.state = state
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    if not quiet:
        engine = "symbolic + neural" if state.model else "symbolic"
        print(f"\n  Motif.ai {VERSION}")
        print(f"  listening on http://{host}:{port}")
        print(f"  engine:  {engine}")
        print(f"  planner: {state.planner_name}")
        if state.model_error:
            print(f"  model:   {state.model_error}")
        print(f"  config:  {CONFIG_DIR / 'config.json'}")
        print(f"  scores:  {OUT_DIR}\n  (ctrl-c to stop)\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()
