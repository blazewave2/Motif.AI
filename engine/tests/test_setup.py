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


def test_every_musescore_gets_the_panel(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(motif_setup.platform, "system", lambda: "Linux")
    assert motif_setup.choose_plugin_dirs() == [tmp_path / "Documents" / "MuseScore4" / "Plugins"]
    ms3 = tmp_path / ".local" / "share" / "MuseScore" / "MuseScore3" / "plugins"
    ms4 = tmp_path / "Documents" / "MuseScore4" / "Plugins"
    ms3.mkdir(parents=True)
    ms4.mkdir(parents=True)
    assert motif_setup.choose_plugin_dirs() == [ms4, ms3]


def test_musescore_4_has_the_panel_switched_on(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(motif_setup.platform, "system", lambda: "Linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    config = motif_setup.musescore4_extensions_config()
    # MuseScore 4 never opened: nothing to switch on, nothing written
    assert motif_setup.enable_in_musescore4() is False
    assert not config.exists()
    config.parent.mkdir(parents=True)
    others = [{"actions": [], "uri": "musescore://extensions/colornotes"}]
    config.write_text(json.dumps(others))
    assert motif_setup.enable_in_musescore4() is True
    entries = json.loads(config.read_text())
    assert entries[0] == others[0]
    assert {"actions": [{"code": "main", "exec_point": "manually"}],
            "uri": "musescore://extensions/v1/motifai/motifai.qml"} in entries
    # switched off again by hand, then repaired: on again, still listed once
    entries[-1]["actions"] = []
    config.write_text(json.dumps(entries))
    assert motif_setup.enable_in_musescore4() is True
    entries = json.loads(config.read_text())
    assert len(entries) == 2 and entries[-1]["actions"]
    motif_setup.forget_in_musescore4()
    assert json.loads(config.read_text()) == others
    # a file MuseScore writes differently is left alone
    config.write_text('{"extensions": {}}')
    assert motif_setup.enable_in_musescore4() is False
    assert config.read_text() == '{"extensions": {}}'


def test_musescore_3_has_the_panel_ticked(tmp_path, monkeypatch):
    import xml.etree.ElementTree as ET
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(motif_setup.platform, "system", lambda: "Linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    folder = tmp_path / "Documents" / "MuseScore3" / "Plugins"
    assert motif_setup.enable_in_musescore3(folder) is False     # never opened
    data = tmp_path / ".local" / "share" / "MuseScore" / "MuseScore3"
    data.mkdir(parents=True)
    listing = data / "plugins.xml"
    listing.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<museScore version="3.02">'
                       '<Plugin><path>/x/colornotes.qml</path><load>0</load></Plugin>'
                       f'<Plugin><path>{folder.as_posix()}/MotifAI/MotifAI.qml</path>'
                       '<load>0</load></Plugin></museScore>')
    assert motif_setup.enable_in_musescore3(folder) is True
    plugins = {p.findtext("path"): p.findtext("load")
               for p in ET.parse(listing).getroot().findall("Plugin")}
    assert plugins == {"/x/colornotes.qml": "0",
                       f"{folder.as_posix()}/MotifAI/MotifAI.qml": "1"}
    listing.unlink()
    assert motif_setup.enable_in_musescore3(folder) is True
    assert [p.findtext("load") for p in ET.parse(listing).getroot().findall("Plugin")] == ["1"]


def test_a_translated_documents_folder_is_found(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(motif_setup.platform, "system", lambda: "Linux")
    monkeypatch.delenv("XDG_DOCUMENTS_DIR", raising=False)
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "user-dirs.dirs").write_text(
        '# written by xdg-user-dirs-update\nXDG_DOCUMENTS_DIR="$HOME/Dokumente"\n')
    ms4 = tmp_path / "Dokumente" / "MuseScore4" / "Plugins"
    ms4.mkdir(parents=True)
    assert motif_setup.choose_plugin_dirs() == [ms4]


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


def test_preferences_has_no_composer_or_instrument_picker():
    """The panel must never let you choose a composer or ensemble from a
    list — both come only from what is typed into the prompt.

    Explaining that design choice in a code comment is fine (and the
    SettingsPanel docstring does); what must not exist is an actual control
    for it — a labelled picker, or the properties that would wire one up.
    """
    root = Path(__file__).resolve().parents[2] / "plugin" / "MotifAI"
    settings = (root / "components" / "SettingsPanel.qml").read_text()
    lowered = settings.lower()
    for banned in ('label: "composer"', 'label: "instruments"', "styleoverride",
                  "ensembleoverride", "styleoptions", "ensembleoptions",
                  "picker {"):
        assert banned not in lowered, f"Preferences still has {banned!r}"
    # A picker component that nothing uses any more should not ship either.
    assert not (root / "components" / "Picker.qml").exists()
    main = (root / "MotifAI.qml").read_text().lower()
    for banned in ("styleoverride", "ensembleoverride", "styleoptions",
                  "ensembleoptions", "loadchoices"):
        assert banned not in main, f"MotifAI.qml still references {banned!r}"


# ---------------------------------------------------------------------------
# The install sequence
# ---------------------------------------------------------------------------
@pytest.fixture
def machine(tmp_path, monkeypatch):
    """Every side effect of run_install, recorded instead of performed."""
    calls = []
    state = {"up": False}
    monkeypatch.setattr(motif_setup, "_log", lambda text: None)
    monkeypatch.setattr(motif_setup, "choose_plugin_dirs", lambda: [tmp_path])
    monkeypatch.setattr(motif_setup, "install_plugin", lambda d: calls.append("panel"))
    monkeypatch.setattr(motif_setup, "enable_in_musescore4", lambda: calls.append("enable"))
    monkeypatch.setattr(motif_setup, "prepare_config", lambda: calls.append("config"))
    monkeypatch.setattr(autostart, "is_running", lambda timeout=1.5: state["up"])

    def stop():
        calls.append("stop")
        state["up"] = False

    def start():
        calls.append("start")
        state["up"] = True
    monkeypatch.setattr(autostart, "stop", stop)
    monkeypatch.setattr(autostart, "start_now", start)
    monkeypatch.setattr(autostart, "install_engine", lambda: calls.append("engine"))
    monkeypatch.setattr(autostart, "install", lambda: calls.append("login item"))
    monkeypatch.setattr(autostart, "install_starts_engine", lambda: False)
    return calls, state


def test_install_runs_every_step_in_order(machine):
    calls, _ = machine
    messages = []
    assert motif_setup.run_install(lambda m, f: messages.append(m)) is True
    assert calls == ["panel", "enable", "engine", "config", "login item", "start"]
    assert messages[-1] == "Motif is ready."


def test_repair_restarts_a_running_copy_with_the_new_version(machine):
    calls, state = machine
    state["up"] = True
    assert motif_setup.run_install(lambda m, f: None) is True
    assert calls[0] == "stop" and calls[-1] == "start"


def test_no_second_copy_when_the_login_item_starts_motif(machine, monkeypatch):
    calls, state = machine
    monkeypatch.setattr(autostart, "install_starts_engine", lambda: True)
    monkeypatch.setattr(autostart, "install",
                        lambda: (calls.append("login item"), state.update(up=True)))
    assert motif_setup.run_install(lambda m, f: None) is True
    assert "start" not in calls
