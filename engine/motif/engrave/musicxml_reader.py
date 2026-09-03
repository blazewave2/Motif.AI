"""Read MusicXML back into Motif's score model.

Needed whenever the request refers to what is already on the page — "continue
this piece", "make the middle section darker" — so the agent can analyse the
user's actual music rather than guessing.
"""
from __future__ import annotations

import re
import zipfile
from xml.etree import ElementTree as ET

from ..score import (Direction, Measure, Note, Part, Score, TempoMark, bar_duration)
from ..theory.pitch import Key, Pitch

_CLEF_BACK = {("G", 2): "G", ("F", 4): "F", ("C", 3): "C", ("C", 4): "tenor",
              ("percussion", 2): "percussion"}


def read_musicxml(data: str | bytes) -> Score:
    """Parse MusicXML (or a compressed .mxl container) into a Score."""
    if isinstance(data, bytes) and data[:2] == b"PK":
        data = _unzip_mxl(data)
    if isinstance(data, bytes):
        data = data.decode("utf-8", errors="replace")
    data = data.lstrip("﻿ \n\r\t")
    root = ET.fromstring(data)
    if root.tag == "score-timewise":
        raise ValueError("timewise MusicXML is not supported")

    score = Score()
    score.title = _text(root, "work/work-title") or _credit_title(root) or "Untitled"
    score.subtitle = _text(root, "movement-title") or ""
    score.composer = _creator(root, "composer") or "Unknown"

    names = {}
    for sp in root.findall("part-list/score-part"):
        names[sp.get("id")] = (
            _text(sp, "part-name") or "Part",
            _text(sp, "part-abbreviation") or "",
            int(_text(sp, "midi-instrument/midi-program") or 1) - 1)

    divisions = 480
    first = True
    for pnode in root.findall("part"):
        pid = pnode.get("id") or f"P{len(score.parts)+1}"
        name, abbrev, program = names.get(pid, ("Part", "", 0))
        part = Part(id=pid, name=name, abbreviation=abbrev or name[:4],
                    midi_program=max(0, program))
        divisions = _read_part(pnode, part, score, divisions, first)
        score.add_part(part)
        first = False
    if not score.parts:
        raise ValueError("no parts found in MusicXML")
    return score


def _read_part(pnode, part: Part, score: Score, divisions: int, first: bool) -> int:
    from ..score import DIVISIONS
    scale = DIVISIONS / divisions
    index = 0
    for mnode in pnode.findall("measure"):
        # The printed number is unreliable: pickup bars are numbered 0, and
        # repeats and cadenzas use "X1"-style labels. Position is authoritative.
        index += 1
        num = index
        m = part.measure(index)
        attrs = mnode.find("attributes")
        if attrs is not None:
            d = attrs.findtext("divisions")
            if d:
                divisions = max(1, int(float(d)))
                scale = DIVISIONS / divisions
            k = attrs.find("key")
            if k is not None:
                fifths = int(k.findtext("fifths") or 0)
                mode = (k.findtext("mode") or "major").lower()
                key = _key_from_fifths(fifths, mode)
                if first and num == 1:
                    score.key = key
                m.key = key
            t = attrs.find("time")
            if t is not None:
                time = (int(t.findtext("beats") or 4), int(t.findtext("beat-type") or 4))
                if first and num == 1:
                    score.time = time
                m.time = time
            st = attrs.findtext("staves")
            if st:
                part.staves = max(part.staves, int(st))
            for c in attrs.findall("clef"):
                sign = c.findtext("sign") or "G"
                line = int(c.findtext("line") or 2)
                staff = int(c.get("number") or 1)
                part.clefs[staff] = _CLEF_BACK.get((sign, line), "G")

        for dnode in mnode.findall("direction"):
            _read_direction(dnode, m, scale)
            mm = dnode.find("direction-type/metronome")
            if mm is not None:
                per = (mm.findtext("per-minute") or "").strip()
                if re.match(r"^\d+(\.\d+)?$", per):
                    score.tempos.append(TempoMark(num, float(per)))

        pending: Note | None = None
        for nnode in mnode.findall("note"):
            note, is_chord = _read_note(nnode, scale)
            if is_chord and pending is not None:
                pending.pitches.extend(note.pitches)
                continue
            m.add(note)
            pending = note
    if score.tempos:
        score.tempo = score.tempos[0].bpm
    return divisions


def _read_note(nnode, scale: float) -> tuple[Note, bool]:
    from ..score import QUARTER
    is_chord = nnode.find("chord") is not None
    grace = nnode.find("grace") is not None
    dur = nnode.findtext("duration")
    ticks = int(round(float(dur) * scale)) if dur else (QUARTER // 4 if grace else QUARTER)
    pitches: list[Pitch] = []
    pn = nnode.find("pitch")
    if pn is not None:
        step = pn.findtext("step") or "C"
        alter = int(float(pn.findtext("alter") or 0))
        octave = int(pn.findtext("octave") or 4)
        pitches.append(Pitch.build(step, alter, octave))
    elif nnode.find("unpitched") is not None:
        pitches.append(Pitch.build("C", 0, 4))
    voice = int(nnode.findtext("voice") or 1)
    staff = int(nnode.findtext("staff") or 1)
    n = Note(pitches, max(1, ticks), voice=voice, staff=staff, grace=grace)
    for tie in nnode.findall("tie"):
        if tie.get("type") == "start":
            n.tie_start = True
        elif tie.get("type") == "stop":
            n.tie_stop = True
    nots = nnode.find("notations")
    if nots is not None:
        for sl in nots.findall("slur"):
            num = int(sl.get("number") or 1)
            if sl.get("type") == "start":
                n.slur_start = num
            elif sl.get("type") == "stop":
                n.slur_stop = num
        arts = nots.find("articulations")
        if arts is not None:
            n.articulations = [child.tag for child in arts]
        orns = nots.find("ornaments")
        if orns is not None:
            n.ornaments = [child.tag for child in orns if child.tag != "tremolo"]
        if nots.find("fermata") is not None:
            n.fermata = True
    lyric = nnode.findtext("lyric/text")
    if lyric:
        n.lyric = lyric
    return n, is_chord


def _read_direction(dnode, m: Measure, scale: float) -> None:
    placement = dnode.get("placement") or "below"
    staff = int(dnode.findtext("staff") or 1)
    offset = int(round(float(dnode.findtext("offset") or 0) * scale))
    dt = dnode.find("direction-type")
    if dt is None:
        return
    dyn = dt.find("dynamics")
    if dyn is not None and len(dyn):
        m.directions.append(Direction("dynamics", dyn[0].tag, offset, staff, placement))
        return
    w = dt.find("wedge")
    if w is not None:
        m.directions.append(Direction("wedge", w.get("type") or "crescendo",
                                      offset, staff, placement))
        return
    ped = dt.find("pedal")
    if ped is not None:
        m.directions.append(Direction("pedal", ped.get("type") or "start",
                                      offset, staff, placement))
        return
    words = dt.findtext("words")
    if words:
        m.directions.append(Direction("words", words.strip(), offset, staff, placement))


_FIFTHS_MAJOR = {0: "C", 1: "G", 2: "D", 3: "A", 4: "E", 5: "B", 6: "F#", 7: "C#",
                 -1: "F", -2: "Bb", -3: "Eb", -4: "Ab", -5: "Db", -6: "Gb", -7: "Cb"}
_FIFTHS_MINOR = {0: "A", 1: "E", 2: "B", 3: "F#", 4: "C#", 5: "G#", 6: "D#", 7: "A#",
                 -1: "D", -2: "G", -3: "C", -4: "F", -5: "Bb", -6: "Eb", -7: "Ab"}


def _key_from_fifths(fifths: int, mode: str) -> Key:
    fifths = max(-7, min(7, fifths))
    if mode.startswith("min") or mode == "aeolian":
        return Key(_FIFTHS_MINOR[fifths], "minor")
    return Key(_FIFTHS_MAJOR[fifths], "major")


def _unzip_mxl(data: bytes) -> str:
    import io
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        target = None
        try:
            container = z.read("META-INF/container.xml").decode("utf-8")
            m = re.search(r'full-path="([^"]+)"', container)
            if m:
                target = m.group(1)
        except KeyError:
            pass
        if not target:
            names = [n for n in z.namelist()
                     if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF")]
            if not names:
                raise ValueError("no MusicXML inside the .mxl container")
            target = names[0]
        return z.read(target).decode("utf-8", errors="replace")


def _text(root, path: str) -> str:
    v = root.findtext(path)
    return v.strip() if v else ""


def _creator(root, ctype: str) -> str:
    for c in root.findall("identification/creator"):
        if c.get("type") == ctype and c.text:
            return c.text.strip()
    return ""


def _credit_title(root) -> str:
    for c in root.findall("credit"):
        if (c.findtext("credit-type") or "") == "title":
            w = c.findtext("credit-words")
            if w:
                return w.strip()
    return ""
