"""Opening a finished score in MuseScore, for hosts whose plugins cannot.

MuseScore 3 lets a plugin open a score file itself. MuseScore 4 does not
(its plugin API's ``readScore`` is not implemented), so the panel asks the
engine to open the file instead — with the very MuseScore that is running
the panel, whose path Qt tells the plugin, or failing that with whatever
the system opens scores with.

Only files in Motif's own scores folder are opened, and only with a program
that is a MuseScore: this is a local, token-guarded service, but it still
never runs anything it was merely told to.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

OPENABLE = (".musicxml", ".mxl", ".mscz", ".mid")

# How long a MuseScore that is going to fail (a missing library, a sandbox
# it cannot leave) takes to say so; one still running by then has started.
_SETTLE = 2.5


def is_musescore(app: str) -> bool:
    """Whether a program path is a MuseScore (MuseScore4.exe, mscore,
    mscore4portable, the mscore inside MuseScore 4.app …)."""
    name = Path(app).name.lower()
    return name.startswith(("mscore", "musescore"))


def inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except (ValueError, OSError):
        return False


def open_score(path: Path, app: str | None = None) -> tuple[bool, str]:
    """Open ``path`` in MuseScore: (whether it was handed on, how)."""
    known = bool(app) and is_musescore(app) and Path(app).exists()
    running = environment_of(app) if known and sys.platform.startswith("linux") else {}
    env = session_env(running)
    if known:
        if sys.platform == "darwin" and ".app/Contents/MacOS/" in app:
            # hand the file to the running application, as the Finder does
            bundle = app.split(".app/Contents/MacOS/")[0] + ".app"
            command = ["open", "-a", bundle, str(path)]
        else:
            command = program(app, running) + [str(path)]
        if _started(command, env):
            return True, "musescore"
    return _system_open(path, env)


# What a program needs from the desktop session to put a window on screen.
_SESSION = ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR",
            "XDG_SESSION_TYPE", "DBUS_SESSION_BUS_ADDRESS")


def session_env(running: dict[str, str]) -> dict[str, str] | None:
    """The engine's environment, with the desktop session of the MuseScore
    that asked: an engine started outside the session (from a terminal
    elsewhere, or a service) could not otherwise open a window."""
    if not running:
        return None
    env = dict(os.environ)
    env.update({k: running[k] for k in _SESSION if running.get(k)})
    return env


def program(app: str, running: dict[str, str] | None = None) -> list[str]:
    """The command that starts the MuseScore at ``app``.

    An AppImage's MuseScore lives inside the image beside an ``AppRun`` that
    finds the libraries it needs, and cannot start without it. So the image
    file the running MuseScore came from (its ``$APPIMAGE``) is started
    instead, which lives on after the MuseScore that asked has closed — or,
    failing that, the image's own AppRun.
    """
    here = Path(app).parent
    for top in (here.parent, here):
        run = top / "AppRun"
        if run.is_file():
            image = (running or {}).get("APPIMAGE", "")
            if image and os.path.isfile(image) and os.access(image, os.X_OK):
                return [image]
            return [str(run)]
    return [app]


def environment_of(app: str) -> dict[str, str]:
    """The environment of the running process whose program is ``app``
    (Linux; empty where that cannot be read)."""
    target = os.path.realpath(app)
    try:
        pids = [p for p in Path("/proc").iterdir() if p.name.isdigit()]
    except OSError:
        return {}
    for pid in pids:
        try:
            if os.path.realpath(pid / "exe") != target:
                continue
            raw = (pid / "environ").read_bytes()
        except OSError:
            continue
        env = {}
        for item in raw.split(b"\0"):
            key, eq, value = item.partition(b"=")
            if eq:
                env[os.fsdecode(key)] = os.fsdecode(value)
        return env
    return {}


def _system_open(path: Path, env: dict[str, str] | None = None) -> tuple[bool, str]:
    if sys.platform == "darwin":
        return (True, "system") if _started(["open", str(path)]) else \
            (False, "no program to open scores with")
    if os.name == "nt":
        os.startfile(str(path))          # type: ignore[attr-defined]
        return True, "system"
    opener = shutil.which("xdg-open")
    if opener and _started([opener, str(path)], env):
        return True, "system"
    return False, "no program to open scores with"


def _started(command: list[str], env: dict[str, str] | None = None) -> bool:
    """Start a program that outlives the request and the engine, and say
    whether it got going: still running after a moment, or finished cleanly
    (having handed the file to a copy already open)."""
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200   # detached, new group
    else:
        kwargs["start_new_session"] = True
    if env is not None:
        kwargs["env"] = env
    try:
        child = subprocess.Popen(command, **kwargs)
    except OSError:
        return False
    try:
        return child.wait(timeout=_SETTLE) == 0
    except subprocess.TimeoutExpired:
        # collect it when it closes, so it never lingers as a zombie
        threading.Thread(target=child.wait, daemon=True).start()
        return True
