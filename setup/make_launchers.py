"""Build the double-clickable launchers, one per platform.

Opening a music application should never involve a console, so macOS gets a
real .app bundle, Windows a windowless .pyw, and Linux a desktop entry.
"""
from __future__ import annotations

import plistlib
import struct
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Install Motif"
ASSETS = ROOT / "plugin" / "MotifAI" / "assets"
APP_NAME = "Motif Setup"


def _chmod_x(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def build_icns(dest: Path) -> bool:
    """Pack the app icons into an .icns container."""
    entries = [("ic07", ASSETS / "icon-128.png"),
               ("ic08", ASSETS / "icon-256.png"),
               ("ic09", ASSETS / "icon-512.png")]
    chunks = b""
    for code, png in entries:
        if not png.exists():
            continue
        data = png.read_bytes()
        chunks += code.encode("ascii") + struct.pack(">I", len(data) + 8) + data
    if not chunks:
        return False
    dest.write_bytes(b"icns" + struct.pack(">I", len(chunks) + 8) + chunks)
    return True


def build_macos_app() -> Path:
    app = OUT / f"{APP_NAME}.app"
    macos = app / "Contents" / "MacOS"
    res = app / "Contents" / "Resources"
    macos.mkdir(parents=True, exist_ok=True)
    res.mkdir(parents=True, exist_ok=True)

    launcher = macos / "MotifSetup"
    launcher.write_text(
        '#!/bin/bash\n'
        '# Locate the Motif folder relative to this bundle and open Setup.\n'
        'HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"\n'
        '\n'
        '# /usr/bin/python3 on a current Mac is a stub that only offers to\n'
        '# install developer tools, so each candidate is asked to actually run\n'
        '# before it is trusted.\n'
        'for PY in /opt/homebrew/bin/python3 /usr/local/bin/python3 \\\n'
        '         /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \\\n'
        '         python3; do\n'
        '  if command -v "$PY" >/dev/null 2>&1 && \\\n'
        '     "$PY" -c "import sys" >/dev/null 2>&1; then\n'
        '    exec "$PY" "$HERE/setup/motif_setup.py" "$@"\n'
        '  fi\n'
        'done\n'
        '\n'
        'osascript -e \'display alert "One more step" message "Motif needs a '
        'free component this Mac does not have yet. Choose Get it to download '
        'it, then open Motif Setup again." buttons {"Not now", "Get it"} '
        'default button "Get it"\' \\\n'
        '  | grep -q "Get it" && open "https://www.python.org/downloads/macos/"\n')
    _chmod_x(launcher)

    icon_ok = build_icns(res / "AppIcon.icns")
    info = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleExecutable": "MotifSetup",
        "CFBundleIdentifier": "ai.motif.setup",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundlePackageType": "APPL",
        "LSMinimumSystemVersion": "10.13",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.music",
    }
    if icon_ok:
        info["CFBundleIconFile"] = "AppIcon"
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps(info))
    return app


def build_windows() -> Path:
    # A .pyw file is opened by pythonw, which shows no console window at all.
    path = OUT / f"{APP_NAME}.pyw"
    path.write_text(
        '"""Open Motif Setup on Windows, with no console window."""\n'
        "import runpy\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "here = Path(__file__).resolve().parent.parent\n"
        "sys.argv = [str(here / 'setup' / 'motif_setup.py')]\n"
        "runpy.run_path(str(here / 'setup' / 'motif_setup.py'),\n"
        "               run_name='__main__')\n")
    # A .bat fallback for machines where .pyw is not associated.
    bat = OUT / f"{APP_NAME}.bat"
    bat.write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        'set HERE=%~dp0..\r\n'
        'start "" pythonw "%HERE%\\setup\\motif_setup.py"\r\n'
        "if errorlevel 1 python \"%HERE%\\setup\\motif_setup.py\"\r\n")
    return path


def build_linux() -> Path:
    path = OUT / f"{APP_NAME}.desktop"
    icon = ASSETS / "icon-256.png"
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Install Motif.AI into MuseScore\n"
        f"Exec=python3 \"{ROOT / 'setup' / 'motif_setup.py'}\"\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=AudioVideo;Audio;Music;\n")
    _chmod_x(path)
    # Double-clicking a .command opens it directly on desktops that ignore
    # .desktop files outside the applications folder.
    cmd = OUT / f"{APP_NAME}.command"
    cmd.write_text(
        '#!/bin/bash\n'
        'HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"\n'
        'exec python3 "$HERE/setup/motif_setup.py" "$@"\n')
    _chmod_x(cmd)
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    app = build_macos_app()
    win = build_windows()
    lin = build_linux()
    (OUT / "Read me.txt").write_text(
        "Motif.AI\n"
        "========\n\n"
        "Double-click the item for your computer:\n\n"
        "  macOS     Motif Setup.app\n"
        "  Windows   Motif Setup.pyw   (or Motif Setup.bat)\n"
        "  Linux     Motif Setup.command\n\n"
        "Setup adds Motif to MuseScore and sets it to start with your\n"
        "computer. Then open MuseScore and choose Motif.AI from the\n"
        "Plugins menu.\n\n"
        "To remove Motif, open Setup again and choose Remove.\n")
    for p in (app, win, lin):
        print("  built", p.relative_to(ROOT))


if __name__ == "__main__":
    main()
