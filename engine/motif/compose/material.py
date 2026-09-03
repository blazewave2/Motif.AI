"""Motifs — the small cells a piece is actually built from — and their
classical transformations.  A piece that develops one motif sounds composed;
one that generates fresh material every bar sounds like noise.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, replace

from ..score import EIGHTH, QUARTER, SIXTEENTH, THIRTYSECOND
from ..theory.pitch import Key, Pitch


@dataclass
class Motif:
    """A cell stored as *scale-degree steps* plus a rhythm.

    Storing steps rather than semitones means a transposition automatically
    stays in key, and a shift from major to minor recolours the motif instead
    of breaking it.
    """

    steps: list[int] = field(default_factory=list)     # diatonic steps between notes
    rhythm: list[int] = field(default_factory=list)    # ticks, one per note
    name: str = "a"
    accents: list[bool] = field(default_factory=list)
    origin_degree: int = 1

    def __post_init__(self) -> None:
        n = len(self.rhythm)
        if len(self.steps) < n - 1:
            self.steps += [0] * (n - 1 - len(self.steps))
        self.steps = self.steps[: max(0, n - 1)]
        if len(self.accents) != n:
            self.accents = [i == 0 for i in range(n)]

    @property
    def length(self) -> int:
        return len(self.rhythm)

    @property
    def total_ticks(self) -> int:
        return sum(self.rhythm)

    @property
    def span(self) -> int:
        """Widest diatonic reach of the cell."""
        pos, lo, hi = 0, 0, 0
        for s in self.steps:
            pos += s
            lo, hi = min(lo, pos), max(hi, pos)
        return hi - lo

    @property
    def contour(self) -> str:
        net = sum(self.steps)
        if abs(net) <= 1 and self.span <= 2:
            return "static"
        return "rising" if net > 0 else "falling" if net < 0 else "arch"

    # -- classical transformations ---------------------------------------
    def transpose(self, steps: int) -> "Motif":
        return replace(self, origin_degree=self.origin_degree + steps,
                       name=self.name + "'")

    def invert(self) -> "Motif":
        return replace(self, steps=[-s for s in self.steps], name=self.name + "i")

    def retrograde(self) -> "Motif":
        return replace(self, steps=[-s for s in reversed(self.steps)],
                       rhythm=list(reversed(self.rhythm)),
                       accents=list(reversed(self.accents)), name=self.name + "r")

    def augment(self, factor: float = 2.0) -> "Motif":
        return replace(self, rhythm=[max(THIRTYSECOND, int(r * factor)) for r in self.rhythm],
                       name=self.name + "+")

    def diminish(self, factor: float = 0.5) -> "Motif":
        return self.augment(factor)

    def fragment(self, start: int = 0, count: int | None = None) -> "Motif":
        count = count if count is not None else max(2, self.length // 2)
        end = min(self.length, start + count)
        return replace(self, steps=self.steps[start:max(start, end - 1)],
                       rhythm=self.rhythm[start:end],
                       accents=self.accents[start:end], name=self.name + "f")

    def extend(self, extra_steps: list[int], extra_rhythm: list[int]) -> "Motif":
        return replace(self, steps=self.steps + extra_steps,
                       rhythm=self.rhythm + extra_rhythm,
                       accents=self.accents + [False] * len(extra_rhythm),
                       name=self.name + "e")

    def intervallic_expand(self, factor: float = 1.5) -> "Motif":
        """Widen every interval — a favourite Beethoven/Liszt device."""
        return replace(self, steps=[int(round(s * factor)) for s in self.steps],
                       name=self.name + "x")

    def rhythmic_displace(self, ticks: int) -> "Motif":
        return replace(self, name=self.name + "d")

    def smooth(self) -> "Motif":
        return replace(self, steps=[max(-2, min(2, s)) for s in self.steps],
                       name=self.name + "s")

    def sequence(self, count: int, step: int = -1) -> list["Motif"]:
        return [self.transpose(step * i) for i in range(count)]

    def realize(self, key: Key, start: Pitch, scale_variant: str | None = None) -> list[Pitch]:
        """Turn the step pattern into spelled pitches from a starting note."""
        pcs = key.scale_pcs_for(scale_variant) if scale_variant else key.scale_pcs
        out = [start]
        cur = start
        for step in self.steps:
            cur = cur.transpose_diatonic(step, key, pcs)
            out.append(cur)
        return out


def generate_motif(rng: random.Random, *, length: int = 4, rhythm: list[int] | None = None,
                   style: str = "classical", energy: float = 0.5) -> Motif:
    """Invent a memorable cell: mostly steps, one characteristic leap."""
    if rhythm is None:
        base = [QUARTER, EIGHTH, EIGHTH, QUARTER]
        rhythm = [base[i % len(base)] for i in range(length)]
    length = len(rhythm)

    shapes = [
        [1, 1, -1], [1, -1, 2], [2, -1, -1], [1, 1, 1], [-1, -1, 2],
        [4, -1, -1], [2, 2, -1], [-2, 1, 1], [1, 2, -1], [3, -1, -1],
        [1, -2, 1], [5, -1, -2], [-1, 2, -1],
    ]
    leap_bias = {"liszt": 1.6, "rachmaninoff": 1.3, "beethoven": 1.3, "scriabin": 1.2,
                 "bach": 0.85, "mozart": 0.95, "satie": 0.7, "debussy": 0.8}.get(style, 1.0)
    weights = []
    for sh in shapes:
        w = 1.0
        big = max(abs(s) for s in sh)
        w *= leap_bias ** (big - 1)
        w *= 1.0 + energy * (big - 1) * 0.25
        weights.append(w)
    shape = list(rng.choices(shapes, weights=weights, k=1)[0])

    while len(shape) < length - 1:
        prev = shape[-1]
        # After a leap, step back the other way; after a step, keep the line moving.
        if abs(prev) >= 3:
            shape.append(-1 if prev > 0 else 1)
        else:
            shape.append(rng.choice([1, -1, 1, -1, 2, -2, 0]))
    shape = shape[: max(0, length - 1)]
    return Motif(steps=shape, rhythm=list(rhythm), name="a")


def develop(motif: Motif, rng: random.Random, intensity: float = 0.5,
            style: str = "classical") -> Motif:
    """Pick a transformation appropriate to how intense the moment is."""
    light = [lambda m: m.transpose(rng.choice([1, -1, 2, -2])),
             lambda m: m,
             lambda m: m.smooth()]
    medium = [lambda m: m.invert(),
              lambda m: m.transpose(rng.choice([2, -2, 3, -3])),
              lambda m: m.fragment(0, max(2, m.length - 1)),
              lambda m: m.augment(1.5) if m.total_ticks < QUARTER * 6 else m.diminish()]
    heavy = [lambda m: m.retrograde(),
             lambda m: m.intervallic_expand(1.5),
             lambda m: m.diminish(),
             lambda m: m.invert().transpose(rng.choice([2, -2, 4, -4])),
             lambda m: m.fragment(m.length // 2)]
    pool = light if intensity < 0.35 else medium if intensity < 0.7 else heavy
    if style in ("bach", "handel") and intensity >= 0.35:
        pool = pool + [lambda m: m.invert(), lambda m: m.augment(2.0)]
    return rng.choice(pool)(motif)


# ---------------------------------------------------------------------------
# Contour planning
# ---------------------------------------------------------------------------
@dataclass
class Contour:
    """Registral plan for a phrase, expressed in diatonic steps around a centre."""

    points: list[float]          # relative height at evenly spaced positions
    peak_at: float = 0.62

    @staticmethod
    def arch(strength: float = 1.0, peak_at: float = 0.62) -> "Contour":
        return Contour([0.0, 0.45 * strength, 0.85 * strength, strength,
                        0.6 * strength, 0.15 * strength, -0.1 * strength], peak_at)

    @staticmethod
    def descending(strength: float = 1.0) -> "Contour":
        return Contour([strength, 0.75 * strength, 0.5 * strength, 0.3 * strength,
                        0.1 * strength, -0.15 * strength, -0.3 * strength], 0.0)

    @staticmethod
    def rising(strength: float = 1.0) -> "Contour":
        return Contour([-0.3 * strength, -0.05 * strength, 0.2 * strength,
                        0.45 * strength, 0.7 * strength, 0.9 * strength, strength], 1.0)

    @staticmethod
    def wave(strength: float = 1.0) -> "Contour":
        return Contour([0.0, 0.6 * strength, 0.1 * strength, 0.75 * strength,
                        0.2 * strength, 0.9 * strength, 0.3 * strength], 0.78)

    @staticmethod
    def flat(strength: float = 0.15) -> "Contour":
        return Contour([0.0, strength, 0.0, strength, 0.0, -strength, 0.0], 0.5)

    def at(self, t: float) -> float:
        """Sample the contour at ``t`` in [0, 1]."""
        if not self.points:
            return 0.0
        t = max(0.0, min(1.0, t))
        x = t * (len(self.points) - 1)
        i = int(x)
        if i >= len(self.points) - 1:
            return self.points[-1]
        frac = x - i
        return self.points[i] * (1 - frac) + self.points[i + 1] * frac


CONTOUR_BY_NAME = {"arch": Contour.arch, "descending": Contour.descending,
                   "rising": Contour.rising, "wave": Contour.wave, "flat": Contour.flat}
