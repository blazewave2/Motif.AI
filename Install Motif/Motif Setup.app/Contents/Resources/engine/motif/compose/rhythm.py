"""Rhythmic cell generation.

Rhythm is generated from a *library of idiomatic cells* rather than by random
subdivision: recurring cells are what make a line sound authored.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from ..score import (DIVISIONS, EIGHTH, HALF, QUARTER, SIXTEENTH, THIRTYSECOND,
                     Tuplet, WHOLE)

Q, E, S, H, W, T = QUARTER, EIGHTH, SIXTEENTH, HALF, WHOLE, THIRTYSECOND
DQ, DE, DH = Q + E, E + S, H + Q          # dotted values


@dataclass(frozen=True)
class Cell:
    """A rhythmic cell: durations in ticks plus a weight and a label."""

    durations: tuple[int, ...]
    weight: float = 1.0
    label: str = ""

    @property
    def total(self) -> int:
        return sum(self.durations)


def _c(*d: int, w: float = 1.0, label: str = "") -> Cell:
    return Cell(tuple(d), w, label)


#: Cells that fill exactly one quarter-note beat.
SIMPLE_BEAT_CELLS: list[Cell] = [
    _c(Q, w=3.0, label="quarter"),
    _c(E, E, w=2.5, label="two-eighths"),
    _c(DE, S, w=1.6, label="dotted-eighth-sixteenth"),
    _c(S, DE, w=0.7, label="lombard"),
    _c(S, S, S, S, w=1.4, label="four-sixteenths"),
    _c(E, S, S, w=1.2, label="eighth-two-sixteenths"),
    _c(S, S, E, w=1.1, label="two-sixteenths-eighth"),
    _c(S, E, S, w=0.5, label="syncopated-sixteenths"),
]

#: Cells filling a dotted-quarter beat (compound meters: 6/8, 9/8, 12/8).
COMPOUND_BEAT_CELLS: list[Cell] = [
    _c(E, E, E, w=3.0, label="three-eighths"),
    _c(DQ, w=2.0, label="dotted-quarter"),
    _c(Q, E, w=2.2, label="quarter-eighth"),
    _c(E, Q, w=1.0, label="eighth-quarter"),
    _c(E, E, S, S, w=1.1, label="two-eighths-two-sixteenths"),
    _c(S, S, E, E, w=1.0, label="two-sixteenths-two-eighths"),
    _c(S, S, S, S, S, S, w=0.8, label="six-sixteenths"),
    _c(DE, S, E, w=0.9, label="dotted-figure"),
]

#: Two-beat cells that give a phrase its longer-range profile.
TWO_BEAT_CELLS: list[Cell] = [
    _c(H, w=2.0, label="half"),
    _c(DQ, E, w=2.4, label="dotted-quarter-eighth"),
    _c(Q, Q, w=2.0, label="two-quarters"),
    _c(E, Q, E, w=1.3, label="syncopation"),
    _c(Q, E, E, w=1.8, label="quarter-two-eighths"),
    _c(E, E, Q, w=1.5, label="two-eighths-quarter"),
    _c(DE, S, Q, w=1.2, label="dotted-then-quarter"),
    _c(E, E, E, E, w=1.6, label="four-eighths"),
    _c(Q, S, S, E, w=0.9, label="mixed"),
]

#: One-bar gestures that identify a dance or a composer immediately. A mazurka
#: is not a waltz because of its harmony; it is the lean on the second beat.
SIGNATURE_BARS: dict[str, list[tuple[tuple[int, ...], tuple[int, int]]]] = {
    "mazurka": [((E, S, S, Q, Q), (3, 4)),          # dotted lean into beat two
                ((DE, S, Q, Q), (3, 4)),
                ((Q, E, E, Q), (3, 4))],
    "waltz": [((DQ, E, Q), (3, 4)), ((H, Q), (3, 4)), ((Q, Q, Q), (3, 4))],
    "polonaise": [((E, S, S, E, E, E, E), (3, 4)), ((Q, E, E, Q), (3, 4))],
    "sarabande": [((Q, H), (3, 4)), ((Q, DQ, E), (3, 4))],
    "siciliano": [((DE, S, E, DE, S, E), (6, 8)), ((Q, E, Q, E), (6, 8))],
    "gigue": [((E, E, E, E, E, E), (6, 8)), ((Q, E, E, E, E), (6, 8))],
    "habanera": [((DE, S, E, E), (2, 4))],
    "march": [((DE, S, Q, DE, S, Q), (4, 4)), ((Q, E, E, Q, Q), (4, 4))],
    "barcarolle": [((Q, E, Q, E), (6, 8)), ((DQ, DQ), (6, 8))],
    "scotch_snap": [((S, DE, Q, Q, Q), (4, 4))],
    "hemiola": [((Q, Q, Q, Q, Q, Q), (3, 4))],
}

#: Which signatures belong to which style, and how strongly.
STYLE_SIGNATURES: dict[str, list[tuple[str, float]]] = {
    "chopin": [("mazurka", 0.30), ("waltz", 0.22), ("barcarolle", 0.10)],
    "bach": [("gigue", 0.16), ("sarabande", 0.14)],
    "handel": [("sarabande", 0.22), ("gigue", 0.16)],
    "scarlatti": [("gigue", 0.14)],
    "mozart": [("march", 0.10), ("waltz", 0.10)],
    "haydn": [("march", 0.12)],
    "beethoven": [("march", 0.16), ("scotch_snap", 0.08)],
    "schubert": [("waltz", 0.18), ("siciliano", 0.10)],
    "brahms": [("hemiola", 0.26), ("waltz", 0.12)],
    "liszt": [("polonaise", 0.14), ("march", 0.12)],
    "rachmaninoff": [("barcarolle", 0.12), ("march", 0.12)],
    "tchaikovsky": [("waltz", 0.30), ("march", 0.12)],
    "grieg": [("waltz", 0.16), ("mazurka", 0.10)],
    "debussy": [("siciliano", 0.10), ("barcarolle", 0.12)],
    "satie": [("sarabande", 0.16)],
}


#: Per-style weighting so a Bach line and a Chopin line breathe differently.
STYLE_RHYTHM_BIAS: dict[str, dict[str, float]] = {
    "bach": {"four-sixteenths": 2.4, "two-eighths": 2.2, "quarter": 1.4,
             "dotted-eighth-sixteenth": 1.0, "syncopation": 0.4, "lombard": 0.2},
    "handel": {"dotted-eighth-sixteenth": 2.2, "four-sixteenths": 1.8, "quarter": 1.5},
    "scarlatti": {"four-sixteenths": 2.2, "two-eighths": 1.8, "eighth-two-sixteenths": 1.6},
    "mozart": {"two-eighths": 2.2, "quarter": 2.0, "eighth-two-sixteenths": 1.8,
               "four-sixteenths": 1.5, "dotted-quarter-eighth": 1.8, "lombard": 0.3},
    "haydn": {"quarter": 2.2, "two-eighths": 2.0, "dotted-eighth-sixteenth": 1.4,
              "two-sixteenths-eighth": 1.5, "syncopation": 0.8},
    "beethoven": {"quarter": 2.2, "dotted-eighth-sixteenth": 1.8, "syncopation": 1.4,
                  "four-sixteenths": 1.6},
    "schubert": {"two-eighths": 2.0, "dotted-quarter-eighth": 2.0, "quarter": 1.8},
    "chopin": {"dotted-quarter-eighth": 2.2, "half": 1.8, "quarter": 1.6,
               "two-eighths": 1.4, "syncopation": 1.2, "lombard": 0.9},
    "liszt": {"four-sixteenths": 2.0, "syncopation": 1.5, "dotted-eighth-sixteenth": 1.6,
              "half": 1.4},
    "rachmaninoff": {"half": 2.2, "dotted-quarter-eighth": 2.2, "quarter": 2.0,
                     "syncopation": 1.6, "two-eighths": 1.4},
    "scriabin": {"syncopation": 2.0, "dotted-quarter-eighth": 1.8, "half": 1.6,
                 "lombard": 1.2},
    "debussy": {"half": 2.0, "two-eighths": 1.6, "four-sixteenths": 1.4, "quarter": 1.6},
    "brahms": {"syncopation": 2.0, "dotted-quarter-eighth": 1.8, "quarter": 1.8},
    "tchaikovsky": {"quarter": 2.0, "dotted-quarter-eighth": 2.0, "two-eighths": 1.8},
    "satie": {"half": 2.4, "quarter": 2.2, "two-quarters": 2.0},
}


class RhythmGenerator:
    def __init__(self, rng: random.Random, style: str = "classical",
                 time: tuple[int, int] = (4, 4), density: float = 0.5):
        self.rng = rng
        self.style = style
        self.time = time
        self.density = max(0.0, min(1.0, density))
        self.bias = STYLE_RHYTHM_BIAS.get(style, {})

    # -- meter facts ------------------------------------------------------
    @property
    def is_compound(self) -> bool:
        beats, unit = self.time
        return unit == 8 and beats in (6, 9, 12)

    @property
    def beat_ticks(self) -> int:
        beats, unit = self.time
        if self.is_compound:
            return DIVISIONS * 3 // 2
        return int(DIVISIONS * 4 / unit)

    @property
    def bar_ticks(self) -> int:
        beats, unit = self.time
        return int(beats * DIVISIONS * 4 / unit)

    @property
    def beats_per_bar(self) -> int:
        return max(1, self.bar_ticks // self.beat_ticks)

    # -- selection --------------------------------------------------------
    def _weight(self, cell: Cell) -> float:
        w = cell.weight * self.bias.get(cell.label, 1.0)
        n = len(cell.durations)
        # `density` pushes toward faster or slower subdivisions.
        w *= (1.0 + self.density * (n - 1) * 0.55) if self.density > 0.5 else \
             (1.0 + (0.5 - self.density) * (2.2 - n) * 0.8)
        return max(0.02, w)

    def _pick(self, cells: list[Cell]) -> Cell:
        weights = [self._weight(c) for c in cells]
        return self.rng.choices(cells, weights=weights, k=1)[0]

    def beat(self) -> list[int]:
        cells = COMPOUND_BEAT_CELLS if self.is_compound else SIMPLE_BEAT_CELLS
        return list(self._pick(cells).durations)

    # -- signature gestures ----------------------------------------------
    def signature_bar(self) -> list[int] | None:
        """A one-bar gesture characteristic of this style, if one fits."""
        options = STYLE_SIGNATURES.get(self.style)
        if not options:
            return None
        for name, chance in options:
            if self.rng.random() >= chance:
                continue
            for durations, meter in SIGNATURE_BARS.get(name, []):
                if meter == self.time and sum(durations) == self.bar_ticks:
                    return list(durations)
        return None

    def triplet_beat(self) -> list[tuple[int, Tuplet]]:
        """Three notes in the space of one beat, correctly grouped."""
        beat = self.beat_ticks
        each = beat // 3
        if each * 3 != beat:
            return []
        base = "eighth" if each >= SIXTEENTH else "16th"
        return [(each, Tuplet(3, 2, base, start=(i == 0), stop=(i == 2), number=1))
                for i in range(3)]

    def bar_events(self, *, cadential: bool = False,
                   sustain_end: bool = False) -> list[tuple[int, Tuplet | None]]:
        """One bar as (duration, tuplet) pairs, occasionally in triplets."""
        sig = None if cadential else self.signature_bar()
        if sig is not None:
            return [(d, None) for d in sig]

        # A triplet turn is one of the plainest ways a line stops sounding
        # metronomic, so it is offered on any beat that can hold one.
        if (not cadential and not self.is_compound
                and self.rng.random() < 0.14 + self.density * 0.12):
            out: list[tuple[int, Tuplet | None]] = []
            for i in range(self.beats_per_bar):
                trip = self.triplet_beat()
                if trip and self.rng.random() < 0.45:
                    out.extend(trip)
                else:
                    out.extend((d, None) for d in self.beat())
            if out and sum(d for d, _ in out) == self.bar_ticks:
                return out

        return [(d, None) for d in self.bar(cadential=cadential,
                                            sustain_end=sustain_end)]

    def bar(self, *, cadential: bool = False, sustain_end: bool = False) -> list[int]:
        """One bar of rhythm.  ``cadential`` lengthens the final note."""
        if cadential:
            return self._cadential_bar()
        out: list[int] = []
        remaining = self.beats_per_bar
        while remaining > 0:
            if (not self.is_compound and remaining >= 2 and self.beat_ticks == QUARTER
                    and self.rng.random() < 0.45):
                cell = self._pick(TWO_BEAT_CELLS)
                out.extend(cell.durations)
                remaining -= 2
            else:
                out.extend(self.beat())
                remaining -= 1
        if sustain_end and len(out) > 1:
            out = _merge_tail(out, self.beat_ticks)
        return out

    def _cadential_bar(self) -> list[int]:
        """A closing bar: motion into the cadence, then a long note."""
        total = self.bar_ticks
        if self.rng.random() < 0.55:
            head = self.beat()
            rest = total - sum(head)
            return head + [rest] if rest > 0 else head
        long = max(self.beat_ticks, total // 2)
        head_ticks = total - long
        head: list[int] = []
        acc = 0
        while acc < head_ticks:
            for d in self.beat():
                if acc + d > head_ticks:
                    break
                head.append(d)
                acc += d
            if not head:
                head = [head_ticks]
                acc = head_ticks
        left = total - sum(head)
        return head + ([left] if left > 0 else [])

    def phrase(self, bars: int, *, cadence_bar: bool = True,
               anacrusis: int = 0) -> list[list[tuple[int, Tuplet | None]]]:
        """A phrase of rhythm, bar by bar, as (duration, tuplet) pairs.

        The opening bar is the phrase's rhythmic idea; later bars either echo it
        in varied form or answer it with something new, so the line neither
        repeats mechanically nor wanders.
        """
        out: list[list[tuple[int, Tuplet | None]]] = []
        seed = self.bar_events()
        for i in range(bars):
            last = i == bars - 1
            if last and cadence_bar:
                out.append(self.bar_events(cadential=True))
            elif i == 0:
                out.append(list(seed))
            elif i % 4 == 0 and self.rng.random() < 0.5:
                out.append(list(seed))                       # restate the idea
            elif self.rng.random() < 0.42 and not any(t for _, t in seed):
                plain = _vary([d for d, _ in seed], self.rng)
                out.append([(d, None) for d in plain])       # varied echo
            else:
                out.append(self.bar_events(sustain_end=(i % 4 == 3)))
        if anacrusis:
            out.insert(0, [(d, None) for d in self.upbeat(anacrusis)])
        return out

    def upbeat(self, ticks: int) -> list[int]:
        if ticks <= EIGHTH:
            return [ticks]
        if ticks <= QUARTER:
            return [ticks] if self.rng.random() < 0.6 else [EIGHTH, EIGHTH][:2]
        cells = [[QUARTER, EIGHTH], [EIGHTH, EIGHTH, EIGHTH], [QUARTER, QUARTER]]
        for c in cells:
            if sum(c) == ticks:
                return c
        return [ticks]

    def ostinato(self, subdivision: int = EIGHTH) -> list[int]:
        n = max(1, self.bar_ticks // subdivision)
        return [subdivision] * n

    def tuplet_group(self, span: int, count: int) -> tuple[list[int], int, int]:
        """``count`` notes in the space of ``span`` ticks; returns (durs, actual, normal)."""
        normal = {3: 2, 5: 4, 6: 4, 7: 4, 9: 8, 2: 3, 4: 3}.get(count, count - 1)
        each = span // count
        durs = [each] * count
        durs[-1] += span - each * count
        return durs, count, normal


def _merge_tail(durations: list[int], beat: int) -> list[int]:
    if len(durations) < 2:
        return durations
    out = durations[:-2] + [durations[-2] + durations[-1]]
    return out


def _vary(bar: list[int], rng: random.Random) -> list[int]:
    """Small rhythmic variation that keeps the bar length intact."""
    if len(bar) < 2:
        return bar
    b = list(bar)
    op = rng.random()
    if op < 0.35:                                  # split a note in two
        i = rng.randrange(len(b))
        if b[i] >= EIGHTH * 2:
            half = b[i] // 2
            b[i:i + 1] = [half, b[i] - half]
    elif op < 0.65 and len(b) >= 3:                # merge two adjacent notes
        i = rng.randrange(len(b) - 1)
        b[i:i + 2] = [b[i] + b[i + 1]]
    elif op < 0.85 and len(b) >= 2:                # dot the pair
        i = rng.randrange(len(b) - 1)
        a, c = b[i], b[i + 1]
        if a == c and a >= SIXTEENTH * 2:
            b[i], b[i + 1] = a + a // 2, c - a // 2
    return [d for d in b if d > 0]


def scale_durations(durations: list[int], factor: float) -> list[int]:
    """Augment or diminish, snapping to the 32nd-note grid."""
    out = [max(THIRTYSECOND, int(round(d * factor / THIRTYSECOND)) * THIRTYSECOND)
           for d in durations]
    return out
