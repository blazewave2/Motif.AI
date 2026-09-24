"""Make Motif start with the computer, on any platform.

Musicians should never start a service by hand, so setup registers a per-user
login item.  Everything here is user-scoped: no administrator rights, nothing
written outside the home folder, and removal puts the machine back exactly as
it was.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

LABEL = "ai.motif.engine"
APP_NAME = "Motif"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def motif_home() -> Path:
    return Path(os.environ.get("MOTIF_HOME") or (Path.home() / ".motif"))


def source_engine_path() -> Path:
    """Where to copy the engine FROM — next to whatever is running Setup."""
    return repo_root() / "engine"


def engine_path() -> Path:
    """Where the INSTALLED engine lives — a stable, permanent location.

    This is deliberately never inside the Setup app itself: an installer is
    conventionally something you can delete once it has done its job, and if
    the login item's PYTHONPATH pointed at Setup's own bundle, deleting
    "Motif Setup.app" after installing would silently break Motif at the next
    login. ``install_engine`` below is what actually populates this path.
    """
    return motif_home() / "engine"


def install_engine() -> Path:
    """Copy the engine into its permanent home, refreshing any old copy.

    The engine is a small, pure-Python tree, so a full copy on every setup
    run is cheap and simplest: it can never drift out of sync with whatever
    version of Setup produced it.
    """
    src = source_engine_path()
    dest = engine_path()
    if src.resolve() == dest.resolve():
        return dest                      # already running from the installed copy
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".new")
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(src, tmp, ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", "tests", ".pytest_cache",
        "pytest.ini", "requirements.txt"))
    if dest.exists():
        shutil.rmtree(dest)
    tmp.rename(dest)
    return dest


def python_command() -> str:
    """The interpreter to launch with, preferring a windowless one."""
    exe = Path(sys.executable)
    if platform.system() == "Windows":
        windowless = exe.with_name("pythonw.exe")
        if windowless.exists():
            return str(windowless)
    return str(exe)


def log_path() -> Path:
    home = motif_home()
    home.mkdir(parents=True, exist_ok=True)
    return home / "motif.log"


# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------
def _launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def _plist_path() -> Path:
    return _launch_agents_dir() / f"{LABEL}.plist"


def _install_macos() -> str:
    _launch_agents_dir().mkdir(parents=True, exist_ok=True)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_command()}</string>
        <string>-m</string><string>motif</string><string>serve</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict><key>PYTHONPATH</key><string>{engine_path()}</string></dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key>
    <dict><key>SuccessfulExit</key><false/></dict>
    <key>ProcessType</key><string>Background</string>
    <key>StandardOutPath</key><string>{log_path()}</string>
    <key>StandardErrorPath</key><string>{log_path()}</string>
</dict>
</plist>
"""
    _plist_path().write_text(plist)
    # bootout first so a re-run reloads cleanly rather than erroring.
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"],
                   capture_output=True)
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(_plist_path())],
                       capture_output=True, text=True)
    if r.returncode != 0:
        # Older macOS releases only understand load/unload.
        subprocess.run(["launchctl", "unload", str(_plist_path())], capture_output=True)
        r = subprocess.run(["launchctl", "load", "-w", str(_plist_path())],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "could not register the login item")
    return str(_plist_path())


def _remove_macos() -> None:
    if _plist_path().exists():
        uid = os.getuid()
        subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"], capture_output=True)
        subprocess.run(["launchctl", "unload", str(_plist_path())], capture_output=True)
        _plist_path().unlink()


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------
def _startup_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _vbs_path() -> Path:
    return _startup_dir() / f"{APP_NAME}.vbs"


def _install_windows() -> str:
    _startup_dir().mkdir(parents=True, exist_ok=True)
    # A VBScript launcher runs the engine with no console window at all.
    script = (
        'Set shell = CreateObject("WScript.Shell")\r\n'
        f'shell.Environment("PROCESS")("PYTHONPATH") = "{engine_path()}"\r\n'
        f'shell.Run """{python_command()}"" -m motif serve", 0, False\r\n'
    )
    _vbs_path().write_text(script)
    subprocess.Popen(["wscript.exe", str(_vbs_path())],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return str(_vbs_path())


def _remove_windows() -> None:
    if _vbs_path().exists():
        _vbs_path().unlink()


# ---------------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------------
def _autostart_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / f"{LABEL}.desktop"


def _install_linux() -> str:
    path = _autostart_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    exec_line = f'env PYTHONPATH="{engine_path()}" "{python_command()}" -m motif serve'
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Your AI composing partner\n"
        f"Exec={exec_line}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "NoDisplay=true\n")
    return str(path)


def _remove_linux() -> None:
    if _autostart_path().exists():
        _autostart_path().unlink()


# ---------------------------------------------------------------------------
def install() -> str:
    system = platform.system()
    if system == "Darwin":
        return _install_macos()
    if system == "Windows":
        return _install_windows()
    return _install_linux()


def install_starts_engine() -> bool:
    """Whether :func:`install` launches the engine itself (launchd's
    RunAtLoad on macOS, the startup script on Windows)."""
    return platform.system() in ("Darwin", "Windows")


def remove() -> None:
    system = platform.system()
    if system == "Darwin":
        _remove_macos()
    elif system == "Windows":
        _remove_windows()
    else:
        _remove_linux()


def is_installed() -> bool:
    system = platform.system()
    if system == "Darwin":
        return _plist_path().exists()
    if system == "Windows":
        return _vbs_path().exists()
    return _autostart_path().exists()


def start_now() -> bool:
    """Launch the engine immediately, detached from this process."""
    if is_running():
        return True
    env = dict(os.environ)
    env["PYTHONPATH"] = str(engine_path()) + os.pathsep + env.get("PYTHONPATH", "")
    kwargs: dict = {"env": env, "cwd": str(repo_root()),
                    "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if platform.system() == "Windows":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0) | \
                                  getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen([python_command(), "-m", "motif", "serve"], **kwargs)
    except OSError:
        return False
    return True


def is_running(timeout: float = 1.5) -> bool:
    """Ask the engine directly rather than hunting for a process."""
    import json
    import urllib.error
    import urllib.request
    home = motif_home()
    port = 8765
    cfg = home / "config.json"
    if cfg.exists():
        try:
            port = int(json.loads(cfg.read_text()).get("port", 8765))
        except (ValueError, OSError):
            pass
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/health", timeout=timeout) as r:
            return json.loads(r.read()).get("ok") is True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def stop() -> None:
    """Ask a running engine to shut down."""
    import json
    import urllib.request
    home = motif_home()
    cfg = home / "config.json"
    if not cfg.exists():
        return
    try:
        data = json.loads(cfg.read_text())
        req = urllib.request.Request(
            f"http://127.0.0.1:{data.get('port', 8765)}/shutdown", data=b"{}",
            headers={"Content-Type": "application/json",
                     "X-Motif-Token": data.get("token", "")})
        urllib.request.build_opener(
            urllib.request.ProxyHandler({})).open(req, timeout=2)
    except Exception:
        pass
