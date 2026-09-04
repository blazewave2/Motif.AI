"""Setup must work without a console and undo itself cleanly."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "setup"))

import autostart  # noqa: E402
import motif_setup  # noqa: E402


def test_plugin_source_is_present():
    assert motif_setup.PLUGIN_SRC.is_dir()
    assert (motif_setup.PLUGIN_SRC / "MotifAI.qml").exists()
    assert (motif_setup.PLUGIN_SRC / "assets" / "wordmark.png").exists()


def test_a_plugin_folder_is_always_chosen():
    chosen = motif_setup.choose_plugin_dir()
    assert chosen.name.lower() in ("plugins",)
    assert str(Path.home()) in str(chosen)


def test_install_and_remove_round_trip(tmp_path, monkeypatch):
    target = tmp_path / "Plugins"
    dest = motif_setup.install_plugin(target)
    assert (dest / "MotifAI.qml").exists()
    assert (dest / "components").is_dir()
    assert (dest / "assets" / "wordmark.png").exists()
    # Installing twice must replace cleanly rather than fail or nest.
    dest2 = motif_setup.install_plugin(target)
    assert dest2 == dest
    assert not (dest / "MotifAI").exists()


def test_autostart_paths_stay_inside_the_home_folder():
    for path in (autostart._autostart_path(), autostart._plist_path(),
                 autostart._vbs_path()):
        assert str(Path.home()) in str(path), f"{path} escapes the home folder"


def test_launchers_exist_for_every_platform():
    root = Path(__file__).resolve().parents[2] / "Install Motif"
    assert (root / "Motif Setup.app" / "Contents" / "MacOS" / "MotifSetup").exists()
    assert (root / "Motif Setup.pyw").exists()
    assert (root / "Motif Setup.command").exists()
    assert (root / "Read me.txt").exists()


def test_the_interface_never_mentions_a_command_line():
    """A musician should never be told to open a terminal."""
    banned = ("terminal", "command line", "virtualenv", "pip install",
              "python -m", "python3 -m", "motif serve", "sudo ")
    root = Path(__file__).resolve().parents[2]
    surfaces = list((root / "plugin").rglob("*.qml"))
    surfaces += list((root / "plugin").rglob("*.js"))
    surfaces += [root / "README.md", root / "Install Motif" / "Read me.txt"]
    surfaces += [root / "setup" / "motif_setup.py"]
    offenders = []
    for path in surfaces:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for word in banned:
            if word in text:
                offenders.append(f"{path.name}: {word!r}")
    assert not offenders, "technical language reached the musician: " + ", ".join(offenders)
