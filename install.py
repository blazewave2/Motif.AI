#!/usr/bin/env python3
"""Install Motif.AI into MuseScore.

Copies the plugin into MuseScore's plugin folder and prepares the engine's
config, so the panel finds the service with nothing for you to type.

    python3 install.py              # install
    python3 install.py --link       # symlink instead (for development)
    python3 install.py --uninstall
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_SRC = HERE / "plugin" / "MotifAI"
PLUGIN_NAME = "MotifAI"


def candidate_plugin_dirs() -> list[Path]:
    """Where MuseScore looks for plugins, newest version first."""
    home = Path.home()
    system = platform.system()
    out: list[Path] = []
    if system == "Windows":
        docs = Path(os.environ.get("USERPROFILE", home)) / "Documents"
        for v in ("MuseScore4", "MuseScore3"):
            out.append(docs / v / "Plugins")
    elif system == "Darwin":
        for v in ("MuseScore4", "MuseScore3"):
            out.append(home / "Documents" / v / "Plugins")
    else:
        for v in ("MuseScore4", "MuseScore3"):
            out.append(home / "Documents" / v / "Plugins")
        out.append(home / ".local" / "share" / "MuseScore" / "MuseScore4" / "plugins")
        out.append(home / ".local" / "share" / "MuseScore" / "MuseScore3" / "plugins")
    return out


def choose_target(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    existing = [d for d in candidate_plugin_dirs() if d.exists()]
    if existing:
        return existing[0]
    # Nothing found: create the most likely location rather than failing.
    return candidate_plugin_dirs()[0]


def install(target_dir: Path, link: bool) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / PLUGIN_NAME
    if dest.exists() or dest.is_symlink():
        if dest.is_symlink():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    if link:
        dest.symlink_to(PLUGIN_SRC, target_is_directory=True)
    else:
        shutil.copytree(PLUGIN_SRC, dest)
    return dest


def prepare_engine_config() -> Path:
    sys.path.insert(0, str(HERE / "engine"))
    from motif.server.app import CONFIG_DIR, ensure_config
    ensure_config()
    return CONFIG_DIR / "config.json"


def main() -> int:
    ap = argparse.ArgumentParser(description="install Motif.AI into MuseScore")
    ap.add_argument("--dir", help="MuseScore plugin folder (auto-detected by default)")
    ap.add_argument("--link", action="store_true",
                    help="symlink the plugin instead of copying it")
    ap.add_argument("--uninstall", action="store_true")
    args = ap.parse_args()

    if not PLUGIN_SRC.exists():
        print(f"error: plugin source not found at {PLUGIN_SRC}", file=sys.stderr)
        return 1

    target_dir = choose_target(args.dir)

    if args.uninstall:
        removed = 0
        for d in ([Path(args.dir).expanduser()] if args.dir else candidate_plugin_dirs()):
            dest = d / PLUGIN_NAME
            if dest.is_symlink():
                dest.unlink()
                removed += 1
            elif dest.exists():
                shutil.rmtree(dest)
                removed += 1
        print(f"removed {removed} installation(s)")
        return 0

    dest = install(target_dir, args.link)
    cfg = prepare_engine_config()
    token = json.loads(cfg.read_text()).get("token", "")

    print(f"""
  Motif.AI installed

    plugin   {dest}
    config   {cfg}
    token    {token[:8]}…  (the panel reads this automatically)

  Next:

    1. Start the engine:      {HERE / 'scripts' / 'motif-serve'}
       (Windows)              {HERE / 'scripts' / 'motif-serve.bat'}

    2. In MuseScore:          Plugins ▸ Manage plugins… ▸ enable "Motif.AI"
                              then Plugins ▸ Motif.AI

  The engine listens on 127.0.0.1 only and never sends your music anywhere.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
