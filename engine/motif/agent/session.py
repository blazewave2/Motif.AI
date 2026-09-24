"""What Motif remembers of a conversation.

A composer sitting beside you remembers what you asked for and what they
wrote. Each conversation in the panel is a session: its turns, and the last
piece written in it — kept in Motif Score Notation, with its plan — so "make
the middle darker" knows which piece and which middle. Sessions are small
JSON files in the Motif folder, and only the most recent are kept.
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

KEEP = 40                 # sessions kept on disk
MAX_TURNS = 60            # turns kept per session


@dataclass
class Session:
    id: str
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    title: str = ""
    history: list[dict] = field(default_factory=list)
    piece_msn: str = ""
    plan: dict | None = None
    last_file: str = ""

    def add(self, role: str, text: str, **extra) -> None:
        self.history.append({"role": role, "text": text[:6000], "time": time.time(), **extra})
        self.history = self.history[-MAX_TURNS:]
        self.updated = time.time()


class SessionStore:
    def __init__(self, folder: Path | None):
        self.folder = folder
        self._mem: dict[str, Session] = {}
        self._lock = threading.Lock()
        if folder is not None:
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError:
                self.folder = None

    def get(self, sid: str | None) -> Session:
        sid = _safe_id(sid) or f"s{int(time.time() * 1000)}"
        with self._lock:
            if sid in self._mem:
                return self._mem[sid]
            s = self._load(sid) or Session(id=sid)
            self._mem[sid] = s
            return s

    def save(self, session: Session) -> None:
        with self._lock:
            self._mem[session.id] = session
            if self.folder is None:
                return
            try:
                path = self.folder / f"{session.id}.json"
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(asdict(session)), encoding="utf-8")
                tmp.replace(path)
                self._prune()
            except OSError:
                pass

    def _load(self, sid: str) -> Session | None:
        if self.folder is None:
            return None
        path = self.folder / f"{sid}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        known = {k: v for k, v in data.items() if k in Session.__dataclass_fields__}
        try:
            return Session(**known)
        except TypeError:
            return None

    def _prune(self) -> None:
        files = sorted(self.folder.glob("*.json"), key=lambda p: p.stat().st_mtime)
        for old in files[:-KEEP]:
            try:
                old.unlink()
            except OSError:
                pass


def _safe_id(sid: str | None) -> str:
    if not sid:
        return ""
    return re.sub(r"[^A-Za-z0-9_-]", "", str(sid))[:64]
