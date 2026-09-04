"""Motif Setup — the only thing a musician ever has to open.

Installs the panel into MuseScore, arranges for Motif to start with the
computer, and starts it now.  Presented as a small window rather than a
console, because setting up a music app should not look like maintenance.
"""
from __future__ import annotations

import platform
import shutil
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

import autostart  # noqa: E402

APP = "Motif"
ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SRC = ROOT / "plugin" / "MotifAI"
PLUGIN_NAME = "MotifAI"
LOG_PATH = Path.home() / ".motif" / "setup-log.txt"

BG = "#16181C"
SURFACE = "#22262C"
BORDER = "#2E333A"
TEXT = "#F2F4F7"
MUTED = "#A7AFBC"
FAINT = "#6C7583"
GOLD = "#D8C48F"
INK = "#12141A"
DANGER = "#E0776B"
OK_GREEN = "#7FBF8A"


# ---------------------------------------------------------------------------
# The work itself, independent of how it is presented
# ---------------------------------------------------------------------------
def musescore_plugin_dirs() -> list[Path]:
    home = Path.home()
    system = platform.system()
    out: list[Path] = []
    if system == "Windows":
        import os
        docs = Path(os.environ.get("USERPROFILE", home)) / "Documents"
        out += [docs / v / "Plugins" for v in ("MuseScore4", "MuseScore3")]
    elif system == "Darwin":
        out += [home / "Documents" / v / "Plugins" for v in ("MuseScore4", "MuseScore3")]
    else:
        out += [home / "Documents" / v / "Plugins" for v in ("MuseScore4", "MuseScore3")]
        out += [home / ".local" / "share" / "MuseScore" / v / "plugins"
                for v in ("MuseScore4", "MuseScore3")]
    return out


def choose_plugin_dir() -> Path:
    existing = [d for d in musescore_plugin_dirs() if d.exists()]
    return existing[0] if existing else musescore_plugin_dirs()[0]


def install_plugin(target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / PLUGIN_NAME
    if dest.is_symlink():
        dest.unlink()
    elif dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(PLUGIN_SRC, dest)
    return dest


def prepare_config() -> Path:
    from motif.server.app import CONFIG_DIR, ensure_config
    ensure_config()
    return CONFIG_DIR / "config.json"


def run_install(report) -> bool:
    """Perform the whole setup, reporting progress through ``report``."""
    report("Installing the Motif panel…", 0.10)
    dest = install_plugin(choose_plugin_dir())

    # Copied to a permanent, per-user location rather than run from wherever
    # Setup itself happens to be sitting — Setup is an installer, and an
    # installer is something you should be able to delete once it has done
    # its job without breaking the thing it installed.
    report("Installing the Motif engine…", 0.25)
    autostart.install_engine()

    report("Preparing your Motif folder…", 0.40)
    prepare_config()

    report("Setting Motif to start with your computer…", 0.55)
    try:
        autostart.install()
    except (OSError, RuntimeError) as exc:
        report(f"Could not set Motif to start automatically ({exc}).", 0.55)

    report("Waking Motif…", 0.75)
    autostart.start_now()
    for _ in range(24):
        if autostart.is_running(0.7):
            report("Motif is ready.", 1.0)
            return True
        time.sleep(0.4)
    report("Motif is installed, but it hasn’t answered yet.", 1.0)
    return False


def run_remove(report) -> None:
    report("Stopping Motif…", 0.2)
    autostart.stop()
    report("Removing the login item…", 0.4)
    autostart.remove()
    report("Removing the panel…", 0.6)
    for d in musescore_plugin_dirs():
        dest = d / PLUGIN_NAME
        if dest.is_symlink():
            dest.unlink()
        elif dest.exists():
            shutil.rmtree(dest)
    report("Removing the installed engine…", 0.85)
    engine_dir = autostart.engine_path()
    if engine_dir.exists() and engine_dir.is_relative_to(autostart.motif_home()):
        shutil.rmtree(engine_dir, ignore_errors=True)
    report("Motif has been removed.", 1.0)


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------
def run_window() -> int:
    import tkinter as tk
    from tkinter import font as tkfont

    win = tk.Tk()
    win.title(f"{APP} Setup")
    win.configure(bg=BG)
    win.resizable(False, False)
    W, H = 460, 430
    win.update_idletasks()
    x = (win.winfo_screenwidth() - W) // 2
    y = (win.winfo_screenheight() - H) // 3
    win.geometry(f"{W}x{H}+{max(0, x)}+{max(0, y)}")

    serif = _first_font(tkfont, ["Georgia", "Palatino", "Times New Roman", "DejaVu Serif"])
    sans = _first_font(tkfont, ["Inter", "Segoe UI", "Helvetica Neue", "DejaVu Sans"])

    # -- wordmark ---------------------------------------------------------
    logo_holder = tk.Frame(win, bg=BG, height=96)
    logo_holder.pack(fill="x", pady=(34, 0))
    logo_holder.pack_propagate(False)
    photo = _load_logo(tk)
    if photo is not None:
        tk.Label(logo_holder, image=photo, bg=BG, borderwidth=0).pack()
        logo_holder.image = photo               # keep a reference alive
    else:
        tk.Label(logo_holder, text="Motif.AI", bg=BG, fg=TEXT,
                 font=(serif, 30)).pack()

    tk.Label(win, text="Your AI composing partner", bg=BG, fg=MUTED,
             font=(sans, 11)).pack(pady=(2, 0))

    status = tk.Label(win, text="", bg=BG, fg=MUTED, font=(sans, 11),
                      wraplength=380, justify="center", height=3)
    status.pack(pady=(26, 0), padx=40, fill="x")

    # -- progress ---------------------------------------------------------
    bar = tk.Canvas(win, height=4, bg=SURFACE, highlightthickness=0, width=300)
    bar.pack(pady=(2, 0))
    fill = bar.create_rectangle(0, 0, 0, 4, fill=GOLD, width=0)

    def set_progress(fraction: float) -> None:
        bar.coords(fill, 0, 0, max(0, min(1.0, fraction)) * 300, 4)

    # -- buttons ----------------------------------------------------------
    buttons = tk.Frame(win, bg=BG)
    buttons.pack(pady=(28, 0))

    primary = tk.Label(buttons, text="Install", bg=GOLD, fg=INK,
                       font=(sans, 12, "bold"), padx=34, pady=11, cursor="hand2")
    primary.grid(row=0, column=0, padx=6)

    secondary = tk.Label(buttons, text="Remove", bg=SURFACE, fg=MUTED,
                         font=(sans, 11), padx=20, pady=11, cursor="hand2")
    secondary.grid(row=0, column=1, padx=6)

    footer = tk.Label(win, text="", bg=BG, fg=FAINT, font=(sans, 9),
                      wraplength=400, justify="center")
    footer.pack(side="bottom", pady=(0, 16))

    state = {"busy": False}

    def report(message: str, fraction: float) -> None:
        win.after(0, lambda: (status.config(text=message), set_progress(fraction)))

    def finish(ok: bool, removed: bool = False) -> None:
        state["busy"] = False
        if removed:
            primary.config(text="Install", bg=GOLD, fg=INK)
            footer.config(text="")
            return
        primary.config(text="Done", bg=OK_GREEN if ok else SURFACE,
                       fg=INK if ok else TEXT)
        footer.config(
            text=("Open MuseScore, then choose Motif.AI from the Plugins menu."
                  if ok else
                  "Motif is installed. If the panel stays quiet, open this "
                  "window again and choose Repair."))

    def work(fn, removed=False):
        if state["busy"]:
            return
        state["busy"] = True
        primary.config(text="Working…", bg=SURFACE, fg=MUTED)
        secondary.config(fg=FAINT)

        def run():
            try:
                ok = fn(report) is not False
            except Exception as exc:                   # never leave a dead window
                report(f"Something went wrong: {exc}", 1.0)
                ok = False
            win.after(0, lambda: finish(ok, removed))
        threading.Thread(target=run, daemon=True).start()

    primary.bind("<Button-1>", lambda e: work(run_install))
    secondary.bind("<Button-1>", lambda e: work(run_remove, removed=True))
    for widget, base in ((primary, GOLD), (secondary, SURFACE)):
        widget.bind("<Enter>", lambda e, w=widget, b=base:
                    w.config(bg=_lighten(b)) if not state["busy"] else None)
        widget.bind("<Leave>", lambda e, w=widget, b=base:
                    w.config(bg=b) if not state["busy"] else None)

    # -- opening state ----------------------------------------------------
    if autostart.is_running(0.6):
        status.config(text="Motif is installed and ready.")
        primary.config(text="Repair")
        set_progress(1.0)
        footer.config(text="Open MuseScore, then choose Motif.AI from the Plugins menu.")
    elif autostart.is_installed():
        status.config(text="Motif is installed but not running.")
        primary.config(text="Repair")
    else:
        status.config(text="Motif will be added to MuseScore and set to start "
                            "with your computer.")

    win.mainloop()
    return 0


def _first_font(tkfont, names):
    try:
        available = set(tkfont.families())
    except Exception:
        return names[-1]
    for n in names:
        if n in available:
            return n
    return names[-1]


def _load_logo(tk):
    for name in ("wordmark.png", "wordmark@2x.png"):
        path = PLUGIN_SRC / "assets" / name
        if not path.exists():
            continue
        try:
            image = tk.PhotoImage(file=str(path))
            # Tk can only scale by whole factors; the 900px asset reduces to a
            # comfortable 300px at a third.
            return image.subsample(3, 3)
        except Exception:
            continue
    return None


def _lighten(colour: str) -> str:
    c = colour.lstrip("#")
    rgb = [min(255, int(c[i:i + 2], 16) + 16) for i in (0, 2, 4)]
    return "#%02X%02X%02X" % tuple(rgb)


# ---------------------------------------------------------------------------
# Making sure the user always sees *something*
#
# A double-clicked app has nowhere for printed text to appear: anything
# written to stdout is invisible, and a process that raises and exits just
# looks like it "bounced once and quit" with no explanation. Every path
# below ends in either a real window or a native OS dialog box — never a
# bare print.
# ---------------------------------------------------------------------------
def _log(text: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(text.rstrip("\n") + "\n")
    except OSError:
        pass


def _log_error(exc: BaseException) -> None:
    import traceback
    _log(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
    _log("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))


def _native_alert(title: str, message: str, error: bool = False) -> None:
    """Show a plain OS dialog with no dependency on tkinter or on Python's
    own GUI stack — this is the path taken precisely when that stack has
    already failed, so it cannot lean on it either."""
    system = platform.system()
    _log(f"[alert] {title}: {message}")
    try:
        if system == "Darwin":
            import subprocess
            script = (f'display dialog {_applescript_str(message)} '
                     f'with title {_applescript_str(title)} '
                     f'buttons {{"OK"}} default button "OK" '
                     f'{"with icon caution" if error else ""}')
            subprocess.run(["osascript", "-e", script],
                           capture_output=True, timeout=30)
            return
        if system == "Windows":
            import ctypes
            flags = 0x40 if not error else 0x10   # information / error icon
            ctypes.windll.user32.MessageBoxW(0, message, title, flags)
            return
        import subprocess
        for cmd in (["zenity", "--info" if not error else "--error",
                    f"--title={title}", f"--text={message}"],
                   ["kdialog", "--msgbox" if not error else "--error", message,
                    "--title", title],
                   ["notify-send", title, message]):
            try:
                if subprocess.run(cmd, capture_output=True, timeout=30).returncode == 0:
                    return
            except (OSError, FileNotFoundError):
                continue
    except Exception as exc:                       # the alert itself must never crash setup
        _log_error(exc)


def _applescript_str(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def run_console(argv: list[str]) -> int:
    """Used when the machine has no windowing toolkit at all — still prints,
    for the case where this is genuinely being run by hand rather than by
    double-clicking."""
    action = "remove" if "--remove" in argv else "install"

    def report(message, fraction):
        print(f"  {message}")

    print(f"\n  {APP} Setup\n")
    if action == "remove":
        run_remove(report)
        print("\n  Removed.\n")
        return 0
    ok = run_install(report)
    print("\n  Open MuseScore, then choose Motif.AI from the Plugins menu.\n"
          if ok else "\n  Installed. Open this again and choose Repair if needed.\n")
    return 0 if ok else 1


def _run_headless(want_remove: bool) -> int:
    """The graphical window could not be shown — do the real work anyway,
    and report the outcome through a native dialog rather than print(),
    which nobody double-clicking an app will ever see."""
    def report(message, fraction):
        _log(message)
    try:
        if want_remove:
            run_remove(report)
            _native_alert(f"{APP} Setup", "Motif has been removed.")
            return 0
        ok = run_install(report)
        if ok:
            _native_alert(f"{APP} Setup",
                "Motif is installed and ready.\n\n"
                "Open MuseScore, then choose Motif.AI from the Plugins menu.")
        else:
            _native_alert(f"{APP} Setup",
                "Motif is installed, but hasn\u2019t answered yet.\n\n"
                "Open this again in a moment and choose Repair if it still "
                "hasn\u2019t.")
        return 0 if ok else 1
    except Exception as exc:
        _log_error(exc)
        _native_alert(
            f"{APP} Setup",
            "Something went wrong during setup. Details were saved to\n"
            f"{LOG_PATH}\n\nPlease try again, or get in touch for help.",
            error=True)
        return 1


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    want_remove = "--remove" in argv
    if "--console" in argv:
        return run_console(argv)

    try:
        import tkinter  # noqa: F401
    except Exception as exc:
        _log_error(exc)
        return _run_headless(want_remove)

    try:
        return run_window()
    except SystemExit:
        raise
    except Exception as exc:
        # tk.Tk() itself is where a broken Tcl/Tk installation fails — this
        # is common on a system Python that was never given a working Tk
        # framework — and it fails before any install work has started, so
        # falling back to the headless path here can never double-install.
        _log_error(exc)
        return _run_headless(want_remove)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as exc:                    # the true last resort
        _log_error(exc)
        _native_alert(f"{APP} Setup",
                     "Setup could not start. Details were saved to\n"
                     f"{LOG_PATH}\n\nPlease try again, or get in touch for help.",
                     error=True)
        raise SystemExit(1)
