"""Build the double-clickable launchers, one per platform.

Opening a music application should never involve a console, so macOS gets a
real .app bundle, Windows a windowless .pyw, and Linux a desktop entry.
"""
from __future__ import annotations

import plistlib
import shutil
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
    """A self-contained .app: the musician can move it anywhere — the Dock,
    Applications, a USB stick — and it still finds everything it needs,
    because everything it needs is copied inside it rather than referenced
    from wherever the zip happened to be unpacked.
    """
    app = OUT / f"{APP_NAME}.app"
    macos = app / "Contents" / "MacOS"
    res = app / "Contents" / "Resources"
    if app.exists():
        shutil.rmtree(app)
    macos.mkdir(parents=True, exist_ok=True)
    res.mkdir(parents=True, exist_ok=True)

    for name in ("engine", "plugin", "setup"):
        shutil.copytree(ROOT / name, res / name,
                        ignore=shutil.ignore_patterns(
                            "__pycache__", "*.pyc", "tests", ".pytest_cache",
                            "pytest.ini", "requirements.txt"))

    launcher = macos / "MotifSetup"
    launcher.write_text(
        '#!/bin/bash\n'
        '# Everything Setup needs lives inside this bundle, so it works no\n'
        '# matter where the app itself has been moved to.\n'
        'RES="$(cd "$(dirname "${BASH_SOURCE[0]}")/../Resources" && pwd)"\n'
        'TARGET="$RES/setup/motif_setup.py"\n'
        '\n'
        'alert() {\n'
        '  osascript -e "display alert \\"Motif Setup\\" message \\"$1\\" as critical" \\\n'
        '    >/dev/null 2>&1\n'
        '}\n'
        '\n'
        'if [ ! -f "$TARGET" ]; then\n'
        '  alert "This copy of Motif Setup looks incomplete. Please re-download '
        'it and try again."\n'
        '  exit 1\n'
        'fi\n'
        '\n'
        '# /usr/bin/python3 on a current Mac is a stub that only offers to\n'
        '# install developer tools, so each candidate is asked to actually run\n'
        '# before it is trusted.\n'
        'PY=""\n'
        'for CAND in /opt/homebrew/bin/python3 /usr/local/bin/python3 \\\n'
        '           /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \\\n'
        '           python3; do\n'
        '  if command -v "$CAND" >/dev/null 2>&1 && \\\n'
        '     "$CAND" -c "import sys" >/dev/null 2>&1; then\n'
        '    PY="$CAND"\n'
        '    break\n'
        '  fi\n'
        'done\n'
        '\n'
        'if [ -z "$PY" ]; then\n'
        '  RESP=$(osascript -e \'display alert "One more step" message "Motif '
        'needs a free component this Mac does not have yet. Choose Get it to '
        'download it, then open Motif Setup again." buttons {"Not now", "Get '
        'it"} default button "Get it"\' 2>/dev/null)\n'
        '  echo "$RESP" | grep -q "Get it" && \\\n'
        '    open "https://www.python.org/downloads/macos/"\n'
        '  exit 1\n'
        'fi\n'
        '\n'
        '"$PY" "$TARGET" "$@"\n'
        'STATUS=$?\n'
        'if [ $STATUS -ne 0 ]; then\n'
        '  alert "Setup ran into a problem. Details were saved to '
        '~/.motif/setup-log.txt. Please try again, or get in touch for help."\n'
        'fi\n'
        'exit $STATUS\n')
    _chmod_x(launcher)

    icon_ok = build_icns(res / "AppIcon.icns")
    info = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleExecutable": "MotifSetup",
        "CFBundleIdentifier": "ai.motif.setup",
        "CFBundleVersion": "2.0.0",
        "CFBundleShortVersionString": "2.0.0",
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
    """The .bat is the real Windows launcher: it can show a message box with
    no dependency on Python being installed at all, which matters because
    Windows does not ship Python — unlike a bare "python"/"pythonw" command,
    which a machine with no real interpreter silently redirects to the
    Microsoft Store instead of failing (so is never trusted here without a
    guard). The .pyw is kept for machines that already have Python properly
    associated with it, as a console-free double-click alternative.
    """
    pyw = OUT / f"{APP_NAME}.pyw"
    pyw.write_text(
        '"""Open Motif Setup on Windows, with no console window."""\n'
        "import runpy\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "here = Path(__file__).resolve().parent.parent\n"
        "sys.argv = [str(here / 'setup' / 'motif_setup.py')]\n"
        "runpy.run_path(str(here / 'setup' / 'motif_setup.py'),\n"
        "               run_name='__main__')\n")

    bat = OUT / f"{APP_NAME}.bat"
    bat.write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        "\r\n"
        'set "HERE=%~dp0.."\r\n'
        'set "TARGET=%HERE%\\setup\\motif_setup.py"\r\n'
        "\r\n"
        'if not exist "%TARGET%" goto :incomplete\r\n'
        "\r\n"
        'set "PY="\r\n'
        'py -3 -c "import sys" >nul 2>nul\r\n'
        'if not errorlevel 1 set "PY=py -3"\r\n'
        "\r\n"
        'if not defined PY (\r\n'
        '  pythonw -c "import sys" >nul 2>nul\r\n'
        '  if not errorlevel 1 set "PY=pythonw"\r\n'
        ')\r\n'
        'if not defined PY (\r\n'
        '  python -c "import sys" >nul 2>nul\r\n'
        '  if not errorlevel 1 set "PY=python"\r\n'
        ')\r\n'
        "\r\n"
        'if not defined PY goto :needpython\r\n'
        "\r\n"
        '%PY% "%TARGET%" %*\r\n'
        'if errorlevel 1 goto :problem\r\n'
        'exit /b 0\r\n'
        "\r\n"
        ":incomplete\r\n"
        'mshta "javascript:new ActiveXObject(\'WScript.Shell\').Popup(\'This '
        'copy of Motif Setup looks incomplete. Please re-download it and try '
        'again.\',0,\'Motif Setup\',48);close();"\r\n'
        'exit /b 1\r\n'
        "\r\n"
        ":needpython\r\n"
        'mshta "javascript:var s=new ActiveXObject(\'WScript.Shell\');if(s.'
        'Popup(\'Motif needs a free component this computer does not have '
        'yet. Open the download page now?\',0,\'Motif Setup\',36)==6){s.Run('
        '\'https://www.python.org/downloads/windows/\');}close();"\r\n'
        'exit /b 1\r\n'
        "\r\n"
        ":problem\r\n"
        'mshta "javascript:new ActiveXObject(\'WScript.Shell\').Popup(\'Setup '
        'ran into a problem. Details were saved to the .motif folder in your '
        'user profile. Please try again, or get in touch for help.\',0,\'Motif '
        'Setup\',48);close();"\r\n'
        'exit /b 1\r\n')
    return bat


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
        "  Windows   Motif Setup.bat   (or Motif Setup.pyw)\n"
        "  Linux     Motif Setup.command\n\n"
        "Setup adds Motif to MuseScore and sets it to start with your\n"
        "computer. Then open MuseScore and choose Motif.AI from the\n"
        "Plugins menu (in MuseScore 4 it is under Composing/arranging\n"
        "tools; if it is missing there, switch it on under Home > Plugins).\n\n"
        "Motif's composer runs entirely on your computer: no account, no\n"
        "internet connection, and nothing you write or open is ever sent\n"
        "anywhere.\n\n"
        "To remove Motif, open Setup again and choose Remove. The scores it\n"
        "wrote stay in the .motif folder in your home folder.\n")
    for p in (app, win, lin):
        print("  built", p.relative_to(ROOT))


if __name__ == "__main__":
    main()
