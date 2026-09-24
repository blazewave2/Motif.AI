"""Turn MSN into Motif's engraving model — the step between a composer's
notation and a page MuseScore can open.

Everything the notation says is kept: voices, ties (per note of a chord),
nested slurs, tuplets, grace notes, articulations, ornaments, dynamics,
hairpins, pedalling, expression text, tempo, key, metre and clef changes,
repeats and volta brackets, lyrics. What the notation leaves to the
engraver is decided here the way an engraver would: where a dynamic sits
between the staves, when a left hand climbs high enough to need a treble
clef, how a transposing instrument's part is actually written.

Bars that don't add up are repaired rather than rejected — padded with a
rest or trimmed — and every repair is reported, so a caller that cares
(the composer's self-correction loop) can see exactly what was wrong.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from ..engrave.beaming import apply_beams
from ..score import (DIVISIONS, Direction, Measure, Note, Part, Score, TempoMark,
                     Tuplet)
from ..theory.pitch import Interval, Key, Pitch
from .instruments import PartSpec
from .msn import (TYPE_NAMES, Issue, Marking, MsnMeasure, MsnPiece,
                  VoiceLine, bar_length, beat_unit)

#: Printed words that are really tempo instructions: they sit above the
#: staff, and they move the playback tempo.
TEMPO_WORDS = ("rit", "rall", "accel", "a tempo", "tempo i", "tempo primo",
               "string", "allarg", "calando", "morendo", "smorz", "slentando",
               "riten", "animando", "affrett", "incalz", "più mosso", "piu mosso",
               "meno mosso", "più lento", "piu lento", "tempo 1", "come prima",
               "l'istesso", "a piacere", "rubato", "largamente", "stretto")

DYNAMIC_VELOCITY = {"pppp": 16, "ppp": 26, "pp": 38, "p": 52, "mp": 66, "mf": 80,
                    "f": 95, "ff": 110, "fff": 120, "ffff": 126, "sf": 106,
                    "sfz": 110, "sffz": 118, "sfp": 100, "sfpp": 100, "fp": 95,
                    "fz": 108, "rf": 100, "rfz": 104, "mfp": 80}


def is_tempo_word(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in TEMPO_WORDS)


def to_ticks(q: Fraction) -> int:
    """Quarter-note position -> ticks, rounding only where a 11- or 13-tuplet forces it."""
    return int(round(q * DIVISIONS))


@dataclass
class _BarInfo:
    msn: MsnMeasure
    time: tuple[int, int]
    length: Fraction          # quarters
    key: Key                  # concert key in force
    start: Fraction           # absolute position, quarters


def to_score(piece: MsnPiece, *, auto_clefs: bool = True) -> tuple[Score, list[Issue]]:
    """Engrave ``piece``. Returns the score and any repairs that were needed."""
    return _Builder(piece, auto_clefs=auto_clefs).build()


class _Builder:
    def __init__(self, piece: MsnPiece, auto_clefs: bool = True):
        self.piece = piece
        self.issues: list[Issue] = []
        self.auto_clefs = auto_clefs
        self.bars: list[_BarInfo] = []

    # ------------------------------------------------------------------
    def build(self) -> tuple[Score, list[Issue]]:
        piece = self.piece
        score = Score(title=piece.title or "Untitled", subtitle=piece.subtitle,
                      composer=piece.composer or "Motif.AI",
                      key=piece.key, time=tuple(piece.time), tempo=float(piece.tempo))
        score.metadata.update({k: v for k, v in piece.meta.items()})
        if piece.style:
            score.metadata["style_text"] = piece.style
        self._timeline()

        parts: list[Part] = []
        for i, spec in enumerate(piece.parts):
            parts.append(self._part(i, spec))
        score.parts = parts

        for i, spec in enumerate(piece.parts):
            self._fill_part(score, parts[i], spec)

        self._tempos(score)
        self._first_part_marks(score, parts[0] if parts else None)
        if self.auto_clefs:
            for part, spec in zip(parts, piece.parts):
                self._auto_clefs(part, spec)
        from .perform import shape_velocities
        shape_velocities(score, seed=len(piece.measures) * 7919 + len(parts))
        for part in parts:
            apply_beams(part, tuple(piece.time), half_bar=True)
            self._beam_graces(part)
            if part.measures and not part.measures[-1].barline and not part.measures[-1].repeat_end:
                part.measures[-1].barline = "light-heavy"
        return score, self.issues

    # ------------------------------------------------------------------
    def _timeline(self) -> None:
        time = tuple(self.piece.time)
        key = self.piece.key
        pos = Fraction(0)
        for i, m in enumerate(self.piece.measures):
            if m.time:
                time = tuple(m.time)
            if m.key is not None:
                key = m.key
            length = bar_length(time)
            if i == 0 and m.number == 0:
                # A pickup bar is as long as what is written in it.
                longest = max((v.duration for v in m.voices if not v.has_bar_rest),
                              default=Fraction(0))
                if 0 < longest < length:
                    length = longest
            self.bars.append(_BarInfo(m, time, length, key, pos))
            pos += length

    def _part(self, index: int, spec: PartSpec) -> Part:
        inst = spec.instrument
        clefs = {i + 1: c for i, c in enumerate(inst.clefs)}
        part = Part(id=f"P{index + 1}", name=spec.display_name,
                    abbreviation=spec.display_abbreviation,
                    midi_program=inst.program, midi_channel=_channel(index),
                    staves=inst.staves, clefs=clefs,
                    instrument_sound=inst.sound)
        if inst.transposes:
            part.transpose = inst.musicxml_transpose()
        part.extra["msn_id"] = spec.id
        part.extra["instrument"] = inst.key
        return part

    # ------------------------------------------------------------------
    def _written_key(self, spec: PartSpec, key: Key) -> Key:
        inst = spec.instrument
        if not inst.transposes:
            return key
        steps, semis = inst.transpose
        tonic = Pitch.parse(key.tonic + "4").transpose_by(Interval(-steps, -semis))
        return _sane_key(tonic.name, key.mode)

    def _written(self, spec: PartSpec, p: Pitch, written_key: Key) -> Pitch:
        inst = spec.instrument
        if not inst.transposes:
            return p
        steps, semis = inst.transpose
        w = p.transpose_by(Interval(-steps, -semis))
        if abs(w.alter) > 2 or abs(w.alter - written_key.signature_alters.get(w.step, 0)) > 1:
            w = written_key.spell(w.midi)
        return w

    def _fill_part(self, score: Score, part: Part, spec: PartSpec) -> None:
        slur_numbers: dict[tuple[int, int], list[int]] = {}
        wedge_open: dict[int, int] = {}
        pedal_down = False
        lyric_state: dict[tuple[int, int], bool] = {}
        prev_written_key: Key | None = None
        tie_carry: dict[tuple[int, int], set[int]] = {}

        for bi, info in enumerate(self.bars):
            m_src = info.msn
            measure = Measure(number=m_src.number)
            measure.implicit = (bi == 0 and m_src.number == 0)
            part.measures.append(measure)
            bar_ticks = to_ticks(info.length)

            written_key = self._written_key(spec, info.key)
            if bi == 0 or m_src.key is not None:
                if prev_written_key is None or str(written_key) != str(prev_written_key) or bi == 0:
                    measure.key = written_key
                prev_written_key = written_key
            if m_src.time is not None and bi > 0:
                measure.time = tuple(m_src.time)
            elif bi == 0:
                measure.time = tuple(info.time)
            clef_changes = {staff: clef for (pid, staff), clef in m_src.clefs.items()
                            if pid == spec.id}
            if clef_changes:
                measure.clefs = clef_changes
            self._barlines(measure, m_src, bi)

            for staff in range(1, spec.staves + 1):
                lines = sorted([v for v in m_src.voices if v.part == spec.id and v.staff == staff],
                               key=lambda v: v.voice)
                if not any(v.voice == 1 for v in lines):
                    measure.add(Note([], bar_ticks, voice=_xml_voice(staff, 1), staff=staff,
                                     measure_rest=True))
                for vl in lines:
                    self._voice(measure, part, spec, vl, info, written_key,
                                slur_numbers, lyric_state, tie_carry)

            # Markings, placed the way an engraver would.
            seen: set[tuple] = set()
            for staff in range(1, spec.staves + 1):
                for vl in sorted([v for v in m_src.voices if v.part == spec.id
                                  and v.staff == staff], key=lambda v: v.voice):
                    for mk in vl.markings:
                        pedal_down = self._marking(measure, spec, vl, mk, info, seen,
                                                   wedge_open, pedal_down)
                    for ev in vl.events:
                        for mark in ev.marks:
                            if mark.startswith("dyn:"):
                                self._marking(measure, spec, vl,
                                              Marking("dynamic", mark[4:], ev.offset),
                                              info, seen, wedge_open, pedal_down)
                            elif mark in ("pizz", "arco"):
                                self._marking(measure, spec, vl,
                                              Marking("text", mark + ("." if mark == "pizz" else ""),
                                                      ev.offset, "above"),
                                              info, seen, wedge_open, pedal_down)

        # Anything still open at the end is closed on the last bar.
        if part.measures:
            last = part.measures[-1]
            end = to_ticks(self.bars[-1].length) if self.bars else 0
            for number in wedge_open.values():
                last.directions.append(Direction("wedge", "stop", max(0, end - 1), 1,
                                                 "below", extra={"number": number}))
            if pedal_down and spec.instrument.key in ("piano", "celesta"):
                last.directions.append(Direction("pedal", "stop", max(0, end - 1),
                                                 spec.staves, "below"))

    def _barlines(self, measure: Measure, m: MsnMeasure, index: int) -> None:
        if m.barline == "double":
            measure.barline = "light-light"
        elif m.barline == "final":
            measure.barline = "light-heavy"
        elif m.barline == "dashed":
            measure.barline = "dashed"
        if m.repeat in ("start", "both"):
            measure.repeat_start = True
        if m.repeat in ("end", "both"):
            measure.repeat_end = True
        if m.ending:
            measure.ending = m.ending
            prev = self.bars[index - 1].msn if index > 0 else None
            nxt = self.bars[index + 1].msn if index + 1 < len(self.bars) else None
            starts = prev is None or prev.ending != m.ending
            stops = nxt is None or nxt.ending != m.ending
            measure.ending_type = ("both" if starts and stops else
                                   "start" if starts else "stop" if stops else "continue")

    # ------------------------------------------------------------------
    def _voice(self, measure: Measure, part: Part, spec: PartSpec, vl: VoiceLine,
               info: _BarInfo, written_key: Key, slur_numbers, lyric_state,
               tie_carry) -> None:
        xml_voice = _xml_voice(vl.staff, vl.voice)
        vkey = (vl.staff, vl.voice)
        bar_len = info.length
        events = vl.events
        if len(events) == 1 and events[0].kind == "bar_rest":
            measure.add(Note([], to_ticks(bar_len), voice=xml_voice, staff=vl.staff,
                             measure_rest=True))
            tie_carry.pop(vkey, None)
            return

        total = sum((e.duration for e in events), Fraction(0))
        if total > bar_len:
            self.issues.append(Issue(
                "error", f"{_q(total)} written in a bar of {_q(bar_len)}; "
                f"the excess was cut", info.msn.number, vl.label, "duration"))
        elif total < bar_len and vl.voice == 1:
            self.issues.append(Issue(
                "error", f"{_q(total)} written in a bar of {_q(bar_len)}; "
                f"padded with a rest", info.msn.number, vl.label, "duration"))

        pos = Fraction(0)
        stack = slur_numbers.setdefault(vkey, [])
        for ev in events:
            if pos >= bar_len:
                break
            end = min(pos + ev.duration, bar_len)
            ticks = to_ticks(end) - to_ticks(pos)
            if ticks <= 0:
                pos = end
                continue
            for g in ev.graces:
                gn = Note([self._written(spec, p, written_key) for p in g.pitches],
                          to_ticks(g.written), voice=xml_voice, staff=vl.staff,
                          grace=True, grace_slash=ev.grace_slash,
                          grace_type=TYPE_NAMES.get(g.base, "16th"))
                _apply_marks(gn, g.marks)
                measure.add(gn)
            n = Note([self._written(spec, p, written_key) for p in ev.pitches], ticks,
                     voice=xml_voice, staff=vl.staff)
            if ev.kind == "spacer":
                n.print_object = False
            if ev.tuplet:
                actual, normal = ev.tuplet
                n.tuplet = Tuplet(actual, normal, TYPE_NAMES.get(ev.base, "eighth"),
                                  start=ev.tuplet_start, stop=ev.tuplet_stop, number=1)
            _apply_marks(n, ev.marks)

            # Ties: which of this note's pitches continue from the last note,
            # and which carry on into the next.
            carried = tie_carry.get(vkey, set())
            if ev.pitches:
                stops = [p.midi for p in n.pitches if _sounding_midi(spec, p) in carried]
                starts = [n.pitches[k].midi for k, t in enumerate(ev.ties) if t]
                if stops:
                    n.tie_stop = True
                    if len(stops) != len(n.pitches):
                        n.tie_stop_pitches = stops
                if starts:
                    n.tie_start = True
                    if len(starts) != len(n.pitches):
                        n.tie_start_pitches = starts
                tie_carry[vkey] = {ev.pitches[k].midi for k, t in enumerate(ev.ties) if t}
            else:
                tie_carry[vkey] = set()

            # Slurs, numbered per voice so nested and overlapping ones survive.
            for s in range(ev.slur_stops):
                number = stack.pop() if stack else 1
                if not n.slur_stop:
                    n.slur_stop = number
                else:
                    n.more_slurs.append(("stop", number))
            for s in range(ev.slur_starts):
                number = _free_slot(stack, slur_numbers)
                stack.append(number)
                if not n.slur_start:
                    n.slur_start = number
                else:
                    n.more_slurs.append(("start", number))

            if ev.lyric is not None and ev.pitches:
                text = ev.lyric
                continues = text.endswith("-")
                was = lyric_state.get(vkey, False)
                n.lyric = text.strip("-").strip() or text
                n.lyric_syllabic = (("middle" if continues else "end") if was
                                    else ("begin" if continues else "single"))
                lyric_state[vkey] = continues
            measure.add(n)
            pos = end

        if pos < bar_len:
            rest = Note([], to_ticks(bar_len) - to_ticks(pos), voice=xml_voice,
                        staff=vl.staff)
            if vl.voice > 1:
                rest.print_object = False
            measure.add(rest)

    # ------------------------------------------------------------------
    def _marking(self, measure: Measure, spec: PartSpec, vl: VoiceLine, mk: Marking,
                 info: _BarInfo, seen: set, wedge_open: dict[int, int],
                 pedal_down: bool) -> bool:
        offset = to_ticks(min(mk.offset, info.length))
        keyboard = spec.instrument.keyboard and spec.staves >= 2
        # One dynamic between the staves speaks for both hands.
        staff = vl.staff if not keyboard else min(vl.staff, 2)
        placement = "below"
        if keyboard and vl.staff >= 2:
            placement = "above"          # between the staves, under the right hand
            staff = 2
        if mk.kind == "dynamic":
            sig = ("dyn", offset, mk.value)
            if sig in seen:
                return pedal_down
            seen.add(sig)
            if keyboard:
                staff, placement = 1, "below"
            vel = DYNAMIC_VELOCITY.get(mk.value, 80)
            measure.directions.append(Direction(
                "dynamics", mk.value, offset, staff, placement,
                extra={"dynamics_velocity": round(vel / 0.9)}))
        elif mk.kind == "hairpin":
            sig = ("wedge", offset, mk.value)
            if sig in seen:
                return pedal_down
            seen.add(sig)
            if keyboard:
                staff, placement = 1, "below"
            number = 1
            while number in wedge_open.values():
                number += 1
            if staff in wedge_open:          # a new hairpin closes an open one
                measure.directions.append(Direction("wedge", "stop", offset, staff,
                                                    placement,
                                                    extra={"number": wedge_open.pop(staff)}))
            wedge_open[staff] = number
            measure.directions.append(Direction("wedge", mk.value, offset, staff, placement,
                                                extra={"number": number}))
        elif mk.kind == "hairpin_end":
            if keyboard:
                staff, placement = 1, "below"
            sig = ("wedge-stop", offset)
            if sig in seen or staff not in wedge_open:
                return pedal_down
            seen.add(sig)
            measure.directions.append(Direction("wedge", "stop", offset, staff, placement,
                                                extra={"number": wedge_open.pop(staff)}))
        elif mk.kind == "pedal":
            if spec.instrument.key not in ("piano", "celesta"):
                return pedal_down
            sig = ("ped", offset, mk.value)
            if sig in seen:
                return pedal_down
            seen.add(sig)
            low = spec.staves
            if mk.value == "down":
                measure.directions.append(Direction("pedal", "change" if pedal_down else "start",
                                                    offset, low, "below"))
                return True
            if pedal_down:
                measure.directions.append(Direction("pedal", "stop", offset, low, "below"))
            return False
        elif mk.kind == "text":
            sig = ("text", offset, mk.value.lower())
            if sig in seen:
                return pedal_down
            seen.add(sig)
            tempo_like = is_tempo_word(mk.value)
            if mk.placement:
                placement = mk.placement
            elif tempo_like:
                placement, staff = "above", 1
            elif keyboard:
                placement = "below" if vl.staff == 1 else "above"
                staff = 1 if vl.staff == 1 else 2
            measure.directions.append(Direction(
                "words", mk.value, offset, staff, placement,
                extra={"style": "italic", "tempo_word": tempo_like}))
        return pedal_down

    def _first_part_marks(self, score: Score, first: Part | None) -> None:
        """Bar-level text and rehearsal marks belong over the top staff."""
        if first is None:
            return
        for bi, (info, measure) in enumerate(zip(self.bars, first.measures)):
            m = info.msn
            if m.mark:
                measure.directions.append(Direction("rehearsal", m.mark, 0, 1, "above"))
            if bi > 0 and m.tempo is None and m.tempo_text:
                # "Più mosso", "Tempo I": printed like a tempo mark; the
                # playback map realises what it asks for.
                measure.directions.append(Direction(
                    "words", m.tempo_text, 0, 1, "above",
                    extra={"style": "normal", "weight": "bold", "tempo_word": True}))
            for text in m.texts:
                measure.directions.append(Direction(
                    "words", text, 0, 1, "above",
                    extra={"style": "italic", "tempo_word": is_tempo_word(text)}))

    # ------------------------------------------------------------------
    def _tempos(self, score: Score) -> None:
        piece = self.piece
        marks: list[TempoMark] = []
        first = self.bars[0] if self.bars else None
        if first is not None:
            unit_len, unit_type, dotted = beat_unit(first.time)
            m0 = first.msn
            bpm = m0.tempo if m0.tempo is not None else piece.tempo
            text = m0.tempo_text if (m0.tempo is not None or m0.tempo_text) else piece.tempo_text
            marks.append(TempoMark(m0.number, float(bpm), unit_type, text, dotted))
        for info in self.bars[1:]:
            m = info.msn
            if m.tempo is None and not m.tempo_text:
                continue
            unit_len, unit_type, dotted = beat_unit(info.time)
            if m.tempo is None:
                # Text alone ("Tempo I", "Più mosso"): printed; playback follows below.
                continue
            marks.append(TempoMark(m.number, float(m.tempo), unit_type, m.tempo_text, dotted))
        score.tempos = marks
        if marks:
            score.tempo = marks[0].bpm
        from .perform import playback_tempos
        score.tempos.extend(playback_tempos(self.bars, score, self._tempo_texts()))

    def _tempo_texts(self) -> list[tuple[int, Fraction, str]]:
        """(bar index, offset, text) for every tempo word, including bar tempo text."""
        out: list[tuple[int, Fraction, str]] = []
        for bi, info in enumerate(self.bars):
            m = info.msn
            if m.tempo is None and m.tempo_text:
                out.append((bi, Fraction(0), m.tempo_text))
            for t in m.texts:
                if is_tempo_word(t):
                    out.append((bi, Fraction(0), t))
            for vl in m.voices:
                for mk in vl.markings:
                    if mk.kind == "text" and is_tempo_word(mk.value):
                        out.append((bi, mk.offset, mk.value))
        seen = set()
        uniq = []
        for bi, off, text in sorted(out, key=lambda x: (x[0], x[1])):
            k = (bi, off, text.lower())
            if k not in seen:
                seen.add(k)
                uniq.append((bi, off, text))
        return uniq

    # ------------------------------------------------------------------
    def _auto_clefs(self, part: Part, spec: PartSpec) -> None:
        """Let a hand that climbs or dives change clef, as a pianist's page does.

        Only for keyboard staves the composer left alone — an explicit clef
        change anywhere on a staff means the composer is managing it. The
        thresholds differ in each direction, so a line hovering at the
        boundary doesn't flip clef every bar.
        """
        if not spec.instrument.keyboard or spec.staves < 2:
            return
        for staff in (1, 2):
            if any(m.clefs and staff in m.clefs for m in part.measures):
                continue
            home = part.clefs.get(staff, "G" if staff == 1 else "F")
            current = home
            for m in part.measures:
                pitches = sorted(p.midi for notes in m.voices.values() for n in notes
                                 if n.staff == staff and not n.grace for p in n.pitches)
                if not pitches:
                    continue
                want = _clef_for(pitches, current, home)
                if want != current:
                    m.clefs = dict(m.clefs or {})
                    m.clefs[staff] = want
                    current = want

    def _beam_graces(self, part: Part) -> None:
        for m in part.measures:
            for notes in m.voices.values():
                run: list[Note] = []
                for n in notes + [None]:
                    if n is not None and n.grace and n.grace_type in ("eighth", "16th", "32nd"):
                        run.append(n)
                        continue
                    if len(run) >= 2:
                        levels = {"eighth": 1, "16th": 2, "32nd": 3}
                        depth = min(levels[g.grace_type] for g in run)
                        for i, g in enumerate(run):
                            kind = "begin" if i == 0 else "end" if i == len(run) - 1 else "continue"
                            g.beam = [kind] * depth
                    run = []


# ---------------------------------------------------------------------------
def _clef_for(pitches: list[int], current: str, home: str) -> str:
    lo, hi = pitches[0], pitches[-1]
    median = pitches[len(pitches) // 2]
    if current == "F":
        if home == "F":
            return "G" if lo >= 55 and median >= 64 else "F"
        return "G" if hi > 67 or median > 57 else "F"         # a right hand coming home
    if home == "G":
        return "F" if hi <= 60 and median <= 52 else "G"
    return "F" if lo < 53 or median < 59 else "G"             # a left hand coming home


def _apply_marks(n: Note, marks: list[str]) -> None:
    from .msn import MARKS
    for mark in marks:
        if mark.startswith("dyn:") or mark in ("pizz", "arco"):
            continue
        if mark == "fermata":
            n.fermata = True
            continue
        if mark == "arp":
            n.arpeggiate = True
            continue
        kind, value = MARKS.get(mark, ("", ""))
        if kind == "art":
            if value not in n.articulations:
                n.articulations.append(value)
        elif kind == "orn":
            if value not in n.ornaments:
                n.ornaments.append(value)
        elif kind == "trem":
            n.tremolo = int(value)
        elif kind == "tech":
            n.technical.append(value)
        elif kind == "finger":
            n.technical.append(value)


def _free_slot(stack: list[int], all_stacks: dict) -> int:
    used = set()
    for s in all_stacks.values():
        used.update(s)
    for n in range(1, 7):
        if n not in used:
            return n
    return (len(stack) % 6) + 1


def _xml_voice(staff: int, voice: int) -> int:
    return (staff - 1) * 4 + voice


def _channel(index: int) -> int:
    ch = index + 1
    if ch >= 10:          # channel 10 is the drum kit in General MIDI
        ch += 1
    return min(16, ch)


def _sounding_midi(spec: PartSpec, written: Pitch) -> int:
    steps, semis = spec.instrument.transpose
    return written.midi + semis


def _q(value: Fraction) -> str:
    """A length in quarter notes as a musician would say it."""
    if value.denominator == 1:
        n = int(value)
        return f"{n} beat" + ("" if n == 1 else "s")
    return f"{float(value):g} beats"


_KEY_TABLE_MAJOR = {"C", "G", "D", "A", "E", "B", "F#", "C#", "F", "Bb", "Eb", "Ab",
                    "Db", "Gb", "Cb"}
_KEY_TABLE_MINOR = {"A", "E", "B", "F#", "C#", "G#", "D#", "A#", "D", "G", "C", "F",
                    "Bb", "Eb", "Ab"}
_ENHARMONIC = {"C#": "Db", "Db": "C#", "D#": "Eb", "Eb": "D#", "F#": "Gb", "Gb": "F#",
               "G#": "Ab", "Ab": "G#", "A#": "Bb", "Bb": "A#", "B": "Cb", "Cb": "B",
               "E#": "F", "Fb": "E", "B#": "C", "Cbb": "Bb", "Fx": "G", "Cx": "D",
               "Gx": "A", "Dx": "E", "Ax": "B", "E": "Fb", "F": "E#", "C": "B#"}


def _sane_key(tonic: str, mode: str) -> Key:
    """A written key a player would actually read: never E# major or D# major."""
    minor = mode in ("minor", "natural_minor", "harmonic_minor", "melodic_minor", "aeolian")
    table = _KEY_TABLE_MINOR if minor else _KEY_TABLE_MAJOR
    candidates = [tonic]
    if tonic in _ENHARMONIC:
        candidates.append(_ENHARMONIC[tonic])
    best = None
    for c in candidates:
        if c in table:
            k = Key(c, "minor" if minor else "major")
            if best is None or abs(k.fifths) < abs(best.fifths):
                best = k
    if best is not None:
        return best
    try:
        return Key(tonic, mode)
    except Exception:
        return Key("C", "minor" if minor else "major")
