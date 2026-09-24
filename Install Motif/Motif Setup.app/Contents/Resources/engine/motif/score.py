"""The internal score representation everything else composes into.

Durations are integers in *divisions* (``DIVISIONS`` per quarter note) so that
triplets, dotted values and 32nds are all exact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .theory.pitch import Key, Pitch

DIVISIONS = 10080  # ticks per quarter: exact for 3-, 5-, 6-, 7- and 9-note tuplets

WHOLE = DIVISIONS * 4
HALF = DIVISIONS * 2
QUARTER = DIVISIONS
EIGHTH = DIVISIONS // 2
SIXTEENTH = DIVISIONS // 4
THIRTYSECOND = DIVISIONS // 8
SIXTYFOURTH = DIVISIONS // 16

#: MusicXML note-type names by tick value.
NOTE_TYPES: list[tuple[int, str]] = [
    (DIVISIONS * 8, "breve"), (WHOLE, "whole"), (HALF, "half"), (QUARTER, "quarter"),
    (EIGHTH, "eighth"), (SIXTEENTH, "16th"), (THIRTYSECOND, "32nd"),
    (SIXTYFOURTH, "64th"), (SIXTYFOURTH // 2, "128th"),
]


def note_type_and_dots(ticks: int) -> tuple[str, int]:
    """Nearest notated value plus augmentation dots for a tick count."""
    for base, name in NOTE_TYPES:
        if ticks == base:
            return name, 0
        if ticks == base + base // 2:
            return name, 1
        if ticks == base + base // 2 + base // 4:
            return name, 2
        if ticks == base + base // 2 + base // 4 + base // 8:
            return name, 3
    # Not exactly notatable: fall back to the largest value that fits.
    for base, name in NOTE_TYPES:
        if ticks >= base:
            return name, 0
    return "64th", 0


def is_notatable(ticks: int) -> bool:
    for base, _ in NOTE_TYPES:
        for dots in range(4):
            total = base
            add = base
            for _ in range(dots):
                add //= 2
                total += add
            if ticks == total:
                return True
    return False


def split_duration(ticks: int, offset: int, beat_ticks: int, bar_ticks: int) -> list[int]:
    """Split a duration into notatable, beat-respecting components.

    A note that crosses a beat boundary in an unreadable way gets tied instead,
    which is what separates engraved-looking output from a MIDI dump.
    """
    out: list[int] = []
    remaining = ticks
    pos = offset
    guard = 0
    while remaining > 0 and guard < 64:
        guard += 1
        # Longest notatable value that neither leaves the bar nor obscures the beat.
        best = 0
        for base, _ in NOTE_TYPES:
            for dots in range(3):
                total, add = base, base
                for _ in range(dots):
                    add //= 2
                    total += add
                if total > remaining:
                    continue
                if pos + total > bar_ticks:
                    continue
                # Allow crossing a beat only when the note starts on a beat and
                # spans whole beats, or stays inside a single beat.
                start_beat, end_beat = pos // beat_ticks, (pos + total - 1) // beat_ticks
                if start_beat != end_beat:
                    if pos % beat_ticks != 0 or total % beat_ticks != 0:
                        # half-bar spans are fine in compound/duple meters
                        if not (pos % (beat_ticks * 2) == 0 and total % beat_ticks == 0):
                            continue
                if total > best:
                    best = total
        if best == 0:
            best = min(remaining, SIXTEENTH)
        out.append(best)
        remaining -= best
        pos += best
    return out or [ticks]


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
@dataclass
class Tuplet:
    actual: int
    normal: int
    base_type: str = "eighth"
    start: bool = False
    stop: bool = False
    number: int = 1


@dataclass
class Note:
    """One notehead-bearing event.  ``pitches`` empty means a rest."""

    pitches: list[Pitch] = field(default_factory=list)
    duration: int = QUARTER
    voice: int = 1
    staff: int = 1
    tie_start: bool = False
    tie_stop: bool = False
    slur_start: int = 0            # slur id, 0 = none
    slur_stop: int = 0
    articulations: list[str] = field(default_factory=list)   # staccato, accent, tenuto...
    ornaments: list[str] = field(default_factory=list)       # trill-mark, turn, mordent...
    technical: list[str] = field(default_factory=list)       # fingering etc.
    grace: bool = False
    grace_slash: bool = False
    tuplet: Tuplet | None = None
    lyric: str | None = None
    velocity: int = 80
    stem: str | None = None        # "up" / "down" / None (auto)
    beam: list[str] = field(default_factory=list)            # per-level begin/continue/end
    notations_text: list[str] = field(default_factory=list)
    tremolo: int = 0
    cue: bool = False
    chord_symbol: "ChordSymbol | None" = None
    fermata: bool = False
    arpeggiate: bool = False
    grace_type: str = ""           # written value of a grace note ("16th", "eighth")
    print_object: bool = True      # False: an invisible (spacer) rest
    measure_rest: bool = False     # a whole-bar rest, centred whatever the metre
    #: Per-pitch ties for chords where only some notes are held over. None
    #: means the tie flags above apply to every pitch in the chord.
    tie_start_pitches: list[int] | None = None
    tie_stop_pitches: list[int] | None = None
    more_slurs: list[tuple[str, int]] = field(default_factory=list)  # nested slurs
    lyric_syllabic: str = ""       # single | begin | middle | end

    @property
    def is_rest(self) -> bool:
        return not self.pitches

    @property
    def top(self) -> Pitch | None:
        return max(self.pitches, key=lambda p: p.midi) if self.pitches else None

    @property
    def bottom(self) -> Pitch | None:
        return min(self.pitches, key=lambda p: p.midi) if self.pitches else None

    def copy(self) -> "Note":
        import copy as _c
        return _c.deepcopy(self)


@dataclass
class ChordSymbol:
    root: Pitch
    kind: str = "major"
    bass: Pitch | None = None
    text: str = ""


@dataclass
class Direction:
    """A marking attached to a point in a measure."""

    kind: str                       # dynamics, words, wedge, pedal, metronome, rehearsal, octave-shift
    value: str = ""                 # "p", "cresc.", "start"/"stop", tempo number...
    offset: int = 0                 # ticks from the start of the measure
    staff: int = 1
    placement: str = "below"
    voice: int = 1
    extra: dict = field(default_factory=dict)


@dataclass
class Measure:
    number: int = 1
    voices: dict[int, list[Note]] = field(default_factory=dict)
    directions: list[Direction] = field(default_factory=list)
    key: Key | None = None          # only when it changes
    time: tuple[int, int] | None = None
    clefs: dict[int, str] | None = None   # staff -> clef name
    barline: str | None = None            # "light-heavy", "repeat-end"...
    repeat_start: bool = False
    repeat_end: bool = False
    ending: int | None = None
    width: float | None = None
    implicit: bool = False                # a pickup bar, not counted in numbering
    ending_type: str = ""                 # start | stop | both (volta brackets)

    def add(self, note: Note) -> Note:
        self.voices.setdefault(note.voice, []).append(note)
        return note

    def extend(self, notes: Iterable[Note]) -> None:
        for n in notes:
            self.add(n)

    def voice_duration(self, voice: int) -> int:
        return sum(n.duration for n in self.voices.get(voice, []) if not n.grace)

    @property
    def total_duration(self) -> int:
        return max((self.voice_duration(v) for v in self.voices), default=0)


@dataclass
class Part:
    id: str = "P1"
    name: str = "Piano"
    abbreviation: str = "Pno."
    midi_program: int = 0
    midi_channel: int = 1
    staves: int = 1
    clefs: dict[int, str] = field(default_factory=lambda: {1: "G"})
    measures: list[Measure] = field(default_factory=list)
    volume: float = 78.0
    pan: float = 0.0
    #: Written-to-sounding transposition as MusicXML spells it
    #: (diatonic, chromatic, octave-change); None for concert-pitch parts.
    transpose: tuple[int, int, int] | None = None
    instrument_sound: str = ""
    extra: dict = field(default_factory=dict)

    def measure(self, n: int) -> Measure:
        """1-based measure access, creating intervening bars as needed."""
        if n < 1:
            raise ValueError(f"measure numbers are 1-based, got {n}")
        while len(self.measures) < n:
            self.measures.append(Measure(number=len(self.measures) + 1))
        return self.measures[n - 1]


@dataclass
class TempoMark:
    measure: int
    bpm: float                     # beats per minute of ``beat_unit``
    beat_unit: str = "quarter"
    text: str = ""
    dotted: bool = False
    offset: int = 0                # ticks into the measure
    visible: bool = True           # False: changes playback only (rit., accel.)

    @property
    def quarter_bpm(self) -> float:
        """The same tempo counted in quarter notes, for playback."""
        unit = {"whole": 4.0, "half": 2.0, "quarter": 1.0, "eighth": 0.5,
                "16th": 0.25}.get(self.beat_unit, 1.0)
        if self.dotted:
            unit *= 1.5
        return self.bpm * unit


@dataclass
class Score:
    title: str = "Untitled"
    subtitle: str = ""
    composer: str = "Generated by Motif.ai"
    lyricist: str = ""
    copyright: str = ""
    key: Key = field(default_factory=Key)
    time: tuple[int, int] = (4, 4)
    tempo: float = 100.0
    parts: list[Part] = field(default_factory=list)
    tempos: list[TempoMark] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def measure_count(self) -> int:
        return max((len(p.measures) for p in self.parts), default=0)

    def part(self, pid: str) -> Part | None:
        return next((p for p in self.parts if p.id == pid), None)

    def add_part(self, part: Part) -> Part:
        self.parts.append(part)
        return part

    def pad_to_equal_length(self) -> None:
        """Make every part the same number of measures, filling with rests."""
        n = self.measure_count
        bar_ticks = bar_duration(self.time)
        for p in self.parts:
            for i in range(1, n + 1):
                m = p.measure(i)
                if not m.voices:
                    for staff in range(1, p.staves + 1):
                        m.add(Note([], bar_ticks, voice=(staff - 1) * 4 + 1, staff=staff))


def bar_duration(time: tuple[int, int]) -> int:
    beats, unit = time
    return int(beats * (DIVISIONS * 4 / unit))


def beat_duration(time: tuple[int, int]) -> int:
    """The felt beat: a dotted quarter in compound meters, else the notated unit."""
    beats, unit = time
    if unit == 8 and beats % 3 == 0 and beats > 3:
        return DIVISIONS * 3 // 2
    return int(DIVISIONS * 4 / unit)


def beats_per_bar(time: tuple[int, int]) -> float:
    """Bar length measured in quarter notes."""
    return bar_duration(time) / DIVISIONS
