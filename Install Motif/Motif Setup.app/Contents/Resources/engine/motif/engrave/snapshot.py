"""Read the open score from the panel's own walk through it.

MuseScore 4's plugins cannot save a score (its ``writeScore`` is not
implemented), so where MuseScore 3 hands Motif the page as MusicXML, the
panel on MuseScore 4 walks it with MuseScore's cursor and sends what it finds
(``plugin/MotifAI/js/snapshot.js``). This module rebuilds a Score from that
walk, in the shape the MusicXML reader gives, so that analysis, continuing,
harmonising and arranging work the same whichever MuseScore asked. The
snapshot holds:
- every chord and rest, with its exact timing, spelled pitches, ties and
  tuplet;
- each bar's time and key signature;
- the tempo and dynamic markings.

A snapshot is::

    {"format": "motif-snapshot-1", "title": ..., "composer": ...,
     "parts":    [{"name", "short", "instrument", "program", "startTrack", "endTrack"}],
     "measures": [{"tick", "len", "ts": [n, d]}],
     "keys":     [[tick, fifths]],
     "events":   [[track, tick, ticks, written_n, written_d,
                   [[midi, tpc, tie_forward, tie_back], ...] or 0,
                   tuplet_actual, tuplet_normal, tuplet_ticks]],
     "tempos":   [[tick, quarters_per_minute, text]],
     "dynamics": [[tick, track, text]]}

Times are in MuseScore's ticks, 480 to the quarter note.
"""
from __future__ import annotations

import bisect
import re
from statistics import median

from ..score import (DIVISIONS, Direction, Note, Part, Score, TempoMark, Tuplet,
                     note_type_and_dots)
from ..theory.pitch import Key, Pitch, from_midi
from .musicxml_reader import _key_from_fifths

FORMAT = "motif-snapshot-1"
MS_QUARTER = 480
SCALE = DIVISIONS // MS_QUARTER          # 21 of Motif's ticks to one of MuseScore's

_STEPS = "FCGDAEB"

#: MuseScore's dynamic symbols, by the letters they print.
_DYNAMIC_SYMS = {
    "dynamicPiano": "p", "dynamicMezzo": "m", "dynamicForte": "f",
    "dynamicRinforzando": "r", "dynamicSforzando": "s", "dynamicZ": "z",
    "dynamicNiente": "n", "dynamicPPPPPP": "pppppp", "dynamicPPPPP": "ppppp",
    "dynamicPPPP": "pppp", "dynamicPPP": "ppp", "dynamicPP": "pp", "dynamicMP": "mp",
    "dynamicMF": "mf", "dynamicPF": "pf", "dynamicFF": "ff", "dynamicFFF": "fff",
    "dynamicFFFF": "ffff", "dynamicFFFFF": "fffff", "dynamicFFFFFF": "ffffff",
    "dynamicFortePiano": "fp", "dynamicForzando": "fz", "dynamicSforzando1": "sf",
    "dynamicSforzandoPiano": "sfp", "dynamicSforzandoPianissimo": "sfpp",
    "dynamicSforzato": "sfz", "dynamicSforzatoPiano": "sfzp", "dynamicSforzatoFF": "sffz",
    "dynamicRinforzando1": "rf", "dynamicRinforzando2": "rfz",
}

#: MuseScore's metronome-mark note symbols (and the characters older scores use).
_UNIT_SYMS = {
    "metNoteDoubleWhole": "breve", "metNoteWhole": "whole", "metNoteHalfUp": "half",
    "metNoteQuarterUp": "quarter", "metNote8thUp": "eighth", "metNote16thUp": "16th",
}
_UNIT_CHARS = {"𝅝": "whole", "𝅗𝅥": "half", "♩": "quarter", "♪": "eighth", "𝅘𝅥𝅯": "16th"}
_UNIT_QUARTERS = {"breve": 8.0, "whole": 4.0, "half": 2.0, "quarter": 1.0, "eighth": 0.5,
                  "16th": 0.25}


def is_snapshot(data) -> bool:
    return isinstance(data, dict) and data.get("format") == FORMAT


def spelled(midi: int, tpc: int) -> Pitch:
    """A pitch from MuseScore's MIDI number and tonal pitch class (14 is C,
    each step up the line of fifths one more: 15 G, 13 F, 21 C♯, 7 C♭)."""
    fifths = int(tpc) - 14
    step = _STEPS[(fifths + 1) % 7]
    alter = (fifths + 1) // 7
    octave = (int(midi) - alter) // 12 - 1
    p = Pitch.build(step, alter, octave)
    return p if p.midi == int(midi) else from_midi(int(midi))   # a stray tpc: trust the pitch


def dynamic_text(raw: str) -> str:
    """The dynamic a marking prints: "mf" from "<sym>dynamicMezzo</sym><sym>dynamicForte</sym>"."""
    letters = "".join(_DYNAMIC_SYMS.get(name, "") for name in re.findall(r"<sym>(\w+)</sym>", raw))
    rest = re.sub(r"<sym>\w+</sym>", "", raw)
    rest = re.sub(r"<[^>]+>", "", rest).strip()
    return (letters + rest).strip() or rest


def tempo_mark(raw: str, qpm: float, measure: int, offset: int,
               time: tuple[int, int]) -> TempoMark:
    """A tempo marking from MuseScore's text and its tempo in quarters per minute."""
    syms = re.findall(r"<sym>(\w+)</sym>", raw)
    unit = next((_UNIT_SYMS[s] for s in syms if s in _UNIT_SYMS), "")
    dotted = "metAugmentationDot" in syms
    text = re.sub(r"<sym>\w+</sym>", " ", raw)
    text = re.sub(r"<[^>]+>", "", text)
    for ch, name in _UNIT_CHARS.items():
        if ch in text:
            unit = unit or name
            text = text.replace(ch, " ")
    words, eq, number = text.partition("=")
    words = re.sub(r"\s+", " ", words.replace(" ", " ")).strip(" .")
    if not eq:
        words, number = re.sub(r"\s+", " ", text).strip(), ""
    if not unit:
        compound = time[1] == 8 and time[0] % 3 == 0 and time[0] > 3
        unit, dotted = ("quarter", True) if compound else (
            {2: "half", 8: "eighth"}.get(time[1], "quarter"), False)
    per_beat = _UNIT_QUARTERS.get(unit, 1.0) * (1.5 if dotted else 1.0)
    try:
        bpm = float(re.findall(r"\d+(?:\.\d+)?", number)[0])
    except IndexError:
        bpm = round(qpm / per_beat, 2) if qpm else 60.0
    return TempoMark(measure, bpm, unit, words, dotted, offset,
                     visible=bool(words or eq))


def score_from_snapshot(data: dict) -> Score:
    """Rebuild the open score from the panel's walk through it."""
    if not is_snapshot(data):
        raise ValueError("not a Motif score snapshot")
    bars = [b for b in data.get("measures") or [] if isinstance(b, dict)]
    if not bars:
        raise ValueError("the snapshot has no bars")
    starts = [int(b.get("tick", 0)) for b in bars]
    keys = sorted((int(t), int(k)) for t, k in (data.get("keys") or [[0, 0]]))
    key_ticks = [t for t, _ in keys]

    def key_at(tick: int) -> int:
        i = bisect.bisect_right(key_ticks, tick) - 1
        return keys[max(0, i)][1] if keys else 0

    score = Score()
    score.title = str(data.get("title") or "").strip() or "Untitled"
    score.composer = str(data.get("composer") or "").strip() or "Unknown"
    first_time = tuple(int(x) for x in (bars[0].get("ts") or (4, 4)))[:2]
    score.time = first_time if len(first_time) == 2 and first_time[1] else (4, 4)
    score.key = _key_from_fifths(key_at(starts[0]), "major")

    parts_in = sorted((p for p in data.get("parts") or [] if isinstance(p, dict)),
                      key=lambda p: int(p.get("startTrack", 0)))
    if not parts_in:
        raise ValueError("the snapshot has no parts")
    parts: list[tuple[int, int, Part]] = []
    for i, p in enumerate(parts_in):
        start, end = int(p.get("startTrack", 0)), int(p.get("endTrack", 4))
        name = str(p.get("name") or "").strip() or f"Part {i + 1}"
        program = int(p.get("program", -1)) if str(p.get("program", "")).lstrip("-").isdigit() \
            else -1
        part = Part(id=f"P{i + 1}", name=name,
                    abbreviation=str(p.get("short") or "").strip() or name[:4],
                    midi_program=max(0, program), staves=max(1, (end - start) // 4))
        part.extra["instrument"] = str(p.get("instrument") or "")
        parts.append((start, end, part))
        score.add_part(part)

    # the bars, the same in every part
    prev_time = None
    prev_key = None
    for i, b in enumerate(bars):
        ts = tuple(int(x) for x in (b.get("ts") or score.time))[:2]
        ts = ts if len(ts) == 2 and ts[1] else score.time
        full = int(ts[0] * MS_QUARTER * 4 / ts[1])
        fifths = key_at(starts[i])
        for _, _, part in parts:
            m = part.measure(i + 1)
            if ts != prev_time:
                m.time = ts
            if fifths != prev_key:
                m.key = _key_from_fifths(fifths, "major")
            if i == 0 and 0 < int(b.get("len") or full) < full:
                m.implicit = True
        prev_time, prev_key = ts, fifths

    def locate(tick: int) -> int:
        return max(0, bisect.bisect_right(starts, tick) - 1)

    def owner(track: int):
        for start, end, part in parts:
            if start <= track < end:
                return start, part
        return None

    # the music, voice by voice, in time order
    by_track: dict[int, list] = {}
    for ev in data.get("events") or []:
        if isinstance(ev, list) and len(ev) >= 6:
            by_track.setdefault(int(ev[0]), []).append(ev)
    for track, events in sorted(by_track.items()):
        found = owner(track)
        if found is None:
            continue
        start, part = found
        rel = track - start
        staff, voice = rel // 4 + 1, rel + 1
        ends: dict[int, int] = {}             # bar -> where this voice has got to
        group_end = -1                        # the open tuplet runs to here
        for ev in sorted(events, key=lambda e: int(e[1])):
            tick, ticks = int(ev[1]), max(1, int(ev[2]))
            bi = locate(tick)
            m = part.measures[bi]
            offset = (tick - starts[bi]) * SCALE
            got = ends.get(bi, 0)
            if offset > got:
                # a voice that enters mid-bar is kept in time by a silent rest
                m.add(Note([], offset - got, voice=voice, staff=staff, print_object=False))
            elif offset < got:
                continue                      # overlaps what is already there
            notes = ev[5] if isinstance(ev[5], list) else []
            pitches, tie_f, tie_b = [], [], []
            for n in notes:
                p = spelled(int(n[0]), int(n[1]))
                pitches.append(p)
                if len(n) > 2 and n[2]:
                    tie_f.append(p.midi)
                if len(n) > 3 and n[3]:
                    tie_b.append(p.midi)
            note = Note(pitches, ticks * SCALE, voice=voice, staff=staff)
            if pitches:
                all_midi = sorted(p.midi for p in pitches)
                note.tie_start = bool(tie_f)
                note.tie_stop = bool(tie_b)
                note.tie_start_pitches = None if sorted(tie_f) == all_midi else sorted(tie_f)
                note.tie_stop_pitches = None if sorted(tie_b) == all_midi else sorted(tie_b)
            elif len(bars) and ticks >= int(bars[bi].get("len") or 0) > 0 and offset == 0:
                note.measure_rest = True
            actual, normal = (int(ev[6]), int(ev[7])) if len(ev) > 7 else (0, 0)
            if actual and normal:
                written_n, written_d = int(ev[3] or 1), int(ev[4] or 4)
                written = MS_QUARTER * 4 * written_n // max(1, written_d)
                base, _ = note_type_and_dots(written * SCALE)
                note.tuplet = Tuplet(actual, normal, base)
                span = int(ev[8]) if len(ev) > 8 and int(ev[8] or 0) > 0 else \
                    written * normal
                if tick >= group_end:
                    note.tuplet.start = True
                    group_end = tick + span
                if tick + ticks >= group_end:
                    note.tuplet.stop = True
            else:
                group_end = -1
            m.add(note)
            ends[bi] = offset + ticks * SCALE

    # the markings
    top = parts[0][2]
    for tick, qpm, raw in data.get("tempos") or []:
        bi = locate(int(tick))
        time = _time_at(top, bi) or score.time
        score.tempos.append(tempo_mark(str(raw), float(qpm or 0), bi + 1,
                                       (int(tick) - starts[bi]) * SCALE, time))
    for tick, track, raw in data.get("dynamics") or []:
        found = owner(int(track))
        value = dynamic_text(str(raw))
        if found is None or not value:
            continue
        start, part = found
        bi = locate(int(tick))
        part.measures[bi].directions.append(
            Direction("dynamics", value, (int(tick) - starts[bi]) * SCALE,
                      (int(track) - start) // 4 + 1, "below"))
    if score.tempos:
        visible = [t for t in score.tempos if t.visible]
        score.tempo = (visible or score.tempos)[0].quarter_bpm

    for _, _, part in parts:
        _choose_clefs(part)
    _find_modes(score)
    if data.get("truncated"):
        score.metadata["truncated"] = True
    return score


#: Krumhansl's key profiles, for telling a major key from its relative minor.
_MAJOR = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
_MINOR = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)


def _find_modes(score: Score) -> None:
    """Major or minor for each stretch under one key signature. MuseScore
    does not record a key's mode, so four sharps could be E major or C♯
    minor: the notes decide, and the bass the piece closes on counts double."""
    measures = [p.measures for p in score.parts]
    count = len(measures[0])
    start = 0
    while start < count:
        sig = measures[0][start].key or _sig_before(measures[0], start) or score.key
        end = start + 1
        while end < count and measures[0][end].key is None:
            end += 1
        hist = [0.0] * 12
        low_last = None
        for bars in measures:
            for m in bars[start:end]:
                for notes in m.voices.values():
                    for n in notes:
                        if n.grace or not n.pitches:
                            continue
                        for p in n.pitches:
                            hist[p.midi % 12] += n.duration
        for bars in measures:
            tail = [n for notes in bars[end - 1].voices.values() for n in notes if n.pitches]
            if tail:
                lowest = min(p.midi for n in tail for p in n.pitches)
                low_last = lowest if low_last is None else min(low_last, lowest)
        major = Key(sig.tonic, "major") if sig.is_minor else sig
        minor = major.relative
        total = sum(hist) or 1.0
        fit = {}
        for key, profile in ((major, _MAJOR), (minor, _MINOR)):
            fit[key.mode] = sum(hist[(key.tonic_pc + i) % 12] / total * profile[i]
                                for i in range(12))
            if low_last is not None and low_last % 12 == key.tonic_pc:
                fit[key.mode] += 0.35
        chosen = minor if fit["minor"] > fit["major"] else major
        for bars in measures:
            if bars[start].key is not None or start == 0:
                bars[start].key = chosen
        if start == 0:
            score.key = chosen
        start = end


def _sig_before(bars, index: int):
    for m in reversed(bars[:index]):
        if m.key is not None:
            return m.key
    return None


def _time_at(part: Part, index: int) -> tuple[int, int] | None:
    for m in reversed(part.measures[:index + 1]):
        if m.time:
            return m.time
    return None


def _choose_clefs(part: Part) -> None:
    """Each staff's clef, from where its music lies (the snapshot does not
    carry clefs; the page's own will be restored by the musician's score)."""
    name = part.name.lower()
    for staff in range(1, part.staves + 1):
        pitches = [p.midi for m in part.measures for notes in m.voices.values()
                   for n in notes if n.staff == staff for p in n.pitches]
        if "viola" in name and part.staves == 1:
            part.clefs[staff] = "C"
        elif pitches and median(pitches) < 57:
            part.clefs[staff] = "F"
        elif staff == 2 and not pitches:
            part.clefs[staff] = "F"
        else:
            part.clefs[staff] = "G"
