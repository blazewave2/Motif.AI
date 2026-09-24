"""Writing the composer's music down.

The composer thinks in voices of timed notes — "this chord, from beat 2 of
bar 5, for three beats" — and this module turns that into Motif Score
Notation, bar by bar, the way an engraver would write it: a note that
crosses a bar line or the middle of a 4/4 bar is split and tied, rests fill
the gaps, a second voice that falls silent is hidden rather than littering
the page with rests, and markings (dynamics, hairpins, pedalling, words)
sit at the point in the voice where they happen.

The text is then read by :mod:`motif.notation`, which validates every bar
and engraves it, so the composer's output passes exactly the checks any
other music does.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction as F

from ..theory.pitch import Key, Pitch

#: Written values, longest first, as MSN duration codes.
_VALUES: list[tuple[F, str]] = [
    (F(4), "w"), (F(3), "h."), (F(2), "h"), (F(3, 2), "q."), (F(1), "q"),
    (F(3, 4), "e."), (F(1, 2), "e"), (F(3, 8), "s."), (F(1, 4), "s"),
    (F(3, 16), "t."), (F(1, 8), "t"), (F(1, 16), "x"),
]
_CODE: dict[F, str] = dict(_VALUES)


@dataclass
class Note:
    """A note, chord or rest in one voice, placed on the piece's timeline."""

    onset: F                                   # quarters from the start of the piece
    dur: F
    pitches: list[Pitch] = field(default_factory=list)   # empty: a rest
    tie: bool = False                          # held into the next note
    marks: list[str] = field(default_factory=list)       # stacc, ten, accent, fermata, arp…
    slur_start: int = 0
    slur_stop: int = 0
    graces: list[Pitch] = field(default_factory=list)
    grace_kind: str = "acc"                    # acc (slashed) | app | g (several)
    tuplet: tuple[int, int] | None = None      # (3, 2): three in the time of two
    tuplet_start: bool = False
    tuplet_stop: bool = False
    lyric: str | None = None

    @property
    def end(self) -> F:
        return self.onset + self.dur

    @property
    def is_rest(self) -> bool:
        return not self.pitches


@dataclass
class Mark:
    """Something that happens at a point in a voice: a dynamic, a hairpin, a
    pedal change, or words."""

    onset: F
    kind: str        # dyn | cresc | dim | end | ped | pedup | text | above | below
    value: str = ""


@dataclass
class Voice:
    label: str                                  # RH, RH2, LH, LH2 (or a part id)
    notes: list[Note] = field(default_factory=list)
    marks: list[Mark] = field(default_factory=list)
    secondary: bool = False                     # gaps are hidden rather than shown

    def add(self, note: Note) -> Note:
        self.notes.append(note)
        return note


@dataclass
class BarInfo:
    """What changes at the start of a bar."""

    key: Key | None = None
    time: tuple[int, int] | None = None
    tempo: float | None = None
    tempo_text: str = ""
    text: str = ""
    barline: str = ""                  # double | final | dashed
    mark: str = ""
    clefs: dict[str, str] = field(default_factory=dict)   # staff label -> clef


def pitch_token(p: Pitch) -> str:
    return f"{p.name}{p.octave}"


# ---------------------------------------------------------------------------
# splitting durations the way an engraver would
# ---------------------------------------------------------------------------
def beat_length(time: tuple[int, int]) -> F:
    num, den = time
    if den == 8 and num % 3 == 0 and num >= 6:
        return F(3, 2)
    if den == 2:
        return F(2)
    return F(4, den)


def bar_length(time: tuple[int, int]) -> F:
    return F(time[0] * 4, time[1])


def split_in_bar(start: F, dur: F, time: tuple[int, int], rest: bool = False) -> list[F]:
    """Break a value that starts ``start`` quarters into a bar into written
    values that show the metre: nothing crosses the middle of a 4/4 bar
    unless it starts on the downbeat, and short values stay inside their
    beat. Syncopations a player reads at a glance (e q e, q h q) are kept
    whole."""
    beat = beat_length(time)
    bar = bar_length(time)
    half = bar / 2 if (time[0] in (4, 12) or (time[1] == 2 and time[0] == 4)) else None
    out: list[F] = []
    s, left = start, min(dur, bar - start)
    guard = 0
    while left > 0 and guard < 64:
        guard += 1
        chosen = None
        for v, _ in _VALUES:
            if v > left:
                continue
            if not _fits(s, v, beat, half, bar, rest, whole=(v == left)):
                continue
            chosen = v
            break
        if chosen is None:
            # A value no written note can take on its own: fall back to the
            # smallest unit that reaches the next grid point.
            chosen = _smallest_step(s, left)
        out.append(chosen)
        s += chosen
        left -= chosen
    return out


def _fits(s: F, v: F, beat: F, half: F | None, bar: F, rest: bool,
          whole: bool = True) -> bool:
    end = s + v
    if end > bar:
        return False
    if half is not None and s < half < end and s != 0:
        # Crossing the middle of the bar is fine from the downbeat, and for
        # the classic q h q syncopation in 4/4 (when that is the whole
        # note) — never for a rest.
        if rest or not (s == beat and v == 2 * beat and whole):
            return False
    if v >= beat:
        if s % beat != 0:
            # The only off-beat long value allowed is the e q e syncopation.
            return (not rest) and v == beat and s % (beat / 2) == 0 and (
                half is None or not (s < half < end))
        dotted = (v / beat) not in (1, 2, 4) and v != 3 * beat
        if dotted and rest:
            return False
        return True
    # Shorter than a beat: stay inside it.
    within = s % beat
    return within + v <= beat


def _smallest_step(s: F, left: F) -> F:
    for v in (F(1, 16), F(1, 32), F(1, 64)):
        if v <= left:
            return v
    return left


def group_tuplets(notes: list[Note]) -> None:
    """Consecutive notes of triplet values are written as triplets: a group
    ends as soon as its values add up to a plain written length."""
    notes.sort(key=lambda n: n.onset)
    group: list[Note] = []
    total = F(0)

    def close(ok: bool) -> None:
        six = ok and len(group) == 6 and all(g.dur == F(1, 6) for g in group)
        for g in group:
            g.tuplet = ((6, 4) if six else (3, 2)) if ok else None
            g.tuplet_start = ok and g is group[0]
            g.tuplet_stop = ok and g is group[-1]

    for n in notes:
        triple = n.dur.denominator % 3 == 0
        if group and (not triple or n.onset != group[-1].end):
            close(False)
            group, total = [], F(0)
        if not triple:
            continue
        group.append(n)
        total += n.dur
        sextuplet = all(g.dur == F(1, 6) for g in group)
        if total.denominator & (total.denominator - 1) == 0 and \
                not (sextuplet and total < 1):              # a power of two: complete
            close(True)
            group, total = [], F(0)
    if group:
        close(False)


# ---------------------------------------------------------------------------
# writing a piece
# ---------------------------------------------------------------------------
@dataclass
class Sheet:
    """Everything needed to write a piece: its header, bar layout and voices."""

    title: str
    key: Key
    time: tuple[int, int]
    tempo: float
    tempo_text: str = ""
    subtitle: str = ""
    composer: str = "Motif.AI"
    style: str = ""
    bars: int = 0
    bar_info: dict[int, BarInfo] = field(default_factory=dict)   # bar number -> changes
    voices: list[Voice] = field(default_factory=list)
    parts: list[tuple[str, str, str]] = field(default_factory=list)  # (id, instrument, name)
    harmony: dict[int, list[tuple[F, str]]] = field(default_factory=dict)
    pickup: F = F(0)                                   # length of an upbeat bar, if any

    def time_at(self, bar: int) -> tuple[int, int]:
        t = self.time
        for n in sorted(self.bar_info):
            if n > bar:
                break
            if self.bar_info[n].time:
                t = self.bar_info[n].time
        return t

    def bar_starts(self) -> list[F]:
        """Where each bar begins on the timeline (index 0 is bar 1)."""
        out, pos = [], self.pickup
        for b in range(1, self.bars + 1):
            out.append(pos)
            pos += bar_length(self.time_at(b))
        return out

    def to_msn(self) -> str:
        lines = [f"title: {self.title}"]
        if self.subtitle:
            lines.append(f"subtitle: {self.subtitle}")
        lines.append(f"composer: {self.composer}")
        if self.style:
            lines.append(f"style: {self.style}")
        lines.append(f"key: {self.key}")
        lines.append(f"time: {self.time[0]}/{self.time[1]}")
        tempo = f"tempo: {int(round(self.tempo))}"
        if self.tempo_text:
            tempo += f' "{self.tempo_text}"'
        lines.append(tempo)
        for pid, inst, name in self.parts:
            lines.append(f'part: {pid} {inst} "{name}"' if name else f"part: {pid} {inst}")
        lines.append("")

        starts = self.bar_starts()
        for v in self.voices:
            if any(x.dur.denominator % 3 == 0 and x.tuplet is None for x in v.notes):
                group_tuplets(v.notes)
            _match_slurs(v.notes)
        by_voice = {v.label: _Cursor(v) for v in self.voices}
        pickup_bar = self.pickup > 0
        for b in range(1, self.bars + 1):
            number = b - 1 if pickup_bar else b
            head = f"m{number}"
            info = self.bar_info.get(b)
            if info is not None:
                head += _bar_attributes(info)
            lines.append(head)
            t = self.time_at(b)
            length = self.pickup if (pickup_bar and b == 1) else bar_length(t)
            bar_start = starts[b - 1] if not (pickup_bar and b == 1) else F(0)
            bar_time = t
            for v in self.voices:
                tokens = by_voice[v.label].bar(bar_start, length, bar_time,
                                               pickup=(pickup_bar and b == 1))
                if tokens is None:
                    continue
                lines.append(f"  {v.label}: {tokens}")
            chords = self.harmony.get(b)
            if chords:
                lines.append("  H: " + " ".join(f"{sym}:{_dur_code(d)}" for d, sym in chords))
        return "\n".join(lines) + "\n"


def _match_slurs(notes: list[Note]) -> None:
    """Every slur that ends must have begun, and every slur that begins must
    end — whatever happened to the notes between."""
    open_at: list[Note] = []
    for n in sorted(notes, key=lambda x: x.onset):
        for _ in range(n.slur_start):
            open_at.append(n)
        if n.slur_stop:
            closed = min(n.slur_stop, len(open_at))
            for _ in range(closed):
                open_at.pop()
            n.slur_stop = closed
    for n in open_at:
        n.slur_start = max(0, n.slur_start - 1)


def _bar_attributes(info: BarInfo) -> str:
    out = ""
    if info.key is not None:
        out += f' key="{info.key}"'
    if info.time is not None:
        out += f" time={info.time[0]}/{info.time[1]}"
    if info.tempo is not None:
        out += f" tempo={int(round(info.tempo))}"
        if info.tempo_text:
            out += f' "{info.tempo_text}"'
    elif info.tempo_text:
        out += f' tempo="{info.tempo_text}"'
    if info.mark:
        out += f' mark="{info.mark}"'
    if info.text:
        out += f' text="{info.text}"'
    for staff, clef in info.clefs.items():
        out += f" clef.{staff}={clef}"
    if info.barline:
        out += f" barline={info.barline}"
    return out


def _dur_code(d: F) -> str:
    return _CODE.get(d, "q")


class _Cursor:
    """Writes one voice bar by bar, carrying ties and slurs across bar lines."""

    def __init__(self, voice: Voice):
        self.voice = voice
        self.notes = sorted(voice.notes, key=lambda n: n.onset)
        self.marks = sorted(voice.marks, key=lambda m: m.onset)
        self.i = 0          # next note not yet fully written
        self.mi = 0
        self.carry: Note | None = None     # a note continuing from the previous bar
        self.carry_left = F(0)

    def bar(self, bar_start: F, length: F, time: tuple[int, int], pickup: bool = False):
        bar_end = bar_start + length
        tokens: list[str] = []
        pos = bar_start
        wrote_note = False

        def gap(until: F) -> None:
            nonlocal pos
            if until <= pos:
                return
            code = "s" if self.voice.secondary else "r"
            for v in split_in_bar(pos - bar_start + (_pickup_shift(time, length) if pickup else 0),
                                  until - pos, time, rest=True):
                tokens.append(f"{code}:{_CODE.get(v, 'q')}")
            pos = until

        def emit_marks(upto: F, inclusive: bool) -> None:
            while self.mi < len(self.marks) and (
                    self.marks[self.mi].onset < upto or
                    (inclusive and self.marks[self.mi].onset == upto)):
                m = self.marks[self.mi]
                if m.onset < bar_start:
                    # A marking that fell before this bar (between notes of a
                    # long tie, say): write it at the start of this one.
                    pass
                tokens.append(_mark_token(m))
                self.mi += 1

        # a note tied over from the last bar
        if self.carry is not None:
            n = self.carry
            take = min(self.carry_left, length)
            emit_marks(bar_start, inclusive=True)
            tokens.extend(_note_tokens(n, pos - bar_start, take, time,
                                       tie_out=(take < self.carry_left) or n.tie,
                                       first_piece=False, last_piece=take >= self.carry_left))
            wrote_note = True
            pos += take
            self.carry_left -= take
            if self.carry_left <= 0:
                self.carry = None
            else:
                return " ".join(tokens)

        while self.i < len(self.notes) and self.notes[self.i].onset < bar_end:
            n = self.notes[self.i]
            if n.onset < pos:
                # overlapping note in the same voice: clip it (the composer
                # should never do this, but a clipped note beats a broken bar)
                if n.end <= pos:
                    self.i += 1
                    continue
                n = _clip(n, pos)
            emit_marks(n.onset, inclusive=True)
            gap(n.onset)
            if n.tuplet is not None and n.tuplet_start:
                group = [n]
                j = self.i + 1
                while j < len(self.notes) and not group[-1].tuplet_stop:
                    group.append(self.notes[j])
                    j += 1
                tokens.append(_tuplet_tokens(group, self.marks, self))
                pos = group[-1].end
                self.i = j
                wrote_note = True
                continue
            take = min(n.end, bar_end) - n.onset
            tokens.extend(_note_tokens(n, n.onset - bar_start, take, time,
                                       tie_out=(n.end > bar_end) or n.tie,
                                       first_piece=True, last_piece=n.end <= bar_end))
            wrote_note = wrote_note or not n.is_rest
            pos = n.onset + take
            self.i += 1
            if n.end > bar_end:
                self.carry = n
                self.carry_left = n.end - bar_end
                break
        emit_marks(bar_end, inclusive=False)
        if pos < bar_end:
            if not wrote_note and not tokens:
                return None if self.voice.secondary else "R"
            gap(bar_end)
        if not wrote_note and all(t.startswith(("r:", "s:")) or t.startswith("!") or
                                  t.startswith('"') for t in tokens):
            if self.voice.secondary:
                return None
            marks = [t for t in tokens if not t.startswith(("r:", "s:"))]
            return " ".join(marks + ["R"]) if not pickup else " ".join(tokens)
        return " ".join(tokens)


def _pickup_shift(time: tuple[int, int], length: F) -> F:
    return bar_length(time) - length


def _clip(n: Note, start: F) -> Note:
    from dataclasses import replace
    return replace(n, onset=start, dur=n.end - start, graces=[], slur_start=0)


def _mark_token(m: Mark) -> str:
    if m.kind == "dyn":
        return f"!{m.value}"
    if m.kind in ("cresc", "dim", "end", "ped", "pedup"):
        return f"!{m.kind}"
    if m.kind == "above":
        return f'^"{m.value}"'
    if m.kind == "below":
        return f'_"{m.value}"'
    return f'"{m.value}"'


def _pitches_token(pitches: list[Pitch], ties: list[bool] | None = None) -> str:
    ties = ties or [False] * len(pitches)
    if len(pitches) == 1:
        return pitch_token(pitches[0]) + ("~" if ties[0] else "")
    inner = " ".join(pitch_token(p) + ("~" if t else "") for p, t in zip(pitches, ties))
    return f"[{inner}]"


def _note_tokens(n: Note, start_in_bar: F, dur: F, time: tuple[int, int], *,
                 tie_out: bool, first_piece: bool, last_piece: bool) -> list[str]:
    values = split_in_bar(start_in_bar, dur, time, rest=n.is_rest)
    out: list[str] = []
    for k, v in enumerate(values):
        first = first_piece and k == 0
        last = last_piece and k == len(values) - 1
        code = _CODE.get(v, "q")
        if n.is_rest:
            out.append(f"r:{code}")
            continue
        tie_here = (k < len(values) - 1) or tie_out
        tok = ""
        if first and n.graces:
            kind = "g" if len(n.graces) > 1 else n.grace_kind
            gdur = "t" if len(n.graces) > 1 else ("e" if kind == "app" else "s")
            tok += "{" + kind + " " + " ".join(f"{pitch_token(g)}:{gdur}" for g in n.graces) + "} "
        if first and n.slur_start:
            tok += "(" * n.slur_start
        tok += _pitches_token(n.pitches, [tie_here] * len(n.pitches)) + ":" + code
        if first:
            for m in n.marks:
                if m in ("fermata",) and not last:
                    continue
                tok += "+" + m
            if n.lyric:
                tok += f'@"{n.lyric}"'
        elif last and "fermata" in n.marks:
            tok += "+fermata"
        if last and n.slur_stop:
            tok += ")" * n.slur_stop
        out.append(tok)
    return out


def _tuplet_tokens(group: list[Note], marks: list[Mark], cursor: "_Cursor") -> str:
    actual, normal = group[0].tuplet or (3, 2)
    inner = []
    for n in group:
        while cursor.mi < len(marks) and marks[cursor.mi].onset <= n.onset:
            inner.append(_mark_token(marks[cursor.mi]))
            cursor.mi += 1
        written = n.dur * F(actual, normal)
        code = _CODE.get(written, "e")
        if n.is_rest:
            inner.append(f"r:{code}")
            continue
        tok = "(" * n.slur_start
        tok += _pitches_token(n.pitches, [n.tie] * len(n.pitches)) + ":" + code
        for m in n.marks:
            tok += "+" + m
        tok += ")" * n.slur_stop
        inner.append(tok)
    ratio = f"{actual}" if (actual, normal) in ((3, 2), (5, 4), (6, 4), (7, 4)) \
        else f"{actual}:{normal}"
    return "{" + ratio + " " + " ".join(inner) + "}"
