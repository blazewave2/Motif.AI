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
    report("Installing the Motif panel…", 0.15)
    dest = install_plugin(choose_plugin_dir())

    report("Preparing your Motif folder…", 0.35)
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
    report("Removing the login item…", 0.5)
    autostart.remove()
    report("Removing the panel…", 0.8)
    for d in musescore_plugin_dirs():
        dest = d / PLUGIN_NAME
        if dest.is_symlink():
            dest.unlink()
        elif dest.exists():
            shutil.rmtree(dest)
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
def run_console(argv: list[str]) -> int:
    """Used when the machine has no windowing toolkit available."""
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


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--console" in argv or "--remove" in argv:
        return run_console(argv)
    try:
        import tkinter  # noqa: F401
    except ImportError:
        return run_console(argv)
    try:
        return run_window()
    except Exception:
        return run_console(argv)


if __name__ == "__main__":
    raise SystemExit(main())
