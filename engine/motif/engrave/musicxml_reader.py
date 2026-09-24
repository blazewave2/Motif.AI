"""Read MusicXML back into Motif's score model.

Needed whenever the request refers to what is already on the page — "continue
this piece", "make the middle section darker" — so the agent can analyse the
user's actual music rather than guessing.
"""
from __future__ import annotations

import re
import zipfile
from xml.etree import ElementTree as ET

from ..score import DIVISIONS as DIVISIONS_DEFAULT, Direction, Measure, Note, Part, Score, TempoMark
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
    score.metadata.update(_read_motif_metadata(root))

    names = {}
    for sp in root.findall("part-list/score-part"):
        names[sp.get("id")] = (
            _text(sp, "part-name") or "Part",
            _text(sp, "part-abbreviation") or "",
            int(_text(sp, "midi-instrument/midi-program") or 1) - 1)

    divisions = DIVISIONS_DEFAULT
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
    """Read one part, tracking the time position through backup and forward.

    MusicXML writes voices one after another inside a bar and rewinds with
    <backup>; a voice that enters mid-bar is preceded by a <forward>. The
    position has to be followed exactly, or a second voice lands on beat
    one and every mid-bar dynamic slides to the start of the bar.
    """
    from ..score import DIVISIONS
    scale = DIVISIONS / divisions
    index = 0
    for mnode in pnode.findall("measure"):
        # The printed number is unreliable: pickup bars are numbered 0, and
        # repeats and cadenzas use "X1"-style labels. Position is authoritative.
        index += 1
        num = index
        m = part.measure(index)
        if (mnode.get("implicit") or "").lower() == "yes" and index == 1:
            m.implicit = True
        pos = 0                                  # ticks from the start of the bar
        voice_end: dict[int, int] = {}
        pending: Note | None = None

        for child in mnode:
            tag = child.tag
            if tag == "attributes":
                d = child.findtext("divisions")
                if d:
                    divisions = max(1, int(float(d)))
                    scale = DIVISIONS / divisions
                k = child.find("key")
                if k is not None and k.findtext("fifths") is not None:
                    fifths = int(k.findtext("fifths") or 0)
                    mode = (k.findtext("mode") or "major").lower()
                    key = _key_from_fifths(fifths, mode)
                    if first and num == 1:
                        score.key = key
                    m.key = key
                t = child.find("time")
                if t is not None and t.findtext("beats"):
                    try:
                        time = (int(t.findtext("beats") or 4), int(t.findtext("beat-type") or 4))
                    except ValueError:
                        time = (4, 4)
                    if first and num == 1:
                        score.time = time
                    m.time = time
                st = child.findtext("staves")
                if st:
                    part.staves = max(part.staves, int(st))
                for c in child.findall("clef"):
                    sign = c.findtext("sign") or "G"
                    line = int(c.findtext("line") or 2)
                    octave = int(c.findtext("clef-octave-change") or 0)
                    staff = int(c.get("number") or 1)
                    name = _CLEF_BACK.get((sign, line), "G")
                    if name == "G" and octave == -1:
                        name = "G8vb"
                    if num == 1 and pos == 0:
                        part.clefs[staff] = name
                    else:
                        m.clefs = dict(m.clefs or {})
                        m.clefs[staff] = name
                tr = child.find("transpose")
                if tr is not None and part.transpose is None:
                    part.transpose = (int(tr.findtext("diatonic") or 0),
                                      int(tr.findtext("chromatic") or 0),
                                      int(tr.findtext("octave-change") or 0))
            elif tag == "backup":
                pos = max(0, pos - int(round(float(child.findtext("duration") or 0) * scale)))
            elif tag == "forward":
                pos += int(round(float(child.findtext("duration") or 0) * scale))
            elif tag == "direction":
                off = int(round(float(child.findtext("offset") or 0) * scale))
                _read_direction(child, m, pos + off)
                tempo = _direction_tempo(child, num, pos + off)
                if tempo is not None and first:
                    score.tempos.append(tempo)
            elif tag == "sound":
                bpm = child.get("tempo")
                if bpm and first:
                    try:
                        score.tempos.append(TempoMark(num, float(bpm), offset=pos,
                                                      visible=False))
                    except ValueError:
                        pass
            elif tag == "barline":
                _read_barline(child, m)
            elif tag == "note":
                note, is_chord, chord_ties = _read_note(child, scale)
                if is_chord and pending is not None:
                    pending.pitches.extend(note.pitches)
                    _merge_chord_ties(pending, note, chord_ties)
                    continue
                if note.grace:
                    m.add(note)
                    continue
                v = note.voice
                end = voice_end.get(v, 0)
                if pos > end:
                    # The voice was silent until here: keep it in time with
                    # an invisible rest rather than pulling the note forward.
                    gap = Note([], pos - end, voice=v, staff=note.staff, print_object=False)
                    m.add(gap)
                m.add(note)
                pending = note
                pos += note.duration
                voice_end[v] = max(end, pos)
    if score.tempos:
        visible = [t for t in score.tempos if t.visible]
        score.tempo = (visible or score.tempos)[0].quarter_bpm
    return divisions


def _merge_chord_ties(head: Note, extra: Note, ties: dict) -> None:
    """Chord members carry their own <tie> elements; keep them per pitch."""
    start = set(head.tie_start_pitches or ([p.midi for p in head.pitches[:-len(extra.pitches)]]
                                           if head.tie_start else []))
    stop = set(head.tie_stop_pitches or ([p.midi for p in head.pitches[:-len(extra.pitches)]]
                                         if head.tie_stop else []))
    for p in extra.pitches:
        if ties.get("start"):
            start.add(p.midi)
        if ties.get("stop"):
            stop.add(p.midi)
    all_midi = {p.midi for p in head.pitches}
    head.tie_start = bool(start)
    head.tie_stop = bool(stop)
    head.tie_start_pitches = None if start == all_midi else sorted(start)
    head.tie_stop_pitches = None if stop == all_midi else sorted(stop)


def _read_note(nnode, scale: float):
    from ..score import QUARTER, Tuplet
    is_chord = nnode.find("chord") is not None
    grace_node = nnode.find("grace")
    grace = grace_node is not None
    dur = nnode.findtext("duration")
    ticks = int(round(float(dur) * scale)) if dur else (QUARTER // 4 if grace else QUARTER)
    pitches: list[Pitch] = []
    pn = nnode.find("pitch")
    rest = nnode.find("rest")
    if pn is not None:
        step = pn.findtext("step") or "C"
        alter = int(round(float(pn.findtext("alter") or 0)))
        octave = int(pn.findtext("octave") or 4)
        pitches.append(Pitch.build(step, alter, octave))
    elif nnode.find("unpitched") is not None:
        pitches.append(Pitch.build("C", 0, 4))
    voice = int(nnode.findtext("voice") or 1)
    staff = int(nnode.findtext("staff") or 1)
    n = Note(pitches, max(1, ticks), voice=voice, staff=staff, grace=grace)
    if grace:
        n.grace_slash = (grace_node.get("slash") or "") == "yes"
        n.grace_type = nnode.findtext("type") or "16th"
    if (nnode.get("print-object") or "").lower() == "no":
        n.print_object = False
    if rest is not None and (rest.get("measure") or "").lower() == "yes":
        n.measure_rest = True
    ties = {"start": False, "stop": False}
    for tie in nnode.findall("tie"):
        if tie.get("type") == "start":
            n.tie_start = True
            ties["start"] = True
        elif tie.get("type") == "stop":
            n.tie_stop = True
            ties["stop"] = True
    tm = nnode.find("time-modification")
    if tm is not None:
        try:
            actual = int(tm.findtext("actual-notes") or 3)
            normal = int(tm.findtext("normal-notes") or 2)
            n.tuplet = Tuplet(actual, normal, nnode.findtext("type") or "eighth")
        except ValueError:
            n.tuplet = None
    nots = nnode.find("notations")
    if nots is not None:
        for sl in nots.findall("slur"):
            num = int(sl.get("number") or 1)
            if sl.get("type") == "start":
                if n.slur_start:
                    n.more_slurs.append(("start", num))
                else:
                    n.slur_start = num
            elif sl.get("type") == "stop":
                if n.slur_stop:
                    n.more_slurs.append(("stop", num))
                else:
                    n.slur_stop = num
        for tup in nots.findall("tuplet"):
            if n.tuplet is not None:
                if tup.get("type") == "start":
                    n.tuplet.start = True
                elif tup.get("type") == "stop":
                    n.tuplet.stop = True
        arts = nots.find("articulations")
        if arts is not None:
            n.articulations = [child.tag for child in arts]
        orns = nots.find("ornaments")
        if orns is not None:
            n.ornaments = [child.tag for child in orns if child.tag != "tremolo"]
            trem = orns.find("tremolo")
            if trem is not None and (trem.get("type") or "single") == "single":
                try:
                    n.tremolo = int((trem.text or "3").strip())
                except ValueError:
                    n.tremolo = 3
        tech = nots.find("technical")
        if tech is not None:
            for child in tech:
                if child.tag == "fingering" and (child.text or "").strip().isdigit():
                    n.technical.append(child.text.strip())
                elif child.tag in ("up-bow", "down-bow", "harmonic", "open-string"):
                    n.technical.append(child.tag)
        if nots.find("fermata") is not None:
            n.fermata = True
        if nots.find("arpeggiate") is not None:
            n.arpeggiate = True
    ly = nnode.find("lyric")
    if ly is not None and ly.findtext("text"):
        n.lyric = ly.findtext("text")
        n.lyric_syllabic = ly.findtext("syllabic") or "single"
    return n, is_chord, ties


def _read_direction(dnode, m: Measure, offset: int) -> None:
    placement = dnode.get("placement") or "below"
    staff = int(dnode.findtext("staff") or 1)
    for dt in dnode.findall("direction-type"):
        dyn = dt.find("dynamics")
        if dyn is not None and len(dyn):
            tag = dyn[0].tag
            if tag == "other-dynamics":
                tag = (dyn[0].text or "mf").strip()
            m.directions.append(Direction("dynamics", tag, offset, staff, placement))
            continue
        w = dt.find("wedge")
        if w is not None:
            m.directions.append(Direction("wedge", w.get("type") or "crescendo",
                                          offset, staff, placement,
                                          extra={"number": int(w.get("number") or 1)}))
            continue
        ped = dt.find("pedal")
        if ped is not None:
            m.directions.append(Direction("pedal", ped.get("type") or "start",
                                          offset, staff, placement))
            continue
        reh = dt.findtext("rehearsal")
        if reh:
            m.directions.append(Direction("rehearsal", reh.strip(), offset, staff, "above"))
            continue
        if dt.find("metronome") is not None:
            continue                      # read separately as a tempo mark
        words = dt.findtext("words")
        if words and words.strip():
            has_metronome = dnode.find("direction-type/metronome") is not None
            if has_metronome:
                continue                  # the tempo mark carries this text
            m.directions.append(Direction("words", words.strip(), offset, staff, placement))


def _direction_tempo(dnode, measure: int, offset: int) -> TempoMark | None:
    """A tempo marking, visible or not, from one <direction>."""
    met = dnode.find("direction-type/metronome")
    sound = dnode.find("sound")
    text = ""
    for dt in dnode.findall("direction-type"):
        w = dt.findtext("words")
        if w and w.strip():
            text = w.strip()
    if met is not None:
        per = (met.findtext("per-minute") or "").strip()
        num = re.match(r"^(\d+(?:\.\d+)?)", per)
        if num:
            return TempoMark(measure, float(num.group(1)),
                             met.findtext("beat-unit") or "quarter", text,
                             met.find("beat-unit-dot") is not None, offset=offset)
    if sound is not None and sound.get("tempo"):
        try:
            bpm = float(sound.get("tempo"))
        except ValueError:
            return None
        return TempoMark(measure, bpm, "quarter", text, False, offset=offset,
                         visible=bool(text))
    return None


def _read_barline(bnode, m: Measure) -> None:
    loc = bnode.get("location") or "right"
    style = bnode.findtext("bar-style") or ""
    rep = bnode.find("repeat")
    if rep is not None:
        if rep.get("direction") == "forward":
            m.repeat_start = True
        elif rep.get("direction") == "backward":
            m.repeat_end = True
    end = bnode.find("ending")
    if end is not None:
        try:
            m.ending = int((end.get("number") or "1").split(",")[0].strip())
        except ValueError:
            m.ending = 1
        kind = end.get("type") or ""
        if kind == "start":
            m.ending_type = "both" if m.ending_type == "stop" else "start"
        elif kind in ("stop", "discontinue"):
            m.ending_type = "both" if m.ending_type == "start" else "stop"
    if loc == "right" and style and rep is None and style not in ("regular",):
        m.barline = style


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


def _read_motif_metadata(root) -> dict:
    """Recover Motif's own provenance fields, when this score carries them.

    Written by ``musicxml.py`` as plain ``<miscellaneous-field>`` entries, so
    they survive in any MusicXML file Motif itself produced and are silently
    absent from anything else (a hand-written score, or one from another
    application) — which is exactly the fallback behaviour that is wanted:
    read back the exact composer and forces when they are known, and let the
    heuristic analysis take over when they are not.
    """
    out: dict = {}
    for field in root.findall("identification/miscellaneous/miscellaneous-field"):
        name = field.get("name") or ""
        if name.startswith("motif-") and field.text:
            out[name[len("motif-"):]] = field.text.strip()
    if "seed" in out:
        try:
            out["seed"] = int(out["seed"])
        except ValueError:
            del out["seed"]
    return out


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
