"""The open score as MuseScore 4 sends it: a walk with MuseScore's cursor.

MuseScore 4's plugins cannot save a score, so the panel reads the page note
by note and the engine rebuilds it. The fixture is exactly what MuseScore
Studio 4.6 sent for ``snapshot_probe.msn``: a pickup, a tie over the bar, a
triplet, a second voice, a change to 6/8 and a tempo change, a key change
and a whole-bar rest.
"""
import json
from pathlib import Path

import pytest

from motif.agent.analysis import analyse
from motif.engrave.snapshot import dynamic_text, score_from_snapshot, spelled, tempo_mark
from motif.notation import parse
from motif.notation.to_score import to_score

FIX = Path(__file__).parent / "fixtures"


def _snapshot() -> dict:
    return json.loads((FIX / "snapshot_probe_ms4.json").read_text())


def _voices(score):
    """Each bar's music, voice by voice: pitches and lengths (grace notes aside)."""
    out = []
    for m in score.parts[0].measures:
        out.append({v: [(tuple(p.midi for p in n.pitches), n.duration, n.tie_start, n.tie_stop)
                        for n in notes if not n.grace and n.print_object]
                    for v, notes in sorted(m.voices.items())})
    return out


def test_a_snapshot_rebuilds_the_page_as_musescore_4_sent_it():
    page = score_from_snapshot(_snapshot())
    written, _ = to_score(parse((FIX / "snapshot_probe.msn").read_text()))
    assert page.title == "Probe Piece"
    assert page.measure_count == written.measure_count == 6
    assert page.parts[0].staves == 2 and page.parts[0].clefs == {1: "G", 2: "F"}
    assert page.parts[0].measures[0].implicit            # the pickup
    assert _voices(page) == _voices(written)
    assert [m.time for m in page.parts[0].measures] == [(3, 4), None, None, (6, 8), None, None]
    assert [str(m.key) if m.key else None for m in page.parts[0].measures] == \
        ["Db major", None, None, None, "A major", None]
    triplet = [n for n in page.parts[0].measures[2].voices[1] if n.tuplet]
    assert [(n.tuplet.start, n.tuplet.stop) for n in triplet] == \
        [(True, False), (False, False), (False, True)]
    assert [(d.kind, d.value) for m in page.parts[0].measures for d in m.directions] == \
        [("dynamics", "p"), ("dynamics", "f")]
    assert [(t.measure, t.bpm, t.dotted, t.text) for t in page.tempos] == \
        [(1, 60.0, False, "Larghetto"), (4, 72.0, True, "Più mosso")]


def test_a_continuation_picks_up_where_the_piece_has_got_to():
    info = analyse(score_from_snapshot(_snapshot()))
    assert str(info.key) == "Db major" and info.time == (3, 4)
    assert str(info.end_key) == "A major" and info.end_time == (6, 8)
    assert info.end_tempo == 72.0                      # dotted quarters, as marked


@pytest.mark.parametrize("midi,tpc,name", [
    (68, 10, "Ab4"), (73, 21, "C#5"), (60, 26, "B#3"), (59, 7, "Cb4"), (62, 14 + 2, "D4"),
    (61, 16, "C#4"),                                   # a tpc that does not match: the pitch wins
])
def test_pitches_are_spelled_as_the_page_spells_them(midi, tpc, name):
    p = spelled(midi, tpc)
    assert p.midi == midi
    if name != "C#4":
        assert f"{p.step}{'#' * p.alter if p.alter > 0 else 'b' * -p.alter}{p.octave}" == name


def test_markings_read_as_they_print():
    assert dynamic_text("<sym>dynamicMezzo</sym><sym>dynamicForte</sym>") == "mf"
    assert dynamic_text("<sym>dynamicSforzato</sym>") == "sfz"
    assert dynamic_text("<i>pp</i>") == "pp"
    t = tempo_mark("<b>Allegro</b> <sym>metNoteHalfUp</sym> = 84", 168, 1, 0, (2, 2))
    assert (t.bpm, t.beat_unit, t.text, t.quarter_bpm) == (84.0, "half", "Allegro", 168.0)
    t = tempo_mark("Andante", 72, 3, 0, (4, 4))
    assert (t.bpm, t.beat_unit, t.text) == (72.0, "quarter", "Andante")


def test_a_broken_snapshot_is_not_trusted():
    with pytest.raises(ValueError):
        score_from_snapshot({"format": "motif-snapshot-1", "measures": [], "parts": []})
    with pytest.raises(ValueError):
        score_from_snapshot({"format": "something else"})


def test_continuing_the_page_musescore_4_sent(tmp_path, monkeypatch):
    """The whole request, as the panel on MuseScore 4 makes it."""
    from motif.agent.agent import MotifAgent, Request
    from motif.engrave.musicxml_reader import read_musicxml
    agent = MotifAgent(options={"quality": "sketch"})
    res = agent.run(Request(prompt="Continue this piece", score_snapshot=_snapshot(), seed=3))
    assert res.ok, res.error
    assert res.intent == "continue" and res.based_on == "open_score"
    out = read_musicxml(res.musicxml)
    assert out.measure_count > 6
    # the page itself comes first, unchanged ...
    assert _voices(out)[:6] == _voices(score_from_snapshot(_snapshot()))
    # ... and the new music carries on in its last key and metre
    seventh = out.parts[0].measures[6]
    keys = [m.key for m in out.parts[0].measures[:7] if m.key]
    times = [m.time for m in out.parts[0].measures[:7] if m.time]
    assert str(keys[-1]) == "A major" and times[-1] == (6, 8)
    assert seventh.voices


def walk(score) -> dict:
    """What the panel on MuseScore 4 would send for ``score``: the walk
    ``js/snapshot.js`` makes, in MuseScore's ticks (480 to the quarter)."""
    from motif.score import DIVISIONS, bar_duration
    k = DIVISIONS // 480
    top = score.parts[0]
    ticks, starts, time, fifths = 0, [], tuple(score.time), score.key.fifths
    measures, keys = [], []
    for m in top.measures:
        time = tuple(m.time) if m.time else time
        fifths = m.key.fifths if m.key is not None else fifths
        full = bar_duration(time)
        length = max([sum(n.duration for n in notes if not n.grace)
                      for notes in m.voices.values()] + [0]) if m.implicit else full
        starts.append(ticks)
        measures.append({"tick": ticks, "len": length // k, "ts": list(time)})
        keys.append([ticks, fifths])
        ticks += length // k
    parts, events, dynamics, track = [], [], [], 0
    for part in score.parts:
        parts.append({"name": part.name, "short": part.abbreviation, "instrument": "",
                      "program": part.midi_program, "startTrack": track,
                      "endTrack": track + 4 * part.staves})
        for i, m in enumerate(part.measures):
            for v, notes in m.voices.items():
                t = starts[i]
                group_end = -1
                for n in notes:
                    if n.grace:
                        continue
                    tr = track + v - 1
                    if n.print_object or n.pitches:
                        ev = [tr, t, n.duration // k, 1, 4,
                              [[p.midi, p.fifths_tpc() if hasattr(p, "fifths_tpc") else
                                _tpc(p), int(n.tie_start), int(n.tie_stop)]
                               for p in n.pitches] or 0, 0, 0, 0]
                        if n.tuplet:
                            if t >= group_end:
                                span = sum(x.duration for x in notes[notes.index(n):]
                                           if x.tuplet) // k
                                group_end = t + span
                            ev[6:9] = [n.tuplet.actual, n.tuplet.normal, span]
                        events.append(ev)
                    t += n.duration // k
            for d in m.directions:
                if d.kind == "dynamics":
                    dynamics.append([starts[i] + d.offset // k, track + 4 * (d.staff - 1),
                                     d.value])
        track += 4 * part.staves
    tempos = [[starts[t.measure - 1] + t.offset // k, t.quarter_bpm, t.text]
              for t in score.tempos if t.visible]
    return {"format": "motif-snapshot-1", "title": score.title, "composer": "",
            "parts": parts, "measures": measures, "keys": keys, "events": events,
            "tempos": tempos, "dynamics": dynamics}


def _tpc(p) -> int:
    fifths = {"F": -1, "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5}[p.step] + 7 * p.alter
    return fifths + 14


def _composed(prompt: str, seed: int = 1):
    from motif.agent.prompt_parser import parse_prompt
    from motif.composer.core import Composer
    return Composer(parse_prompt(prompt, seed=seed), quality="sketch").compose()


@pytest.mark.parametrize("prompt,key", [
    ("A Rachmaninoff prelude in C sharp minor", "C# minor"),
    ("A Chopin nocturne in E flat major", "Eb major"),
    ("A Chopin waltz in A minor", "A minor"),
])
def test_a_key_signature_is_heard_as_major_or_minor(prompt, key):
    """MuseScore does not say whether four sharps are E major or C♯ minor;
    the notes do."""
    page = score_from_snapshot(walk(_composed(prompt)))
    assert str(page.key) == key


def test_a_piece_read_from_musescore_4_is_arranged_in_its_own_key():
    from motif.agent.agent import MotifAgent, Request
    from motif.engrave.musicxml_reader import read_musicxml
    prelude = _composed("A Rachmaninoff prelude in C sharp minor")
    agent = MotifAgent(options={"quality": "sketch"})
    res = agent.run(Request(prompt="Arrange this for string quartet",
                            score_snapshot=walk(prelude), seed=2))
    assert res.ok and res.intent == "arrange", res.error
    assert res.title == prelude.title                  # its own name, not a new one
    out = read_musicxml(res.musicxml)
    assert [p.name for p in out.parts][:2] == ["Violin I", "Violin II"]
    assert out.key.fifths == 4 and str(out.key) == "C# minor"
    # and at its own tempo, under its own marking
    marked = [t for t in prelude.tempos if t.visible][0]
    kept = [t for t in out.tempos if t.visible][0]
    assert (kept.text, kept.bpm) == (marked.text, marked.bpm)
