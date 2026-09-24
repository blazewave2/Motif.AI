"""Melody: inventing a theme, and making it go somewhere.

A melody here grows from a motif — a small rhythm and shape with character —
through the phrase grammar composers actually use. A sentence states a
basic idea, restates it (often on a new harmony), breaks it into fragments
that press forward, and closes with a cadence; a period asks a question
ending on a half cadence and answers it with a full one. So the music
repeats, varies and develops its own material instead of wandering.

Every note is chosen by a beam search against a musical cost: chord tones
on strong beats unless the note is an appoggiatura that resolves; passing
and neighbour notes approached and left by step; leaps recovered in the
other direction; a contour that climbs to one climax per phrase; fidelity
to the motif wherever it is being restated; no parallel fifths or octaves
against the bass; and the right scale degree at every cadence.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from fractions import Fraction as F

from ..theory.pitch import Key, Pitch
from .harmony import Harmony, harmony_at, spell as spell_in_chord
from .style_model import melody_model


# ---------------------------------------------------------------------------
# style profiles for melody
# ---------------------------------------------------------------------------
@dataclass
class MelodyStyle:
    name: str
    low: int = 60                  # comfortable range (MIDI)
    high: int = 84
    climax_high: int = 88          # how high a climax may reach
    step: float = 0.0              # cost of a step (seconds / whole tones)
    third: float = 0.35
    fourth: float = 0.8
    fifth: float = 1.1
    sixth: float = 1.2
    octave: float = 1.8
    repeat: float = 0.6            # repeated note
    leap_recovery: float = 1.5     # penalty for not recovering a leap by contrary step
    appoggiatura: float = 0.4      # appetite for accented dissonance (0..1)
    chromatic: float = 0.15        # appetite for chromatic neighbours / passing notes
    triplets: float = 0.0          # chance a lyrical bar uses triplets
    anacrusis: float = 0.3         # chance a theme begins with an upbeat
    cells: str = "lyrical"         # which rhythm family
    ornament: float = 0.1          # turns, grace notes on restatements
    octaves: float = 0.0           # doubling the melody in octaves at climaxes
    learned: float = 1.0           # how much the learned model of real melodies counts


MELODY_STYLES: dict[str, MelodyStyle] = {
    "baroque": MelodyStyle("baroque", 60, 81, 84, third=0.3, fourth=0.6, fifth=0.8,
                           sixth=1.3, repeat=0.9, appoggiatura=0.15, chromatic=0.1,
                           cells="motoric", anacrusis=0.4),
    "classical": MelodyStyle("classical", 62, 84, 88, third=0.25, fourth=0.7, fifth=0.9,
                             sixth=1.1, repeat=0.5, appoggiatura=0.35, chromatic=0.15,
                             cells="galant", anacrusis=0.35, ornament=0.15),
    "romantic": MelodyStyle("romantic", 62, 86, 91, third=0.3, fourth=0.7, fifth=0.9,
                            sixth=0.8, repeat=0.7, appoggiatura=0.5, chromatic=0.3,
                            cells="lyrical", triplets=0.15, anacrusis=0.4, ornament=0.3),
    "russian": MelodyStyle("russian", 60, 84, 91, third=0.35, fourth=0.6, fifth=1.0,
                           sixth=1.1, repeat=0.35, appoggiatura=0.45, chromatic=0.25,
                           cells="grand", triplets=0.2, anacrusis=0.25, ornament=0.05,
                           octaves=0.8),
    "impressionist": MelodyStyle("impressionist", 62, 86, 91, third=0.2, fourth=0.35,
                                 fifth=0.6, sixth=0.9, repeat=0.3, appoggiatura=0.3,
                                 chromatic=0.05, cells="floating", triplets=0.25,
                                 anacrusis=0.2),
    "film": MelodyStyle("film", 62, 84, 88, third=0.25, fourth=0.5, fifth=0.8, sixth=0.9,
                        repeat=0.35, appoggiatura=0.3, chromatic=0.05, cells="lyrical",
                        anacrusis=0.3, octaves=0.3),
}


def melody_style(name: str) -> MelodyStyle:
    return MELODY_STYLES.get(name, MELODY_STYLES["romantic"])


# ---------------------------------------------------------------------------
# rhythm
# ---------------------------------------------------------------------------
#: Bar rhythms by family and metre, as lists of note values in quarters.
#: Each family has "idea" cells (distinctive, for motifs), "flow" cells (for
#: continuations) and "close" cells (for cadence bars: a long final note).
CELLS: dict[str, dict[str, dict[tuple[int, int], list[list[F]]]]] = {}


def _cells(spec: dict) -> dict:
    out = {}
    for role, by_time in spec.items():
        out[role] = {t: [[F(x) for x in c] for c in cells] for t, cells in by_time.items()}
    return out


CELLS["lyrical"] = _cells({
    "idea": {(4, 4): [["3/2", "1/2", 1, 1], [2, 1, 1], [1, 1, 2], ["3/2", "1/2", 2], [3, 1],
                      ["1/2", "1/2", 1, 2], [1, "1/2", "1/2", 2], [2, "3/2", "1/2"],
                      [1, 2, 1], ["1/2", 1, "1/2", 2], [1, "3/2", "1/2", 1]],
             (3, 4): [[2, 1], ["3/2", "1/2", 1], [1, 1, 1], ["5/2", "1/2"], [1, 2],
                      ["1/2", 1, "1/2", 1], [1, "3/2", "1/2"]],
             (6, 8): [["3/2", 1, "1/2"], [1, "1/2", "3/2"], ["3/2", "3/2"], [1, "1/2", 1, "1/2"]],
             (2, 4): [["3/2", "1/2"], [1, 1], ["1/2", "1/2", 1]],
             (12, 8): [["3/2", 1, "1/2", 3], [1, "1/2", 1, "1/2", 3], [3, "3/2", 1, "1/2"]]},
    "flow": {(4, 4): [[1, 1, 1, 1], ["1/2", "1/2", 1, 1, 1], [1, "1/2", "1/2", 1, 1],
                      ["1/2", "1/2", "1/2", "1/2", 2], ["3/2", "1/2", "1/2", "1/2", 1],
                      [1, "2/3", "2/3", "2/3", 2], ["1/2", "1/2", "1/2", "1/2", 1, 1],
                      [1, "1/4", "1/4", "1/4", "1/4", 2], ["3/2", "1/4", "1/4", "1/2", "1/2", 1],
                      ["1/2", "1/2", "1/2", "1/4", "1/4", 1, 1]],
             (3, 4): [[1, 1, 1], ["1/2", "1/2", 1, 1], [1, "1/2", "1/2", 1],
                      ["3/2", "1/4", "1/4", "1/2", "1/2"], [1, "1/4", "1/4", "1/4", "1/4", 1],
                      ["1/2", "1/2", "1/2", "1/2", 1]],
             (6, 8): [[1, "1/2", 1, "1/2"], ["1/2", "1/2", "1/2", "3/2"],
                      ["1/2", "1/4", "1/4", "1/2", 1, "1/2"], ["1/2", "1/2", "1/2", "1/2", "1/2", "1/2"],
                      ["3/4", "1/4", "1/2", 1, "1/2"], ["1/4", "1/4", "1/4", "1/4", "1/2", "3/2"]],
             (2, 4): [[1, 1], ["1/2", "1/2", 1], ["1/2", "1/4", "1/4", "1/2", "1/2"]],
             (12, 8): [[1, "1/2", 1, "1/2", 1, "1/2", "3/2"],
                       ["1/2", "1/2", "1/2", "3/2", "1/2", "1/4", "1/4", "1/2", "3/2"],
                       ["3/2", "1/2", "1/2", "1/2", 1, "1/2", "3/2"]]},
    "close": {(4, 4): [[4], [2, 2], [3, 1]], (3, 4): [[3], [2, 1]], (6, 8): [[3], ["3/2", "3/2"]],
              (2, 4): [[2]], (12, 8): [[6], [3, 3]]},
})
CELLS["grand"] = _cells({
    "idea": {(4, 4): [[2, 2], [1, 1, 2], [3, 1], ["3/2", "1/2", 2], [2, 1, 1], [1, 3],
                      ["1/2", "1/2", 1, 2], ["2/3", "2/3", "2/3", 2], [1, "1/2", "1/2", 2],
                      ["3/2", "1/2", 1, 1], [2, "1/2", "1/2", 1],
                      # the syncopations and long upbeats of the Russian line
                      [1, 2, 1], ["1/2", 1, "1/2", 2], [1, "3/2", "1/2", 1],
                      ["3/2", "1/2", "3/2", "1/2"], [2, "2/3", "2/3", "2/3"]],
             (3, 4): [[2, 1], [1, 2], ["3/2", "1/2", 1], [1, "1/2", "1/2", 1],
                      [2, "1/2", "1/2"], ["1/2", "1/2", 2], ["2/3", "2/3", "2/3", 1],
                      ["1/2", 1, "1/2", 1], [1, "3/2", "1/2"]],
             (6, 8): [["3/2", "3/2"], [1, "1/2", "3/2"], ["3/2", 1, "1/2"],
                      ["1/2", "1/2", "1/2", "3/2"]],
             (2, 4): [[1, 1], ["3/2", "1/2"], ["1/2", "1/2", 1]],
             (12, 8): [[3, 3], ["3/2", "3/2", 3], [1, "1/2", "3/2", 3],
                       ["3/2", 1, "1/2", 3]],
             (2, 2): [[2, 2], [1, 1, 2], [3, 1]]},
    "flow": {(4, 4): [[1, 1, 1, 1], [2, 1, 1], [1, 1, 2], ["1/2", "1/2", 1, 1, 1],
                      [1, "1/2", "1/2", 1, 1], ["2/3", "2/3", "2/3", 1, 2],
                      ["3/2", "1/2", "1/2", "1/2", 1]],
             (3, 4): [[1, 1, 1], [2, 1], ["1/2", "1/2", 1, 1], [1, "1/2", "1/2", 1],
                      ["2/3", "2/3", "2/3", 1], ["1/2", "1/2", "1/2", "1/2", 1]],
             (6, 8): [[1, "1/2", 1, "1/2"], ["3/2", "3/2"], ["1/2", "1/2", "1/2", "3/2"],
                      ["3/4", "1/4", "1/2", 1, "1/2"]], (2, 4): [[1, 1], ["1/2", "1/2", 1]],
             (12, 8): [["3/2", "3/2", "3/2", "3/2"], [1, "1/2", 1, "1/2", 3]],
             (2, 2): [[1, 1, 1, 1], [2, 1, 1]]},
    "close": {(4, 4): [[4], [2, 2]], (3, 4): [[3]], (6, 8): [[3]], (2, 4): [[2]],
              (12, 8): [[6]], (2, 2): [[4], [2, 2]]},
})
CELLS["galant"] = _cells({
    "idea": {(4, 4): [[1, "1/2", "1/2", 1, 1], [2, "1/2", "1/2", 1], ["1/2", "1/2", "1/2", "1/2", 2],
                      [1, 1, "1/2", "1/2", 1], ["3/2", "1/2", 1, 1]],
             (3, 4): [[2, 1], [1, "1/2", "1/2", 1], ["3/2", "1/2", 1], [1, 1, 1]],
             (2, 4): [[1, "1/2", "1/2"], ["1/2", "1/2", 1], ["3/4", "1/4", 1]],
             (6, 8): [[1, "1/2", 1, "1/2"], ["3/2", 1, "1/2"]]},
    "flow": {(4, 4): [["1/2"] * 8, [1, "1/2", "1/2", "1/2", "1/2", 1], ["1/4"] * 4 + [1, 1, 1]],
             (3, 4): [["1/2"] * 6, [1, "1/2", "1/2", 1]], (2, 4): [["1/2"] * 4, ["1/4"] * 4 + [1]],
             (6, 8): [["1/2"] * 6]},
    "close": {(4, 4): [[2, 2], [1, 1, 2], [4]], (3, 4): [[2, 1], [3]], (2, 4): [[1, 1], [2]],
              (6, 8): [[3], ["3/2", "3/2"]]},
})
CELLS["motoric"] = _cells({
    "idea": {(4, 4): [["1/4"] * 4 + ["1/2", "1/2", 1, 1], ["1/2", "1/4", "1/4"] * 2 + [1, 1],
                      ["1/4"] * 8 + [1, 1], [1, "1/4", "1/4", "1/4", "1/4", 1, 1]],
             (3, 4): [["1/4"] * 4 + [1, 1], ["1/2", "1/2", "1/4", "1/4", "1/4", "1/4", 1]],
             (2, 4): [["1/4"] * 4 + [1], ["1/2", "1/4", "1/4", 1]],
             (6, 8): [["1/2"] * 6, [1, "1/2", 1, "1/2"]], (12, 8): [["1/2"] * 12]},
    "flow": {(4, 4): [["1/4"] * 16, ["1/4"] * 8 + ["1/2"] * 4], (3, 4): [["1/4"] * 12],
             (2, 4): [["1/4"] * 8], (6, 8): [["1/2"] * 6], (12, 8): [["1/2"] * 12]},
    "close": {(4, 4): [[1, 1, 2], [2, 2], ["1/2", "1/2", 1, 2]], (3, 4): [[2, 1], [1, 1, 1]],
              (2, 4): [[1, 1], ["1/2", "1/2", 1]], (6, 8): [["3/2", "3/2"], [1, "1/2", "3/2"]],
              (12, 8): [[3, 3], ["3/2", "3/2", 3]]},
})
CELLS["floating"] = _cells({
    "idea": {(4, 4): [[3, 1], [1, 3], [2, 2], ["3/2", "1/2", 2]], (3, 4): [[2, 1], [3]],
             (6, 8): [["3/2", "3/2"], [3]], (2, 4): [[2]], (12, 8): [[3, 3], [6]]},
    "flow": {(4, 4): [[1, 1, 2], [2, 1, 1]], (3, 4): [[1, 1, 1]], (6, 8): [["3/2", 1, "1/2"]],
             (2, 4): [[1, 1]], (12, 8): [["3/2"] * 4]},
    "close": {(4, 4): [[4]], (3, 4): [[3]], (6, 8): [[3]], (2, 4): [[2]], (12, 8): [[6]]},
})


#: Set while composing something a learner can play: no note shorter than an
#: eighth and no triplets.
SIMPLE = {"on": False}


def _easy(cells: list[list[F]]) -> list[list[F]]:
    ok = [c for c in cells if min(c) >= F(1, 2) and all(v.denominator in (1, 2) for v in c)]
    return ok or cells


def cells_for(family: str, role: str, time: tuple[int, int]) -> list[list[F]]:
    out = _cells_for(family, role, time)
    return _easy(out) if SIMPLE["on"] else out


def _cells_for(family: str, role: str, time: tuple[int, int]) -> list[list[F]]:
    fam = CELLS.get(family, CELLS["lyrical"])
    by_time = fam.get(role, fam["idea"])
    if time in by_time:
        return by_time[time]
    # scale the nearest metre's cells to this bar length
    bar = F(time[0] * 4, time[1])
    for t, cells in by_time.items():
        if F(t[0] * 4, t[1]) == bar:
            return cells
    return [[bar]]


# ---------------------------------------------------------------------------
# motifs
# ---------------------------------------------------------------------------
@dataclass
class Motif:
    """The seed of a theme: the two-bar basic idea's rhythm and its contour
    in scale steps."""

    rhythm: list[F]                      # the first bar's note values
    steps: list[int]                     # scale steps from note to note through both bars
    anacrusis: list[F] = field(default_factory=list)   # upbeat values, if any
    second: list[F] = field(default_factory=list)      # the basic idea's second bar
    start_degree: int = 0                # the scale degree it starts on (0 = tonic)
    bar2: str = "T"                      # the harmony its second bar implies: T, S or D

    def __str__(self) -> str:
        return f"rhythm={[str(x) for x in self.rhythm]}+{[str(x) for x in self.second]} " \
               f"steps={self.steps}"

    @property
    def contour(self) -> list[int]:
        pos, out = 0, [0]
        for s in self.steps:
            pos += s
            out.append(pos)
        return out


#: How often each size of step appears in a style's themes (by rhythm family).
_STEP_WEIGHTS = {
    "lyrical": {1: 50, 0: 6, 2: 22, 3: 10, 4: 5, 5: 5, 7: 1},
    "grand": {1: 46, 0: 12, 2: 18, 3: 11, 4: 7, 5: 5, 7: 1},
    "galant": {1: 45, 0: 8, 2: 30, 3: 9, 4: 5, 7: 2},
    "motoric": {1: 60, 0: 5, 2: 24, 3: 7, 4: 4},
    "floating": {1: 35, 0: 10, 2: 30, 3: 15, 4: 10},
}


def invent_motif(style: MelodyStyle, time: tuple[int, int], rng: random.Random,
                 candidates: int = 24, character: str = "") -> Motif:
    """The most characterful of a batch of candidate ideas — and, when the
    request asks for a character, the one that has it."""
    best, best_score = None, -1e9
    for _ in range(candidates):
        m = _random_motif(style, time, rng)
        sc = motif_score(m, style) + character_fit(m, character)
        if sc > best_score:
            best, best_score = m, sc
    return best


def character_fit(m: Motif, character: str) -> float:
    """How well an idea suits the mood asked for: drama rises by arpeggio in
    dotted rhythm over a wide span; calm and grief move by step in a narrow
    one; play and joy skip in short notes."""
    c = (character or "").lower()
    if not c or not m.steps:
        return 0.0
    pos = m.contour
    span = max(pos) - min(pos)
    values = list(m.rhythm) + list(m.second)
    s = 0.0
    if any(w in c for w in ("dramatic", "stormy", "triumphant")):
        arps = sum(1 for a, b in zip(m.steps, m.steps[1:]) if a >= 2 and b >= 2 or
                   (a <= -2 and b <= -2))
        s += 0.8 * min(arps, 2)
        s += 0.6 if span >= 5 else 0.0
        s += 0.5 if any(v in (F(3, 2), F(3, 4)) for v in values) else 0.0
    if any(w in c for w in ("calm", "sad", "nostalgic", "mysterious")):
        s += 0.7 if max(abs(x) for x in m.steps) <= 2 else 0.0
        s -= 0.3 * max(0, span - 5)
        s += 0.4 if max(values) >= 2 else 0.0
    if any(w in c for w in ("playful", "joyful")):
        s += 0.5 * min(3, sum(1 for v in values if v <= F(1, 2)))
        s += 0.4 if any(abs(x) == 2 for x in m.steps) else 0.0
    return s


def _random_motif(style: MelodyStyle, time: tuple[int, int], rng: random.Random,
                  shapes: int = 48, lively: bool = False) -> Motif:
    """A rhythm for the idea's two bars and the best of many contours for it.
    A lively idea (a contrasting theme that presses forward) may take its
    rhythm from the flowing cells too."""
    ideas = cells_for(style.cells, "idea", time)
    if lively:
        ideas = ideas + [c for c in cells_for(style.cells, "flow", time) if len(c) >= 3]
    rhythm = list(rng.choice(ideas))
    closes = cells_for(style.cells, "close", time)
    if style.cells not in ("grand", "floating", "lyrical") or rng.random() < 0.6:
        closes = [c for c in closes if len(c) >= 2]
    second = list(rng.choice(ideas + closes))
    ana: list[F] = []
    if rng.random() < style.anacrusis:
        beat = F(4, time[1]) if not (time[1] == 8 and time[0] % 3 == 0) else F(1, 2)
        ana = [beat] if rng.random() < 0.6 else [beat / 2, beat / 2]
    n = len(rhythm) + len(second) - 1
    weights = _STEP_WEIGHTS.get(style.cells, _STEP_WEIGHTS["lyrical"])
    sizes, ws = zip(*weights.items())
    best, best_score = None, -1e9
    for _ in range(shapes):
        steps = []
        for _k in range(n):
            size = rng.choices(sizes, ws)[0]
            steps.append(size if rng.random() < 0.5 else -size)
        m = Motif(rhythm, steps, ana, second)
        fit, start, bar2 = implied_harmony(m, time)
        m.start_degree, m.bar2 = start, bar2
        sc = motif_score(m, style) + fit
        if sc > best_score:
            best, best_score = m, sc
    return best


#: Scale degrees (0 = tonic) of the chords a theme's opening can imply.
_FUNCTION_DEGREES = {"T": {0, 2, 4}, "D": {4, 6, 1, 3}, "S": {3, 5, 0, 1}}


def implied_harmony(m: Motif, time: tuple[int, int]) -> tuple[float, int, str]:
    """Where the idea should start (on the tonic, third or fifth) and what
    its second bar implies (tonic, subdominant or dominant), so that its
    long and accented notes are chord tones and only its passing notes are
    not: (fit bonus, start degree, second-bar function)."""
    beat = F(3, 2) if (time[1] == 8 and time[0] % 3 == 0) else F(4, time[1])
    notes = []                                   # (onset in bar, dur, bar index)
    t = F(0)
    for d in m.rhythm:
        notes.append((t, d, 0))
        t += d
    t = F(0)
    for d in m.second:
        notes.append((t, d, 1))
        t += d
    pos = m.contour
    best = (-1e9, 0, "T")
    for start in (0, 2, 4):
        for bar2 in ("T", "D", "S"):
            pen = 0.0
            for k, (on, d, b) in enumerate(notes):
                deg = (start + pos[k]) % 7
                chord = _FUNCTION_DEGREES["T" if b == 0 else bar2]
                if deg in chord:
                    continue
                w = float(d) * (1.5 if on % beat == 0 else 1.0)
                prev_step = pos[k] - pos[k - 1] if k else None
                next_step = pos[k + 1] - pos[k] if k + 1 < len(pos) else None
                passing = prev_step is not None and next_step is not None and \
                    abs(prev_step) == 1 and abs(next_step) == 1 and d < beat
                pen += w * (0.25 if passing else 1.0)
            # the first note on the tonic triad, the strongest start on 1 or 5
            fit = 2.0 - 1.2 * pen - (0.2 if start == 2 else 0.0)
            fit -= 0.3 if bar2 == "T" else 0.0     # a second bar that moves is livelier
            if fit > best[0]:
                best = (fit, start, bar2)
    return best


def motif_score(m: Motif, style: MelodyStyle) -> float:
    """Character: a rhythm with a long note and a short one; a clear gesture
    (a leap filled in by steps the other way, one high point, a range of a
    fifth or so); no trilling back and forth; and somewhere to go."""
    s = 0.0
    durs = list(m.rhythm) + list(m.second)
    values = set(durs)
    s += 1.0 * min(len(values), 3)
    if len(m.rhythm) > 6 and style.cells not in ("motoric", "galant"):
        s -= 1.5
    if len(m.rhythm) <= 1:
        s -= 3
    if max(m.rhythm) >= 2 * min(m.rhythm):
        s += 0.6
    steps = m.steps
    if not steps:
        return s
    pos = m.contour
    span = max(pos) - min(pos)
    if 3 <= span <= 7:
        s += 1.5
    elif span > 9:
        s -= 2.0
    elif span < 2:
        s -= 1.5
    leaps = [i for i, x in enumerate(steps) if abs(x) >= 2]
    s += 1.0 if 1 <= len(leaps) <= 3 else (-1.0 if not leaps else -0.5 * (len(leaps) - 3))
    for i in leaps:
        if abs(steps[i]) >= 3:
            nxt = steps[i + 1] if i + 1 < len(steps) else None
            s += 0.8 if (nxt is not None and nxt * steps[i] < 0 and abs(nxt) <= 2) else -1.0
    for a, b in zip(steps, steps[1:]):
        if abs(a) >= 2 and abs(b) >= 2 and a * b > 0 and style.cells != "galant":
            s -= 0.8
        if abs(a) >= 5 and abs(b) >= 3:
            s -= 1.0
    # trilling back and forth
    osc = sum(1 for a, b, c in zip(steps, steps[1:], steps[2:])
              if abs(a) == abs(b) == abs(c) == 1 and a == -b == c)
    s -= 1.5 * osc
    reps = steps.count(0)
    s -= 0.8 * max(0, reps - (1 if style.cells == "grand" else 0))
    if any(a == 0 and b == 0 for a, b in zip(steps, steps[1:])):
        s -= 1.5
    # one high point, not the first note, held rather than passed through
    top = max(pos)
    tops = [i for i, p in enumerate(pos) if p == top]
    if len(tops) == 1 and tops[0] > 0:
        s += 1.0
        if durs[tops[0]] >= max(durs) / 2:
            s += 0.5
    elif len(tops) > 2:
        s -= 1.0
    # it arrives somewhere else
    if pos[-1] != 0:
        s += 0.4
    if abs(pos[-1]) > 5:
        s -= 1.0
    if style.cells == "grand" and pos[-1] < 0:
        s += 0.3              # the Russian lament: themes that sink
    return s


# ---------------------------------------------------------------------------
# phrases
# ---------------------------------------------------------------------------
@dataclass
class MelNote:
    onset: F
    dur: F
    midi: int
    pitch: Pitch | None = None
    role: str = "CT"               # CT chord tone | PT passing | NT neighbour | APP appoggiatura
    marks: list[str] = field(default_factory=list)
    tie: bool = False
    graces: list[Pitch] = field(default_factory=list)
    slur_start: int = 0
    slur_stop: int = 0

    @property
    def end(self) -> F:
        return self.onset + self.dur


@dataclass
class PhrasePlan:
    """What one phrase's melody must do."""

    start: F
    bars: int
    bar_len: F
    time: tuple[int, int]
    key: Key
    harmony: list[Harmony]
    cadence: str = "PAC"
    #: What each bar does with the motif: idea, idea2, repeat, repeat2,
    #: sequence, fragment, flow, cadence, recall:<n> (restate bar n of the
    #: theme), rest.
    bar_roles: list[str] = field(default_factory=list)
    peak_at: float = 0.65          # where in the phrase the climax falls (0..1)
    peak: int = 79                 # its pitch
    start_near: int | None = None  # continue from the previous phrase's last note
    low: int = 60
    high: int = 84
    energy: float = 0.5
    bass: list[tuple[F, int]] = field(default_factory=list)   # (onset, midi) of the bass line
    final: bool = False            # the last phrase of the piece: it ends on the tonic
    anacrusis: list[F] = field(default_factory=list)   # upbeat values leading into bar 1
    prev_harmony: Harmony | None = None                 # the chord under the upbeat
    tail_room: F = F(0)            # leave this much of the last bar for the next upbeat
    response_shift: int = 0        # how far the harmony moved the idea's repeat (0: free)
    imitate: bool = False          # the other hand answers the idea a bar later, below


@dataclass
class Slot:
    """One note of a phrase before its pitch is chosen."""

    t: F
    d: F
    role: str
    bar: int
    src: int | None = None          # imitates the note chosen for slot ``src``…
    src_pitch: int | None = None    # …or this remembered pitch
    anchor: int | None = None       # the first slot of this imitation unit
    fixed: int | None = None        # an exact pitch to restate (a recalled bar)
    lower: int | None = None        # the slot whose note the other hand answers with here


def roles_for(kind: str, bars: int) -> list[str]:
    """The bar-by-bar grammar of a phrase.

    A sentence states its two-bar idea, repeats it at another level, then
    breaks it down — the first bar in sequence, then half-bar fragments — and
    runs freely into its cadence. A consequent restates its antecedent's
    opening and closes differently; a coda remembers the theme's opening and
    settles."""
    if kind in ("sentence", "antecedent") and bars >= 8:
        base = ["idea", "idea2", "repeat", "repeat2", "sequence", "fragment", "flow", "cadence"]
        return base if bars == 8 else base[:6] + ["sequence", "flow"] * ((bars - 7) // 2) + \
            ["flow"] * ((bars - 7) % 2) + ["cadence"]
    if kind == "antecedent":
        return ["idea", "idea2", "flow", "cadence"][:bars] if bars >= 4 else \
            (["idea"] + ["cadence"])[:bars]
    if kind == "consequent":
        if bars <= 4:
            return ["recall:0", "recall:1", "flow", "cadence"][:bars]
        body = ["recall:0", "recall:1", "recall:2", "recall:3", "sequence", "fragment"]
        return (body + ["flow"] * max(0, bars - 7))[:bars - 1] + ["cadence"]
    if kind in ("continuation", "development"):
        seq = ["sequence", "sequence", "fragment", "fragment"]
        body = (seq * ((bars + 3) // 4))[:max(0, bars - 1)]
        return body + ["cadence"]
    if kind == "closing":
        if bars <= 2:
            return ["flow", "cadence"][-bars:]
        body = ["recall:0", "recall:1", "fragment", "flow", "fragment", "flow"]
        return (body + ["flow"] * bars)[:bars - 1] + ["cadence"]
    if kind == "intro":
        return ["rest"] * bars
    if bars <= 1:
        return ["cadence"]
    return (["idea", "idea2"] + ["flow"] * bars)[:bars - 1] + ["cadence"]


class MelodyWriter:
    """Writes the melody of phrases, one after another, remembering what it
    has written so later phrases can recall and develop it."""

    def __init__(self, style: MelodyStyle, motif: Motif, rng: random.Random,
                 beam: int = 12, time: tuple[int, int] = (4, 4)):
        self.style = style
        self.motif = motif
        self.rng = rng
        self.beam = beam
        self.time = time
        self.last_cost = 0.0                         # what the last phrase cost the search
        self.model = melody_model()
        self.theme_bars: list[list[MelNote]] = []    # bar-by-bar memory of the first theme
        self.theme_key: Key | None = None            # the key it was written in
        self.upbeat: list[int] = []                  # scale steps from each upbeat note to the downbeat

    # -- rhythm ---------------------------------------------------------
    def _bar_rhythm(self, role: str, plan: PhrasePlan, room: F) -> list[F]:
        time = plan.time
        m = self.motif
        if role in ("idea", "repeat", "sequence"):
            r = list(m.rhythm)
        elif role in ("idea2", "repeat2"):
            r = list(m.second) if m.second else list(m.rhythm)
        elif role == "fragment":
            half = _first_half(m.rhythm, plan.bar_len)
            r = half + half
        elif role == "cadence":
            r = [room] if plan.final else \
                list(self.rng.choice(cells_for(self.style.cells, "close", time)))
        elif role == "rest":
            r = [room]
        else:
            cells = cells_for(self.style.cells, "flow", time)
            dense = [c for c in cells if len(c) > len(m.rhythm)]
            pool = dense if dense and self.rng.random() < 0.7 else cells
            r = list(self.rng.choice(pool))
            if self.rng.random() < self.style.triplets and time in ((4, 4), (3, 4), (2, 4)) \
                    and not SIMPLE["on"]:
                # a bar that breaks into triplets for a beat
                pos = self.rng.randrange(len(r))
                if r[pos] == 1:
                    r = r[:pos] + [F(1, 3)] * 3 + r[pos + 1:]
        if sum(r) != room:
            r = _fit_rhythm(r, room)
        return r

    # -- laying out a phrase -------------------------------------------------
    def _layout(self, plan: PhrasePlan, memory: list[list[MelNote]]) -> list[Slot]:
        roles = plan.bar_roles or roles_for("sentence", plan.bars)
        slots: list[Slot] = []
        bar_slots: dict[int, list[int]] = {}      # bar index -> its slot indices
        # an upbeat into the first bar
        if plan.anacrusis and roles and (roles[0] in ("idea", "recall:0")):
            t = plan.start - sum(plan.anacrusis)
            for v in plan.anacrusis:
                slots.append(Slot(t, v, "ana", -1))
                t += v
        first_idea: int | None = None             # bar index of this phrase's "idea"
        second_idea: int | None = None
        for b, role in enumerate(roles):
            bar_start = plan.start + plan.bar_len * b
            last_bar = b == len(roles) - 1
            room = plan.bar_len - (plan.tail_room if last_bar else 0)
            if role.startswith("recall:"):
                src = int(role.split(":")[1])
                if src < len(memory) and memory[src]:
                    src_start = _bar_floor(memory[src][0].onset, plan)
                    idxs = []
                    for n in memory[src]:
                        on = bar_start + (n.onset - src_start)
                        if on - bar_start >= room:
                            break
                        d = min(n.dur, bar_start + room - on)
                        idxs.append(len(slots))
                        slots.append(Slot(on, d, "recall", b,
                                          fixed=_move_to_key(n.midi, self.theme_key, plan.key)))
                    bar_slots[b] = idxs
                    if src == 0:
                        first_idea = b
                    elif src == 1:
                        second_idea = b
                    continue
                role = "idea" if src % 2 == 0 else "idea2"
            if role == "rest":
                continue
            rhythm = self._bar_rhythm(role, plan, room)
            idxs = []
            t = bar_start
            for d in rhythm:
                idxs.append(len(slots))
                slots.append(Slot(t, d, role, b))
                t += d
            bar_slots[b] = idxs
            if role == "idea" and first_idea is None:
                first_idea = b
            elif role == "idea2" and second_idea is None:
                second_idea = b
                if plan.imitate and first_idea is not None and first_idea in bar_slots:
                    # against the answer: the subject, a bar later, below
                    model = bar_slots[first_idea]
                    for i in idxs:
                        rel = slots[i].t - plan.bar_len
                        for j in model:
                            if slots[j].t <= rel < slots[j].t + slots[j].d:
                                slots[i].lower = j
                                break
            # -- what this bar imitates
            if role in ("repeat", "repeat2"):
                model = first_idea if role == "repeat" else second_idea
                if model is not None and model in bar_slots:
                    anchor = None
                    if role == "repeat2" and b - 1 in bar_slots and \
                            slots[bar_slots[b - 1][0]].role == "repeat":
                        anchor = slots[bar_slots[b - 1][0]].anchor
                    self._imitate(slots, idxs, bar_slots[model], anchor)
                elif memory:
                    self._imitate_memory(slots, idxs, memory[0 if role == "repeat" else
                                                            min(1, len(memory) - 1)], None)
            elif role == "fragment":
                head_src = bar_slots.get(first_idea) if first_idea is not None else None
                half = len(idxs) // 2
                for part in (idxs[:half], idxs[half:]):
                    if not part:
                        continue
                    if head_src:
                        self._imitate(slots, part, head_src[:len(part)], None)
                    elif memory and memory[0]:
                        self._imitate_memory(slots, part, memory[0][:len(part)], None)
            elif role == "sequence":
                if first_idea is not None and first_idea in bar_slots and first_idea != b:
                    self._imitate(slots, idxs, bar_slots[first_idea], None)
                elif memory and memory[0]:
                    self._imitate_memory(slots, idxs, memory[0], None)
        return slots

    @staticmethod
    def _imitate(slots: list[Slot], idxs: list[int], model: list[int], anchor: int | None
                 ) -> None:
        if not idxs:
            return
        a = anchor if anchor is not None else idxs[0]
        for k, i in enumerate(idxs):
            if k < len(model):
                slots[i].src = model[k]
                slots[i].anchor = a

    @staticmethod
    def _imitate_memory(slots: list[Slot], idxs: list[int], model: list[MelNote],
                        anchor: int | None) -> None:
        if not idxs or not model:
            return
        a = anchor if anchor is not None else idxs[0]
        for k, i in enumerate(idxs):
            if k < len(model):
                slots[i].src_pitch = model[k].midi
                slots[i].anchor = a

    # -- writing a phrase ------------------------------------------------
    def write(self, plan: PhrasePlan, memory: list[list[MelNote]] | None = None
              ) -> list[MelNote]:
        """The melody of one phrase (with its upbeat, if it has one)."""
        memory = memory if memory is not None else self.theme_bars
        slots = self._layout(plan, memory)
        if not slots:
            return []
        return self._search(plan, slots)

    # -- the search -----------------------------------------------------------
    def _search(self, plan: PhrasePlan, slots: list[Slot]) -> list[MelNote]:
        style = self.style
        n = len(slots)
        span = plan.bar_len * plan.bars
        peak_pos = plan.start + span * F(int(plan.peak_at * 1000), 1000)
        hi_lim = max(plan.high, plan.peak) + 2
        lo_lim = plan.low - 2
        # everything about a slot that doesn't depend on the pitch chosen
        info = []
        for i, sl in enumerate(slots):
            h = self._chord_at(plan, sl.t)
            nxt = self._chord_at(plan, slots[i + 1].t) if i + 1 < n else None
            scale = _scale_pcs(plan.key, h)
            opts = []
            for m in range(lo_lim, hi_lim + 1):
                pc = m % 12
                if pc in h.pcs or pc in scale or (style.chromatic > 0 and sl.d <= F(1, 2)):
                    opts.append(m)
            info.append(_SlotInfo(
                h=h, nxt=nxt, pcs=h.pcs, scale=scale, strong=_is_strong(sl.t, plan),
                target=_contour_target(sl.t, plan, peak_pos), options=opts,
                bass=_bass_at(plan.bass, sl.t) if plan.bass else None,
                bass_prev=_bass_at(plan.bass, slots[i - 1].t) if plan.bass and i else None,
                same_chord_as_src=False))
        for i, sl in enumerate(slots):
            if sl.anchor == i and sl.src is not None:
                info[i].same_chord_as_src = info[sl.src].h.roman == info[i].h.roman

        beam: list[tuple[float, list[int]]] = [(0.0, [])]
        width = max(4, self.beam)
        for i, sl in enumerate(slots):
            inf = info[i]
            new_beam: list[tuple[float, list[int]]] = []
            for cost, seq in beam:
                prev = seq[-1] if seq else plan.start_near
                prev2 = seq[-2] if len(seq) >= 2 else None
                for m in inf.options:
                    c = cost + self._note_cost(m, prev, prev2, i, sl, inf, slots, info, seq,
                                               plan, peak_pos)
                    if c >= 1e8:
                        continue
                    new_beam.append((c, seq + [m]))
            if not new_beam:
                # nothing satisfied the constraints: relax to chord tones
                for cost, seq in beam:
                    for m in inf.options:
                        if m % 12 in inf.pcs:
                            new_beam.append((cost + 5, seq + [m]))
            new_beam.sort(key=lambda x: x[0])
            beam = []
            seen = set()
            for c, seq in new_beam:
                keyt = tuple(seq[-3:])
                if keyt in seen:
                    continue
                seen.add(keyt)
                # a little noise, so each take explores differently
                beam.append((c + self.rng.random() * 0.15, seq))
                if len(beam) >= width:
                    break
        best = self._finish_cost_pick(beam, plan, slots)
        out: list[MelNote] = []
        for sl, inf, m in zip(slots, info, best):
            out.append(MelNote(sl.t, sl.d, m, spell_in_chord(m, inf.h), _role_of(m, inf.h)))
        _respell_chromatic(out, plan)
        # remember how the theme's upbeat leads in
        ana = [k for k, sl in enumerate(slots) if sl.role == "ana"]
        if ana and not self.upbeat and len(best) > len(ana):
            down = best[len(ana)]
            self.upbeat = [_scale_steps(best[k], down, plan.key) for k in ana]
        return out

    @staticmethod
    def _chord_at(plan: PhrasePlan, t: F) -> Harmony:
        if t < plan.start and plan.prev_harmony is not None:
            return plan.prev_harmony
        return harmony_at(plan.harmony, t)

    def _finish_cost_pick(self, beam, plan, slots):
        """Whole-phrase judgement among the finalists: one climax, a real
        cadence, and enough variety."""
        best, best_score = None, 1e18
        self.last_cost = 0.0
        for cost, seq in beam:
            extra = 0.0
            top = max(seq)
            if seq.count(top) > 2:
                extra += 2.0
            last = seq[-1]
            deg = (last - plan.key.tonic_pc) % 12
            if plan.cadence in ("PAC",) and deg != 0:
                extra += 6.0
            if plan.cadence in ("IAC",) and deg not in (0, 3, 4):
                extra += 4.0
            if plan.cadence == "HC" and deg not in (2, 7, 11):
                extra += 4.0
            distinct = len(set(seq))
            if distinct < min(5, len(seq)):
                extra += 2.0
            # the phrase should reach the height it was planned to
            extra += 0.8 * max(0, plan.peak - 2 - top)
            total = cost + extra
            if total < best_score:
                best, best_score = seq, total
        self.last_cost = best_score
        return best

    def _note_cost(self, m: int, prev: int | None, prev2: int | None, i: int, sl: Slot,
                   inf: "_SlotInfo", slots: list[Slot], info: list["_SlotInfo"],
                   seq: list[int], plan: PhrasePlan, peak_pos: F) -> float:
        st = self.style
        c = 0.0
        pc = m % 12
        chord = pc in inf.pcs
        in_scale = pc in inf.scale
        d = sl.d
        strong = inf.strong
        if m > plan.peak:
            c += 4.0 * (m - plan.peak)
        # -- harmony
        if not chord:
            if not in_scale:
                c += 3.0 * (1 - st.chromatic)
            if strong and d >= F(1, 2):
                # an accented dissonance must be an appoggiatura resolving by step
                c += 3.5 * (1 - st.appoggiatura)
                if d >= 2:
                    c += 4.0
            elif prev is not None and abs(m - prev) > 2:
                c += 2.5          # a dissonance is approached by step…
            beat = plan.bar_len / (plan.time[0] if plan.time[1] == 4 or plan.time[0] % 3
                                   else plan.time[0] // 3)
            if d >= beat and not strong:
                # a long dissonance off the beat is no passing note
                c += 1.2 + 0.8 * float(d / beat - 1)
        if strong and chord:
            c -= 0.4
        # the note before must resolve if it was a dissonance
        if prev is not None and seq:
            pinf = info[i - 1]
            if prev % 12 not in pinf.pcs:
                if abs(m - prev) > 2:
                    c += 3.0      # …and left by step
                elif pinf.strong and m >= prev:
                    c += 1.2 * st.appoggiatura   # appoggiaturas fall into their resolution
        # -- motion
        if prev is not None:
            iv = abs(m - prev)
            c += _interval_cost(iv, st)
            if iv == 6:
                c += 3.0
            if prev2 is not None:
                last = prev - prev2
                if abs(last) >= 5 and (m - prev) * last > 0:
                    c += st.leap_recovery          # leaps are recovered in the other direction
                if abs(last) >= 5 and abs(m - prev) > 2:
                    c += 0.6 * st.leap_recovery
                if last and (m - prev) and abs(last) >= 3 and abs(m - prev) >= 3 and \
                        (m - prev) * last > 0:
                    c += 0.8                        # two leaps in one direction
            if m == prev and d < F(1, 2):
                c += 0.8
            if prev2 is not None and m == prev == prev2:
                c += 1.5                                # a note hammered three times
            if len(seq) >= 3 and m == seq[-2] and prev == seq[-3] and m != prev:
                c += 1.2                                # trilling back and forth
        # -- what real melodies do
        model = self.model
        if model is not None and prev is not None and st.learned:
            w = st.learned
            c += w * 0.35 * model.interval_cost(prev - prev2 if prev2 is not None else None,
                                                m - prev)
            tonic = plan.key.tonic_pc
            c += w * 0.25 * model.degree_cost(plan.key.is_minor, prev - tonic, m - tonic)
            if strong:
                c += w * 0.15 * model.strong_cost(plan.key.is_minor, m - tonic)
        # -- contour
        c += 0.15 * abs(m - inf.target)
        # -- the climax belongs where it was planned
        if m >= plan.peak - 1 and abs(sl.t - peak_pos) > plan.bar_len * F(3, 2):
            c += 2.5
        # -- the motif's own shape where it is first stated
        if sl.role in ("idea", "idea2") and prev is not None and seq:
            idx_in_bar = sum(1 for j in range(i) if slots[j].bar == sl.bar)
            want = self._motif_step(sl.role, idx_in_bar)
            if sl.role == "idea2" and idx_in_bar == 0 and (i == 0 or slots[i - 1].role != "idea"):
                want = None
            if want is not None:
                got = _scale_steps(prev, m, plan.key)
                c += 1.5 * abs(got - want)
            elif idx_in_bar == 0 and self.upbeat and i > 0 and slots[i - 1].role == "ana":
                got = _scale_steps(prev, m, plan.key)
                c += 0.9 * abs(got + self.upbeat[-1])
        if sl.role == "idea" and (i == 0 or slots[i - 1].role in ("ana",)) :
            if key_degree(m, plan.key) != self.motif.start_degree:
                c += 2.0
        # -- restating and developing: the same shape, moved as a whole
        if sl.fixed is not None:
            c += 0.8 * abs(m - sl.fixed)
        elif sl.anchor is not None and (sl.src is not None or sl.src_pitch is not None):
            base = seq[sl.src] if sl.src is not None else sl.src_pitch
            if sl.anchor == i:
                shift = _scale_steps(base, m, plan.key)
                if sl.role in ("repeat", "repeat2") and plan.response_shift % 7:
                    # the harmony has moved the idea: the tune moves with it
                    c += 0.0 if (shift - plan.response_shift) % 7 == 0 and abs(shift) <= 5 \
                        else 3.0
                else:
                    c += _shift_cost(shift, sl.role, sl.t < peak_pos, inf.same_chord_as_src)
            else:
                a = slots[sl.anchor]
                a_base = seq[a.src] if a.src is not None else a.src_pitch
                if a_base is not None and sl.anchor < len(seq):
                    shift = _scale_steps(a_base, seq[sl.anchor], plan.key)
                    want = _transpose_steps(base, shift, plan.key)
                    c += 1.0 * abs(m - want)
        # -- counterpoint with the answering hand
        if sl.lower is not None and sl.lower < len(seq):
            low = seq[sl.lower] - 12
            while low > m - 3:
                low -= 12
            ic = (m - low) % 12
            if ic in (1, 2, 5, 6, 10, 11):
                c += 2.2 if (strong or d >= F(1, 2)) else 0.6
            if i and slots[i - 1].lower is not None and prev is not None:
                plow = seq[slots[i - 1].lower] - 12
                while plow > prev - 3:
                    plow -= 12
                if ic in (0, 7) and (prev - plow) % 12 == ic and m != prev:
                    c += 2.5
        # -- counterpoint with the bass: no parallel fifths or octaves on beats
        if strong and inf.bass is not None and inf.bass_prev is not None and prev is not None:
            b_now, b_prev = inf.bass, inf.bass_prev
            iv_now = (m - b_now) % 12
            iv_prev = (prev - b_prev) % 12
            if iv_now in (0, 7) and iv_now == iv_prev and m != prev and b_now != b_prev \
                    and (m - prev) * (b_now - b_prev) > 0:
                c += 3.0
        # -- cadences
        if i == len(slots) - 1:
            deg = (m - plan.key.tonic_pc) % 12
            if plan.cadence in ("PAC",) or (plan.final and plan.cadence == "plagal"):
                c += 0 if deg == 0 else 8
            elif plan.cadence == "IAC":
                c += 0 if deg in (3, 4) else (2 if deg == 0 else 8)
            elif plan.cadence == "HC":
                c += 0 if deg in (2, 7) else (1 if deg == 11 else 6)
            elif plan.cadence in ("DC", "plagal"):
                c += 0 if chord else 6
            if prev is not None:
                step = abs(m - prev)
                c += 0 if 1 <= step <= 2 else (1.8 if step == 0 else 1.0 if step <= 5 else 2.5)
        return c

    def _motif_step(self, role: str, idx: int) -> int | None:
        """The step the basic idea takes into its ``idx``-th note of the bar."""
        steps = self.motif.steps
        n1 = len(self.motif.rhythm)
        if role == "idea":
            k = idx - 1 if idx > 0 else None
        else:
            k = n1 - 1 + idx
        return steps[k] if k is not None and 0 <= k < len(steps) else None


@dataclass
class _SlotInfo:
    h: Harmony
    nxt: Harmony | None
    pcs: set
    scale: set
    strong: bool
    target: float
    options: list[int]
    bass: int | None
    bass_prev: int | None
    same_chord_as_src: bool


def _shift_cost(shift: int, role: str, before_peak: bool, same_chord: bool) -> float:
    """How natural a transposition is for a restated idea: a repeat moves to
    a new level (or keeps its level over a new chord); fragments climb in
    sequence towards the climax and fall away after it."""
    if role in ("repeat", "repeat2"):
        if shift == 0:
            return 1.8 if same_chord else 0.7
        return {1: 0.0, -1: 0.3, 2: 0.3, -2: 0.4, 3: 0.7, -3: 0.6, 4: 0.9, -4: 1.2
                }.get(shift, 3.0)
    if before_peak:
        return {1: 0.0, 2: 0.3, 0: 0.8, -1: 0.9, 3: 1.0, -2: 1.2}.get(shift, 3.0)
    return {-1: 0.0, -2: 0.3, 0: 0.8, 1: 1.0, -3: 1.0, 2: 1.4}.get(shift, 3.0)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _first_half(rhythm: list[F], bar: F) -> list[F]:
    half, acc, out = bar / 2, F(0), []
    for v in rhythm:
        if acc + v > half:
            out.append(half - acc)
            acc = half
            break
        out.append(v)
        acc += v
        if acc == half:
            break
    if acc < half:
        out.append(half - acc)
    return [v for v in out if v > 0]


def _fit_rhythm(r: list[F], bar: F) -> list[F]:
    total = sum(r)
    if total == 0:
        return [bar]
    if total > bar:
        out, acc = [], F(0)
        for v in r:
            if acc + v >= bar:
                out.append(bar - acc)
                break
            out.append(v)
            acc += v
        return [v for v in out if v > 0]
    return r[:-1] + [r[-1] + (bar - total)]


def _bar_floor(t: F, plan: PhrasePlan) -> F:
    """The start of the bar containing ``t`` (bars are equal-length from 0)."""
    return (t // plan.bar_len) * plan.bar_len


def _is_strong(t: F, plan: PhrasePlan) -> bool:
    pos = (t - plan.start) % plan.bar_len
    num, den = plan.time
    if den == 8 and num % 3 == 0:
        return pos % F(3, 2) == 0
    if num == 4 and den == 4:
        return pos in (0, 2)
    if num == 3:
        return pos == 0
    if den == 2:
        return pos % 2 == 0
    return pos == 0


def _contour_target(t: F, plan: PhrasePlan, peak_pos: F) -> float:
    """An arch: rise to the peak, fall to the cadence."""
    span = plan.bar_len * plan.bars
    x = float((t - plan.start) / span) if span else 0.0
    p = plan.peak_at
    base_lo = plan.low + (plan.high - plan.low) * 0.35
    end = plan.low + (plan.high - plan.low) * (0.25 if plan.cadence in ("PAC", "IAC") else 0.45)
    if plan.start_near is not None:
        begin = float(plan.start_near)
    else:
        begin = base_lo
    if x <= p:
        u = x / p if p else 1.0
        return begin + (plan.peak - begin) * math.sin(u * math.pi / 2)
    u = (x - p) / (1 - p) if p < 1 else 1.0
    return plan.peak + (end - plan.peak) * (1 - math.cos(u * math.pi / 2))


def _interval_cost(iv: int, st: MelodyStyle) -> float:
    if iv == 0:
        return st.repeat
    if iv <= 2:
        return st.step
    if iv <= 4:
        return st.third
    if iv == 5:
        return st.fourth
    if iv == 7:
        return st.fifth
    if iv in (8, 9):
        return st.sixth
    if iv == 12:
        return st.octave
    if iv in (10, 11):
        return st.octave + 1.0
    return 4.0 + (iv - 12) * 0.5


def _scale_pcs(key: Key, h: Harmony) -> set[int]:
    pcs = set(key.scale_pcs)
    if key.is_minor:
        # raised sixth and seventh around the dominant
        t = key.tonic_pc
        pcs |= {(t + 11) % 12}
        if h.function == "D":
            pcs |= {(t + 9) % 12}
            pcs.discard((t + 10) % 12)
    # the chord's own chromatic notes are in the scale while it sounds
    pcs |= set(h.chord.pcs)
    return pcs


def _scale_steps(a: int, b: int, key: Key) -> int:
    """Signed number of scale steps from ``a`` to ``b`` (chromatic notes count
    as the degree they inflect)."""
    return _degree_of(b, key)[0] - _degree_of(a, key)[0]


def key_degree(m: int, key: Key) -> int:
    """The scale degree of a pitch counted from the tonic (0..6)."""
    return (_degree_of(m, key)[0] - _degree_of(key.tonic_pc + 60, key)[0]) % 7


def _degree_of(m: int, key: Key) -> tuple[int, int]:
    """(scale-step index counted from C-1, chromatic offset) of a pitch."""
    scale = list(key.scale_pcs)
    octv, pc = divmod(m, 12)
    best, off = 0, 99
    for i, s in enumerate(scale):
        d = (pc - s + 6) % 12 - 6
        # between two degrees, a note is the lower one raised (the leading
        # tone of minor is the seventh degree sharpened)
        if abs(d) < abs(off) or (abs(d) == abs(off) and d > off):
            best, off = i, d
    # a degree just below C belongs to the octave below (B in C major)
    rel = pc - off
    if rel < 0:
        octv -= 1
    elif rel >= 12:
        octv += 1
    return octv * len(scale) + best, off


def _move_to_key(m: int, old: Key | None, new: Key) -> int:
    """A remembered pitch, carried into another key at the same scale degree."""
    if old is None or old == new:
        return m
    shift = (new.tonic_pc - old.tonic_pc) % 12
    if shift > 6:
        shift -= 12
    if old.is_minor == new.is_minor:
        return m + shift
    # a change of mode: keep the degree, take the new key's version of it
    rel = (m - old.tonic_pc) % 12
    old_scale = [(p - old.tonic_pc) % 12 for p in old.scale_pcs]
    new_scale = [(p - new.tonic_pc) % 12 for p in new.scale_pcs]
    old_scale.sort()
    new_scale.sort()
    if rel in old_scale:
        deg = old_scale.index(rel)
        return m + shift + (new_scale[deg] - old_scale[deg])
    return m + shift


def _transpose_steps(m: int, steps: int, key: Key) -> int:
    """Move a pitch ``steps`` degrees along the key's scale, keeping any
    chromatic inflection it had."""
    if steps == 0:
        return m
    scale = list(key.scale_pcs)
    idx, _off = _degree_of(m, key)
    idx += steps
    octv, deg = divmod(idx, len(scale))
    # the plain degree: the harmony decides whether it is inflected
    return octv * 12 + scale[deg]


def _bass_at(bass: list[tuple[F, int]], t: F) -> int | None:
    cur = None
    for onset, midi in bass:
        if onset > t:
            break
        cur = midi
    return cur


def _role_of(m: int, h: Harmony) -> str:
    return "CT" if m % 12 in h.pcs else "NCT"


def _respell_chromatic(notes: list[MelNote], plan: PhrasePlan) -> None:
    respell_line(notes, plan.harmony, plan.key)


def respell_line(notes: list[MelNote], harmony: list[Harmony], key: Key) -> None:
    """A note outside the chord and the key is spelled by where it goes: a
    chromatic lower neighbour or rising passing note takes the letter below
    its goal (B# rising to C#), a falling one the letter above (Db falling to
    C) — so every step reads as a step; and never the letter of the note
    before it, so B# never falls to Bb."""
    plan = _LinePlan(harmony, key)
    for i, n in enumerate(notes):
        pc = n.midi % 12
        h = harmony_at(plan.harmony, n.onset)
        if pc in h.pcs or pc in set(plan.key.scale_pcs):
            continue
        goal = notes[i + 1] if i + 1 < len(notes) else None
        if goal is None or goal.pitch is None or abs(goal.midi - n.midi) > 2 or \
                goal.midi == n.midi:
            leading = (plan.key.tonic_pc + 11) % 12
            if plan.key.is_minor and pc == leading:
                n.pitch = plan.key.degree_pitch(7, 4, variant="harmonic_minor")
                n.pitch = Pitch.build(n.pitch.step, n.pitch.alter,
                                      (n.midi - n.pitch.pc) // 12 - 1 + _octfix(n.pitch))
            continue
        gp = goal.pitch
        from ..theory.pitch import STEPS, STEP_INDEX, STEP_SEMITONE
        before = notes[i - 1].pitch if i > 0 else None
        options = []
        for delta in ((-1, 1) if goal.midi > n.midi else (1, -1)):
            idx = STEP_INDEX[gp.step] + delta
            octv = gp.octave + (idx // 7)
            letter = STEPS[idx % 7]
            alter = n.midi - (STEP_SEMITONE[letter] + (octv + 1) * 12)
            if abs(alter) <= 1:
                options.append(Pitch.build(letter, alter, octv))
        # a spelling that repeats the letter of the note before reads as a
        # unison, not a step: take the other if there is one
        good = [p for p in options if before is None or p.step != before.step]
        if good:
            n.pitch = good[0]
        elif options:
            n.pitch = options[0]


@dataclass
class _LinePlan:
    harmony: list[Harmony]
    key: Key


def _octfix(p: Pitch) -> int:
    if p.step == "B" and p.alter > 0:
        return -1
    if p.step == "C" and p.alter < 0:
        return 1
    return 0
