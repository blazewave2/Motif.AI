"""Harmony: the chords a phrase moves through, and how they get there.

A phrase is not a random walk from chord to chord. It opens by establishing
its key, moves away through predominant harmony, gathers on the dominant and
closes with a cadence — authentic, half, deceptive or plagal — and the
chords change faster as it nears that cadence. This module plans each
phrase in those functional terms first, then realises every function with
chords drawn from the style's own vocabulary: the cadential six-four and
augmented sixths of Mozart, the mixture chords, applied diminished sevenths
and Neapolitans of Chopin, the added-sixth minor chords, half-diminished
subdominants, chromatic descending inner lines and pedal points of
Rachmaninoff, the modal planing of Debussy.

Several candidate progressions are generated for every phrase and the one
with the best bass line, variety and cadence is kept.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace
from fractions import Fraction as F

from ..theory.harmony import CHORD_INTERVALS, CHORD_SPEC, Chord, roman_to_chord
from ..theory.pitch import Key, Pitch

# Sonorities the base theory module doesn't name.
CHORD_SPEC.setdefault("dom7b9", ((0, 0), (2, 4), (4, 7), (6, 10), (8, 13)))
CHORD_SPEC.setdefault("min_add6", ((0, 0), (2, 3), (4, 7), (5, 9)))
CHORD_SPEC.setdefault("maj7_add9", ((0, 0), (2, 4), (4, 7), (6, 11), (8, 14)))
CHORD_SPEC.setdefault("aug_maj7", ((0, 0), (2, 4), (4, 8), (6, 11)))
for _k, _v in CHORD_SPEC.items():
    CHORD_INTERVALS.setdefault(_k, tuple(s for _, s in _v))


# ---------------------------------------------------------------------------
# chords by name
# ---------------------------------------------------------------------------
#: Harmonic function of each chord, by its bare numeral: T tonic, S
#: predominant, D dominant; X is colour that behaves like its neighbours.
FUNCTION = {
    "I": "T", "i": "T", "vi": "T", "VI": "S", "iii": "T", "III": "T",
    "IV": "S", "iv": "S", "ii": "S", "N": "S", "bII": "S", "bVI": "S", "bIII": "T",
    "V": "D", "v": "D", "vii": "D", "bVII": "D", "It": "S", "Fr": "S", "Ger": "S",
    "Cad": "D",
}


def core(roman: str) -> str:
    """The bare numeral of a chord label: ``V65/V`` -> ``V``, ``bVI7`` -> ``bVI``."""
    r = roman.split("/")[0]
    for special in ("It", "Fr", "Ger", "Cad", "N"):
        if r.startswith(special):
            return special
    out = ""
    for ch in r:
        if ch in "b#":
            if not out:
                out += ch
                continue
        if ch in "ivIV":
            out += ch
        elif out and out[-1] in "ivIV":
            break
    return out or "I"


def function_of(roman: str) -> str:
    if "/" in roman:
        return "D"                      # applied chords point at what follows
    c = core(roman)
    return FUNCTION.get(c, FUNCTION.get(c.lower(), "T"))


def chord_for(roman: str, key: Key) -> Chord:
    """A spelled chord for a label in ``key``: every roman numeral the base
    parser reads, plus N6, It6/Fr6/Ger6, Cad64, V7b9 and added-tone chords
    written as ``i(add6)``, ``I(add9)``, ``i(maj7)``."""
    r = roman.strip()
    added = ""
    if "(" in r and r.endswith(")"):
        r, added = r[:-1].split("(", 1)
    if r.startswith("N"):
        base = roman_to_chord("bII" + r[1:], key)
        return replace(base, roman=roman)
    if r[:2] in ("It", "Fr") or r.startswith("Ger"):
        kind = {"It": "it6", "Fr": "fr6", "Ge": "ger6"}[r[:2]]
        # built on the lowered sixth degree in either mode (Ab in C and in c)
        root = key.degree_pitch(6, 3, variant="natural_minor")
        return Chord(root, kind, roman=roman)
    if r.startswith("Cad"):
        return replace(roman_to_chord(("i" if key.is_minor else "I") + "64", key), roman=roman)
    if r.endswith("7b9"):
        base = roman_to_chord(r[:-3] + "7", key)
        return replace(base, quality="dom7b9", roman=roman)
    base = roman_to_chord(r, key)
    if added:
        quality = {
            ("min", "add6"): "min_add6", ("min", "add9"): "min_add9",
            ("maj", "add6"): "six", ("maj", "add9"): "add9",
            ("min", "maj7"): "min_maj7", ("maj7", "add9"): "maj7_add9",
            ("maj", "maj7"): "maj7", ("min7", "add9"): "min9",
            ("dom7", "add9"): "dom9", ("dom7", "add13"): "dom13",
            ("aug", "maj7"): "aug_maj7",
        }.get((base.quality, added))
        if quality:
            base = replace(base, quality=quality)
    return replace(base, roman=roman)


# ---------------------------------------------------------------------------
# a chord in time
# ---------------------------------------------------------------------------
@dataclass
class Harmony:
    """One chord on the piece's timeline."""

    roman: str
    key: Key
    onset: F
    dur: F
    chord: Chord = None                 # type: ignore[assignment]
    function: str = "T"
    pedal: int | None = None            # a held bass pitch class under the chord
    cadence: str = ""                   # set on the final chord of a cadence

    def __post_init__(self) -> None:
        if self.chord is None:
            self.chord = chord_for(self.roman, self.key)
        self.function = function_of(self.roman)

    @property
    def end(self) -> F:
        return self.onset + self.dur

    @property
    def pcs(self) -> set[int]:
        return set(self.chord.pcs)

    @property
    def bass_pc(self) -> int:
        return self.pedal if self.pedal is not None else self.chord.bass_pc

    @property
    def root_pc(self) -> int:
        return self.chord.root.pc

    def label(self) -> str:
        return self.roman


def harmony_at(harmonies: list[Harmony], t: F) -> Harmony:
    for h in harmonies:
        if h.onset <= t < h.end:
            return h
    return harmonies[-1] if t >= harmonies[-1].end else harmonies[0]


# ---------------------------------------------------------------------------
# style vocabularies
# ---------------------------------------------------------------------------
@dataclass
class HarmonyStyle:
    """How a style fills each harmonic function, and how richly."""

    name: str
    # Patterns are lists of labels; ``_`` repeats the previous chord's function
    # slot so a pattern can stretch to however many chords the phrase has room for.
    tonic: dict[str, list[tuple[float, list[str]]]]
    predominant: dict[str, list[tuple[float, list[str]]]]
    dominant: dict[str, list[tuple[float, list[str]]]]
    cadence: dict[str, dict[str, list[tuple[float, list[str]]]]]
    colour: float = 0.2              # chance to recolour a chord chromatically
    sevenths: float = 0.2            # chance a predominant or tonic takes a seventh
    pedal: float = 0.0               # chance a tonic phrase opening sits on a pedal
    sequence: float = 0.15           # chance a continuation is sequential
    #: Chromatic recolourings, by mode: a plain chord and what it may become.
    swaps: dict[str, dict[str, str]] = field(default_factory=dict)
    rhythm: tuple[float, float, float] = (1.0, 1.0, 2.0)   # chords per bar: open, middle, cadence
    #: How a sentence answers its opening idea in bars 3-4: a dominant
    #: version, a sequence a step higher, or the same tune reharmonised.
    response: dict[str, list[tuple[float, list[str]]]] = field(default_factory=dict)


def _p(*items):
    return list(items)


_CLASSICAL = HarmonyStyle(
    name="classical",
    tonic={
        "major": _p((5, ["I"]), (3, ["I", "V65", "I"]), (2, ["I", "IV64", "I"]),
                    (2, ["I", "V43", "I6"]), (1, ["I", "viio6", "I6"]), (1, ["I", "I6"])),
        "minor": _p((5, ["i"]), (3, ["i", "V65", "i"]), (2, ["i", "iv64", "i"]),
                    (2, ["i", "V43", "i6"]), (1, ["i", "viio6", "i6"])),
    },
    predominant={
        "major": _p((4, ["IV"]), (4, ["ii6"]), (2, ["ii65"]), (2, ["vi", "ii6"]),
                    (2, ["IV", "V65/V"]), (1, ["vi", "IV"]), (1, ["V7/IV", "IV"]),
                    (1, ["viio7/V"])),
        "minor": _p((4, ["iv"]), (3, ["iio6"]), (2, ["iv6"]), (2, ["VI", "iio6"]),
                    (1, ["N6"]), (1, ["It6"]), (1, ["Ger6"]), (1, ["iv", "viio7/V"])),
    },
    dominant={
        "major": _p((4, ["V"]), (4, ["V7"]), (3, ["Cad64", "V7"]), (1, ["viio7"])),
        "minor": _p((4, ["V"]), (4, ["V7"]), (3, ["Cad64", "V7"]), (1, ["viio7"])),
    },
    cadence={
        "PAC": {"major": _p((4, ["Cad64", "V7", "I"]), (4, ["V7", "I"]), (2, ["V", "I"])),
                "minor": _p((4, ["Cad64", "V7", "i"]), (4, ["V7", "i"]), (2, ["V", "i"]))},
        "IAC": {"major": _p((3, ["V65", "I"]), (2, ["V7", "I6"]), (2, ["viio6", "I"])),
                "minor": _p((3, ["V65", "i"]), (2, ["V7", "i6"]))},
        "HC": {"major": _p((4, ["V"]), (2, ["Cad64", "V"]), (2, ["V65/V", "V"])),
               "minor": _p((4, ["V"]), (2, ["Cad64", "V"]), (2, ["iv6", "V"]),
                           (2, ["Ger6", "V"]))},
        "DC": {"major": _p((4, ["V7", "vi"]), (1, ["V7", "IV6"])),
               "minor": _p((4, ["V7", "VI"]))},
        "plagal": {"major": _p((3, ["IV", "I"]), (1, ["ii65", "I"])),
                   "minor": _p((3, ["iv", "i"]), (1, ["iv6", "i"]))},
    },
    colour=0.08, sevenths=0.15, pedal=0.05, sequence=0.2,
    rhythm=(1.0, 1.0, 2.0),
    swaps={"major": {"IV": "ii6"}, "minor": {"iv": "iio6"}},
    response={"major": _p((4, ["V65", "I"]), (3, ["V7"]), (2, ["V", "V7"]), (1, ["ii6", "V7"])),
              "minor": _p((4, ["V65", "i"]), (3, ["V7"]), (2, ["iv6", "V7"]))},
)

_BAROQUE = replace(
    _CLASSICAL, name="baroque",
    tonic={
        "major": _p((3, ["I"]), (3, ["I", "V6", "I"]), (2, ["I", "IV6", "V6"]),
                    (2, ["I", "viio6", "I6"])),
        "minor": _p((3, ["i"]), (3, ["i", "V6", "i"]), (2, ["i", "iv6", "V6"]),
                    (2, ["i", "viio6", "i6"])),
    },
    predominant={
        "major": _p((3, ["ii6"]), (3, ["IV"]), (2, ["ii65"]), (2, ["vi", "ii"]),
                    (2, ["V7/V"]), (1, ["iii", "vi", "ii"])),
        "minor": _p((3, ["iio6"]), (3, ["iv"]), (2, ["iv6"]), (2, ["VI", "iio6"]),
                    (1, ["III", "VI", "iio6"])),
    },
    cadence={
        **_CLASSICAL.cadence,
        "HC": {"major": _p((4, ["V"]), (2, ["V65/V", "V"])),
               "minor": _p((4, ["iv6", "V"]), (3, ["V"]))},
        "PAC": {"major": _p((4, ["V7", "I"]), (3, ["ii65", "V7", "I"]), (2, ["V", "I"])),
                "minor": _p((4, ["V7", "i"]), (3, ["ii%65", "V7", "i"]), (2, ["V", "i"]))},
    },
    colour=0.05, sevenths=0.35, pedal=0.1, sequence=0.45, rhythm=(2.0, 2.0, 2.0),
    swaps={"major": {"IV": "ii6"}, "minor": {"iv": "iv6"}},
    response={"major": _p((3, ["V7", "I"]), (2, ["V", "V7"]), (2, ["IV", "V7"]),
                          (1, ["ii", "V"])),
              "minor": _p((3, ["V7", "i"]), (2, ["V", "V7"]), (2, ["iv", "V7"]))},
)

_ROMANTIC = HarmonyStyle(
    name="romantic",
    tonic={
        "major": _p((4, ["I"]), (3, ["I", "V65", "I"]), (2, ["I", "IV64", "I"]),
                    (2, ["I", "vi"]), (2, ["I", "iii", "vi"]), (1, ["I", "viio7/ii", "ii"]),
                    (1, ["I", "bVI", "I"]), (1, ["I", "iv64", "I"])),
        "minor": _p((4, ["i"]), (3, ["i", "V65", "i"]), (2, ["i", "iv64", "i"]),
                    (2, ["i", "VI"]), (1, ["i", "III", "VI"]), (1, ["i", "viio7", "i"]),
                    (1, ["i", "bVII", "III"])),
    },
    predominant={
        "major": _p((3, ["IV"]), (3, ["ii6"]), (2, ["ii65"]), (2, ["iv6"]),
                    (2, ["vi", "ii65"]), (2, ["V7/IV", "IV"]), (1, ["bVI"]),
                    (1, ["ii%65"]), (1, ["V65/V"]), (1, ["viio7/V"]),
                    (1, ["IV", "iv"]), (1, ["V7/vi", "vi"])),
        "minor": _p((3, ["iv"]), (3, ["ii%65"]), (2, ["iv6"]), (2, ["VI"]),
                    (2, ["N6"]), (1, ["It6"]), (1, ["Ger6"]), (1, ["V7/iv", "iv"]),
                    (1, ["VI", "N6"]), (1, ["viio7/V"])),
    },
    dominant={
        "major": _p((4, ["V7"]), (3, ["Cad64", "V7"]), (2, ["V9"]), (1, ["viio7"])),
        "minor": _p((4, ["V7"]), (3, ["Cad64", "V7"]), (2, ["V7b9"]), (1, ["viio7"])),
    },
    cadence={
        "PAC": {"major": _p((4, ["Cad64", "V7", "I"]), (4, ["V7", "I"]), (2, ["V9", "I"]),
                            (1, ["iv6", "V7", "I"])),
                "minor": _p((4, ["Cad64", "V7", "i"]), (4, ["V7", "i"]),
                            (2, ["V7b9", "i"]), (1, ["Ger6", "V7", "i"]))},
        "IAC": {"major": _p((3, ["V65", "I"]), (2, ["V7", "I6"])),
                "minor": _p((3, ["V65", "i"]), (2, ["V7", "i6"]))},
        "HC": {"major": _p((4, ["V"]), (2, ["Cad64", "V"]), (2, ["V65/V", "V"]),
                           (1, ["Ger6", "V"])),
               "minor": _p((4, ["V"]), (2, ["Ger6", "V"]), (2, ["iv6", "V"]),
                           (1, ["It6", "V"]))},
        "DC": {"major": _p((3, ["V7", "vi"]), (2, ["V7", "bVI"])),
               "minor": _p((4, ["V7", "VI"]))},
        "plagal": {"major": _p((3, ["iv", "I"]), (2, ["IV", "I"]), (1, ["ii%65", "I"])),
                   "minor": _p((3, ["iv", "i"]), (1, ["iv6", "i"]))},
    },
    colour=0.25, sevenths=0.3, pedal=0.15, sequence=0.25, rhythm=(1.0, 1.0, 2.0),
    swaps={"major": {"IV": "iv", "ii": "ii%7", "vi": "bVI"},
           "minor": {"iv": "iv(add6)", "VI": "N6"}},
    response={"major": _p((3, ["V7"]), (2, ["V65", "I"]), (2, ["ii7", "V7"]), (2, ["vi", "iii"]),
                          (1, ["IV", "iv"]), (1, ["V7/vi", "vi"])),
              "minor": _p((3, ["V7"]), (2, ["V65", "i"]), (2, ["VI", "iv"]), (2, ["ii%7", "V7"]),
                          (1, ["III", "VI"]), (1, ["V7/iv", "iv"]))},
)

_RUSSIAN = HarmonyStyle(
    name="russian",
    tonic={
        "major": _p((3, ["I"]), (3, ["I", "I(maj7)", "I6"]), (2, ["I", "iv64", "I"]),
                    (2, ["I", "vi"]), (2, ["I(add6)"]), (1, ["I", "bVI", "I"]),
                    (1, ["I", "III", "vi"])),
        # the descending "line cliché" over the tonic: i, i(maj7), i7, i(add6)
        "minor": _p((3, ["i"]), (4, ["i", "i(maj7)", "i7", "i(add6)"]),
                    (3, ["i", "iv64", "i"]), (2, ["i(add9)"]), (2, ["i", "VI", "i"]),
                    (2, ["i", "ii%65", "i"]), (1, ["i", "bVII", "VI"]),
                    (1, ["i", "III", "VI"])),
    },
    predominant={
        "major": _p((3, ["ii65"]), (3, ["iv6"]), (2, ["IV(maj7)"]), (2, ["ii%65"]),
                    (2, ["vi", "ii65"]), (1, ["bVI(maj7)"]), (1, ["V7/vi", "vi"])),
        "minor": _p((4, ["ii%65"]), (3, ["iv(add6)"]), (3, ["VI(maj7)"]), (2, ["iv"]),
                    (2, ["N6"]), (2, ["VI", "ii%65"]), (1, ["Ger6"]),
                    (1, ["iv", "iv(add6)"]), (1, ["V7/iv", "iv"])),
    },
    dominant={
        "major": _p((3, ["V9"]), (3, ["V7"]), (2, ["Cad64", "V7"]), (1, ["V13"]),
                    (1, ["V+"])),
        "minor": _p((3, ["V7b9"]), (3, ["V7"]), (2, ["Cad64", "V7"]), (1, ["V9"]),
                    (1, ["viio7"])),
    },
    cadence={
        "PAC": {"major": _p((3, ["V9", "I"]), (3, ["Cad64", "V7", "I"]),
                            (2, ["ii%65", "V7", "I"]), (2, ["iv6", "V7", "I"])),
                "minor": _p((4, ["ii%65", "V7", "i"]), (3, ["V7b9", "i"]),
                            (3, ["Cad64", "V7", "i"]), (2, ["iv(add6)", "V7", "i"]))},
        "IAC": {"major": _p((3, ["V65", "I"])), "minor": _p((3, ["V65", "i"]))},
        "HC": {"major": _p((3, ["V"]), (2, ["ii%65", "V"]), (2, ["bVI", "V"])),
               "minor": _p((4, ["V"]), (3, ["VI", "V"]), (2, ["Ger6", "V"]),
                           (2, ["ii%65", "V"]))},
        "DC": {"major": _p((3, ["V7", "vi"]), (3, ["V7", "bVI"])),
               "minor": _p((4, ["V7", "VI"]))},
        # the Russian plagal close: a minor subdominant with its sixth
        "plagal": {"major": _p((4, ["iv(add6)", "I"]), (2, ["iv", "I"])),
                   "minor": _p((4, ["iv(add6)", "i"]), (2, ["iv", "i"]),
                               (1, ["ii%65", "i"]))},
    },
    colour=0.3, sevenths=0.45, pedal=0.3, sequence=0.3, rhythm=(1.0, 1.0, 2.0),
    swaps={"major": {"IV": "iv(add6)", "ii": "ii%7", "vi": "bVI(maj7)", "I": "I(add6)"},
           "minor": {"iv": "iv(add6)", "VI": "VI(maj7)", "i": "i(add9)"}},
    response={"major": _p((3, ["V9"]), (2, ["ii7", "V7"]), (2, ["vi", "IV(maj7)"]),
                          (2, ["iv6", "I"]), (1, ["bVI(maj7)"])),
              "minor": _p((3, ["ii%7", "V7"]), (3, ["VI(maj7)"]), (2, ["iv(add6)", "i"]),
                          (2, ["V7", "i"]), (2, ["bVII", "III"]), (1, ["V7/iv", "iv"]))},
)

_IMPRESSIONIST = HarmonyStyle(
    name="impressionist",
    tonic={
        "major": _p((3, ["I(maj7)"]), (3, ["I(add9)", "IV(maj7)"]), (2, ["I(add6)", "bVII"]),
                    (2, ["I(maj7)", "ii7", "iii7"]), (1, ["I", "II"])),
        "minor": _p((3, ["i7"]), (3, ["i(add9)", "IV"]), (2, ["i7", "bVII"]),
                    (2, ["i", "VI(maj7)"])),
    },
    predominant={
        "major": _p((3, ["IV(maj7)"]), (3, ["ii7"]), (2, ["vi7"]), (2, ["bVII"]),
                    (1, ["II"])),
        "minor": _p((3, ["iv7"]), (3, ["VI(maj7)"]), (2, ["IV"]), (2, ["bVII"])),
    },
    dominant={
        "major": _p((3, ["V9"]), (2, ["V+"]), (2, ["bVII"]), (1, ["V13"])),
        "minor": _p((3, ["v7"]), (2, ["bVII"]), (2, ["V9"])),
    },
    cadence={
        "PAC": {"major": _p((3, ["V9", "I(add9)"]), (3, ["bVII", "I(maj7)"]),
                            (2, ["IV(maj7)", "I(add6)"])),
                "minor": _p((3, ["bVII", "i"]), (3, ["iv7", "i(add9)"]), (2, ["v7", "i"]))},
        "IAC": {"major": _p((2, ["V9", "I6"])), "minor": _p((2, ["v7", "i6"]))},
        "HC": {"major": _p((3, ["V9"]), (2, ["bVII"])), "minor": _p((3, ["v7"]),
                                                               (2, ["bVII"]))},
        "DC": {"major": _p((3, ["V9", "vi7"])), "minor": _p((3, ["v7", "VI(maj7)"]))},
        "plagal": {"major": _p((3, ["IV(maj7)", "I(add9)"])),
                   "minor": _p((3, ["iv7", "i(add9)"]))},
    },
    colour=0.2, sevenths=0.8, pedal=0.35, sequence=0.1, rhythm=(0.5, 1.0, 1.0),
    swaps={"major": {"IV": "IV(maj7)", "I": "I(add9)", "V": "bVII"},
           "minor": {"iv": "iv7", "i": "i(add9)", "v": "bVII"}},
    response={"major": _p((3, ["IV(maj7)"]), (2, ["bVII"]), (2, ["ii7", "iii7"]), (2, ["vi7"])),
              "minor": _p((3, ["iv7"]), (2, ["bVII"]), (2, ["VI(maj7)"]))},
)

_FILM = replace(
    _ROMANTIC, name="film",
    tonic={
        "major": _p((3, ["I", "V6", "vi", "IV"]), (3, ["I", "iii", "vi"]),
                    (2, ["I(add9)"]), (2, ["I", "bVII", "IV"])),
        "minor": _p((4, ["i", "VI", "III", "bVII"]), (3, ["i", "i(add9)"]),
                    (2, ["i", "VI"]), (2, ["i", "iv", "VI"])),
    },
    colour=0.1, sevenths=0.3, pedal=0.25, sequence=0.15, rhythm=(0.5, 1.0, 1.0),
    response={"major": _p((3, ["IV", "I"]), (3, ["vi", "IV"]), (2, ["V", "vi"])),
              "minor": _p((3, ["VI", "III"]), (3, ["iv", "VI"]), (2, ["bVII", "i"]))},
)

HARMONY_STYLES = {s.name: s for s in (_BAROQUE, _CLASSICAL, _ROMANTIC, _RUSSIAN,
                                      _IMPRESSIONIST, _FILM)}


def harmony_style(name: str) -> HarmonyStyle:
    return HARMONY_STYLES.get(name, _ROMANTIC)


# ---------------------------------------------------------------------------
# planning one phrase
# ---------------------------------------------------------------------------
@dataclass
class PhraseHarmonySpec:
    """What a phrase's harmony must do."""

    key: Key
    start: F                     # timeline position of the phrase
    bars: int
    bar_len: F                   # quarters per bar
    cadence: str = "PAC"         # PAC | IAC | HC | DC | plagal | none
    kind: str = "open"           # open (sentence/period opening) | continuation | sequence
                                 # | pedal | transition | closing
    rhythm: tuple[float, float, float] | None = None   # chords per bar: open, middle, cadence
    begin_on_tonic: bool = True
    to_key: Key | None = None    # a transition ending in another key
    pedal: bool = False
    beat: F = F(1)               # the metre's beat, so chords change on beats
    #: A sentence: the idea on the tonic (bars 1-2), answered in bars 3-4.
    presentation: bool = False
    #: Chords borrowed from an earlier phrase for the opening bars (a
    #: consequent restates its antecedent's opening over the same harmony).
    prefix: list["Harmony"] = field(default_factory=list)
    prefix_bars: int = 0
    #: What the theme's second bar implies (T, S or D), so its opening two
    #: bars are harmonised the way the tune suggests.
    idea_bar2: str = ""
    #: Hold this pitch class in the bass under the whole phrase (a dominant
    #: pedal building towards a return), rather than the tonic at its start.
    pedal_pc: int | None = None
    #: A sentence whose idea is repeated a number of scale steps away has its
    #: opening chords moved the same distance (a true sequence); 0 means the
    #: repeat is reharmonised from the style's own answers instead.
    response_shift: int = 0


def plan_phrase(spec: PhraseHarmonySpec, style: HarmonyStyle, rng: random.Random,
                tries: int = 12) -> list[Harmony]:
    """The best of several candidate progressions for one phrase."""
    best, best_score = None, -1e9
    for _ in range(max(1, tries)):
        cand = _candidate(spec, style, rng)
        if spec.prefix:
            cand = _merge_repeats([replace(h) for h in spec.prefix] + cand)
        s = score_progression(cand, spec)
        if s > best_score:
            best, best_score = cand, s
    return best


def _slots(spec: PhraseHarmonySpec, style: HarmonyStyle, rng: random.Random
           ) -> list[tuple[str, F, F]]:
    """Divide the phrase into (stage, onset, duration) chord slots.

    Stages: T (opening), R (a sentence's answer to its idea), S (moving
    away) and A (the cadence's arrival, which takes the whole final bar, so
    a cadence lands on a downbeat and is held). Harmonic rhythm quickens in
    the bar before the arrival. Bars borrowed from an earlier phrase are
    skipped."""
    rhythm = spec.rhythm or style.rhythm
    bar = spec.bar_len
    total = spec.bars - spec.prefix_bars
    arrive = 1 if (spec.cadence != "none" and total >= 2) else 0
    body = total - arrive
    out: list[tuple[str, F, F]] = []
    t = spec.start + bar * spec.prefix_bars

    def fill(stage: str, bars: int, per_bar: float) -> None:
        nonlocal t
        if bars <= 0:
            return
        n = max(1, round(bars * per_bar))
        length = bar * bars
        unit = _quantise(length / n, spec.beat)
        pos = F(0)
        for i in range(n):
            d = unit if i < n - 1 else length - pos
            if d <= 0:
                break
            out.append((stage, t + pos, d))
            pos += d
        t += length

    if spec.prefix_bars:
        # a consequent carries on from its borrowed opening
        fill("S", max(0, body - 1), rhythm[1])
        fill("S", 1 if body >= 1 else 0, rhythm[2])
    elif spec.presentation and body >= 5:
        fill("T", 2, rhythm[0])
        fill("R", 2, rhythm[0])
        rest = body - 4
        fill("S", max(0, rest - 1), rhythm[1])
        fill("S", 1 if rest >= 1 else 0, rhythm[2])
    else:
        open_bars = max(1, body // 2) if body > 1 else body
        if spec.kind in ("continuation", "sequence"):
            open_bars = max(1, body // 3)
        mid_bars = body - open_bars
        fill("T", open_bars - (1 if mid_bars == 0 and open_bars > 1 else 0), rhythm[0])
        if mid_bars == 0 and open_bars > 1:
            fill("S", 1, rhythm[2])
        else:
            fill("S", max(0, mid_bars - 1), rhythm[1])
            fill("S", 1 if mid_bars >= 1 else 0, rhythm[2])
    if arrive:
        out.append(("A", t, bar))
    return out


def _quantise(d: F, beat: F) -> F:
    """Chords change on beats (or on half-beats only when a beat is long)."""
    unit = beat if beat <= 1 else beat / 2 if beat == 2 else beat
    q = max(unit, F(round(d / unit)) * unit)
    return q


def _choose(options: list[tuple[float, list[str]]], rng: random.Random) -> list[str]:
    total = sum(w for w, _ in options)
    x = rng.random() * total
    for w, pat in options:
        x -= w
        if x <= 0:
            return list(pat)
    return list(options[-1][1])


def _mode(key: Key) -> str:
    return "minor" if key.is_minor else "major"


def _fit(pattern: list[str], n: int) -> list[str]:
    """Squeeze a pattern of chords onto ``n`` slots (keeping its first and
    last chords), or pad it by letting its stable chords last longer."""
    if n <= 0:
        return []
    if len(pattern) >= n:
        if n == 1:
            return [pattern[-1]]
        return ([pattern[0]] + pattern[-(n - 1):])[:n]
    out = list(pattern)
    stable = [i for i, r in enumerate(out) if function_of(r) in ("T", "S")
              and core(r) in ("I", "i", "IV", "iv", "VI", "vi", "bVI")] or [0]
    k = 0
    while len(out) < n:
        i = stable[k % len(stable)] + k // len(stable)
        i = min(i, len(out) - 1)
        out.insert(i + 1, out[i])
        k += 1
    return out[:n]


def _extend(pattern: list[str], n: int, pool: list[tuple[float, list[str]]],
            rng: random.Random, tail: bool = True) -> list[str]:
    """Fill ``n`` slots from a pattern, adding more of the same function
    rather than holding an unstable chord for bars on end."""
    out = list(pattern)
    guard = 0
    while len(out) < n and guard < 8:
        guard += 1
        more = _choose(pool, rng)
        room = n - len(out)
        if len(more) > room:
            break
        # tonic prolongations go before, predominants lead into what follows
        out = (out + more) if not tail else (more + out)
        # collapse an immediate repeat produced at the seam
        out = [r for j, r in enumerate(out) if j == 0 or r != out[j - 1] or
               function_of(r) == "T"]
    return _fit(out, n)


def _candidate(spec: PhraseHarmonySpec, style: HarmonyStyle, rng: random.Random
               ) -> list[Harmony]:
    key = spec.key
    mode = _mode(key)
    slots = _slots(spec, style, rng)
    n_t = sum(1 for x in slots if x[0] == "T")
    n_r = sum(1 for x in slots if x[0] == "R")
    n_s = sum(1 for x in slots if x[0] == "S")
    has_arrival = bool(slots) and slots[-1][0] == "A"

    # -- opening: establish the tonic (or continue from what came before)
    if spec.kind == "sequence":
        body = _sequence(n_t + n_r + n_s, mode, rng)
        n_r = n_s = 0
    else:
        tonic = _choose(style.tonic[mode], rng)
        if not spec.begin_on_tonic or spec.prefix_bars:
            tonic = _choose(style.predominant[mode] + style.tonic[mode][1:], rng)
        body = _fit(tonic, n_t) if len(tonic) >= n_t or n_t <= 2 else \
            _extend(tonic, n_t, style.tonic[mode], rng, tail=False)
        if spec.idea_bar2 and n_t == 2 and not spec.prefix_bars:
            # the theme's own harmony: tonic, then what its second bar implies
            if spec.idea_bar2 == "D":
                second = _choose(style.dominant[mode], rng)[-1]
            elif spec.idea_bar2 == "S":
                second = _choose(style.predominant[mode], rng)[0]
            else:
                second = body[-1] if len(body) > 1 else body[0]
            body = [body[0] if core(body[0]) in ("I", "i") else ("i" if key.is_minor else "I"),
                    second]
        # -- a sentence answers its idea: a dominant version, a sequence or
        # a reharmonisation
        if n_r:
            if spec.response_shift % 7:
                body += _fit([transpose_roman(r, spec.response_shift, key) for r in body[:n_t]],
                             n_r)
            else:
                pool = style.response.get(mode) or style.dominant[mode]
                body += _fit(_choose(pool, rng), n_r)
        # -- moving away through predominant harmony
        if n_s:
            if spec.kind == "continuation" and rng.random() < style.sequence:
                mid = _sequence(n_s, mode, rng)
            else:
                mid = _choose(style.predominant[mode], rng)
                mid = _extend(mid, n_s, style.predominant[mode], rng, tail=True)
            body += mid

    # -- the cadence: its approach chords replace the end of the body, and
    # its arrival takes the final bar
    if has_arrival:
        cad = _choose(style.cadence.get(spec.cadence, style.cadence["PAC"])[mode], rng)
        approach, arrival = cad[:-1], cad[-1]
        room = max(0, len(body) - 1)
        if approach and room:
            approach = approach[-room:]
            body = body[:len(body) - len(approach)] + approach
        labels = body + [arrival]
    else:
        labels = body

    labels = _resolve_applied(labels, key)
    fixed_from = len(labels) - (len(approach) + 1 if has_arrival else 0) \
        if has_arrival else len(labels)
    labels = [r if i == 0 and style.name != "impressionist"
              else _colour(r, i, fixed_from, style, mode, rng)
              for i, r in enumerate(labels)]

    out = [Harmony(roman, key, onset, dur)
           for (stage, onset, dur), roman in zip(slots, labels)]
    if spec.pedal or spec.pedal_pc is not None or \
            (spec.kind == "open" and rng.random() < style.pedal):
        _pedal(out, key, spec)
    if spec.cadence != "none" and out and has_arrival:
        out[-1].cadence = spec.cadence
    return _merge_repeats(out)


_DEGREE_CHORDS = {
    "major": ["I", "ii", "iii", "IV", "V", "vi", "viio"],
    "minor": ["i", "ii%", "III", "iv", "V", "VI", "bVII"],
}
_DEGREE_OF = {"i": 0, "ii": 1, "iii": 2, "iv": 3, "v": 4, "vi": 5, "vii": 6,
              "bii": 1, "biii": 2, "bvi": 5, "bvii": 6}


def transpose_roman(roman: str, steps: int, key: Key) -> str:
    """The chord ``steps`` degrees along the scale from ``roman``, as the key
    itself would have it (in minor, V keeps its leading tone and the chord on
    the seventh degree is the subtonic)."""
    if steps % 7 == 0 or "/" in roman or roman[:2] in ("It", "Fr", "Ge", "Ca") or \
            roman.startswith("N"):
        return roman
    c = core(roman)
    deg = _DEGREE_OF.get(c.lower())
    if deg is None:
        return roman
    mode = "minor" if key.is_minor else "major"
    new = _DEGREE_CHORDS[mode][(deg + steps) % 7]
    seventh = any(f in roman for f in ("7", "65", "43", "42", "9"))
    if new == "ii%":
        return "ii%7" if seventh or mode == "minor" else "iio"
    if seventh:
        if new == "viio":
            return "vii%7"
        if new in ("I", "IV", "III", "VI"):
            return new + "(maj7)"
        return new + "7"
    return new


def _applied_target(roman: str) -> str | None:
    return roman.split("/", 1)[1] if "/" in roman else None


def _goes_to(label: str, target: str) -> bool:
    """Whether ``label`` is the chord an applied chord aimed at ``target``
    resolves to (the target itself, in any inversion or colour)."""
    if core(label).lower() == core(target).lower():
        return True
    # an applied dominant of V may resolve through the cadential six-four
    return core(target) == "V" and label.startswith("Cad")


def _resolve_applied(labels: list[str], key: Key) -> list[str]:
    """Every applied chord must go to its target; one that doesn't becomes
    its target's own predominant preparation instead. An augmented sixth
    must open onto the dominant (or the cadential six-four)."""
    out = list(labels)
    for i, r in enumerate(out):
        if r[:2] in ("It", "Fr", "Ge"):
            nxt = out[i + 1] if i + 1 < len(out) else None
            if nxt is None or not (core(nxt) == "V" or nxt.startswith("Cad")):
                out[i] = "iv6" if key.is_minor else "ii6"
            continue
        tgt = _applied_target(r)
        if tgt is None:
            continue
        nxt = out[i + 1] if i + 1 < len(out) else None
        if nxt is not None and _goes_to(nxt, tgt):
            continue
        if nxt is not None and function_of(nxt) == "D":
            out[i] = "ii6" if not key.is_minor else "iio6"
        elif nxt is not None:
            out[i] = tgt
        else:
            out[i] = tgt
    return out


def _colour(roman: str, i: int, fixed_from: int, style: HarmonyStyle, mode: str,
            rng: random.Random) -> str:
    if i >= fixed_from:
        return roman                   # cadences are left exactly as written
    if "(" in roman or "/" in roman or roman[:2] in ("It", "Fr", "Ge", "Ca", "N6"):
        return roman
    c = core(roman)
    fig = roman[len(roman.split("/")[0].rstrip("0123456789")):]
    if not fig and rng.random() < style.sevenths and c in ("ii", "IV", "iv", "vi", "VI",
                                                            "I", "i", "iii", "III"):
        if c in ("I", "IV") and style.name in ("russian", "impressionist", "romantic"):
            return f"{roman}(maj7)"
        if c in ("I", "IV", "i"):
            return roman               # a classical tonic or subdominant stays a triad
        if c in ("i",) and style.name == "russian":
            return "i(add6)" if rng.random() < 0.5 else "i(add9)"
        if c in ("ii", "iv", "vi", "iii"):
            return roman + "7"
        if c == "VI" and style.name in ("russian", "romantic"):
            return "VI(maj7)"
    if rng.random() < style.colour * 0.5:
        swaps = style.swaps.get(mode, {})
        if c in swaps and not fig:
            return swaps[c]
    return roman


def _sequence(n: int, mode: str, rng: random.Random) -> list[str]:
    """A sequential progression: descending fifths, or rising 5-6."""
    if rng.random() < 0.65:
        chain = (["I", "IV", "viio", "iii", "vi", "ii", "V", "I"] if mode == "major"
                 else ["i", "iv", "bVII", "III", "VI", "iio", "V", "i"])
        start = rng.choice([0, 1, 3]) if n < len(chain) else 0
        seq = chain[start:start + n]
        while len(seq) < n:
            seq.append(chain[(start + len(seq)) % len(chain)])
        # sevenths make a fifths sequence sing
        return [s + "7" if k % 2 == 1 and not s.endswith("o") else s
                for k, s in enumerate(seq)]
    chain = (["I", "vi6", "ii", "V7/V", "V", "iii", "vi", "IV"] if mode == "major"
             else ["i", "VI6", "iv", "V7/III", "III", "VI", "iio6", "V"])
    return (chain * 2)[:n]


def _pedal(harmonies: list[Harmony], key: Key, spec: PhraseHarmonySpec) -> None:
    """Hold the tonic in the bass under the opening chords — or, for a
    passage leading home, the dominant under all of it."""
    if spec.pedal_pc is not None:
        for h in harmonies:
            h.pedal = spec.pedal_pc
        return
    tonic_pc = key.tonic_pc
    limit = spec.start + spec.bar_len * max(2, spec.bars // 2)
    for h in harmonies:
        if h.onset >= limit or h.cadence:
            break
        h.pedal = tonic_pc


def _merge_repeats(hs: list[Harmony]) -> list[Harmony]:
    out: list[Harmony] = []
    for h in hs:
        if out and out[-1].roman == h.roman and out[-1].key == h.key \
                and out[-1].pedal == h.pedal and not out[-1].cadence:
            out[-1] = replace(out[-1], dur=out[-1].dur + h.dur, cadence=h.cadence)
            continue
        out.append(h)
    return out


# ---------------------------------------------------------------------------
# letting the melody have its say
# ---------------------------------------------------------------------------
#: What a chord may become when the tune over it asks: the same chord
#: coloured, or another chord doing the same job.
_ALTERNATIVES = {
    "major": {
        "I": ["I", "I6", "I(add6)", "I(maj7)", "I(add9)", "vi", "iii", "vi7"],
        "vi": ["vi", "vi7", "I6", "iii", "IV(maj7)"],
        "iii": ["iii", "iii7", "I6", "V6"],
        "IV": ["IV", "IV(maj7)", "ii7", "ii65", "ii", "IV(add6)", "iv", "iv(add6)"],
        "ii": ["ii", "ii7", "ii65", "IV", "IV(add6)", "ii%7"],
        "V": ["V", "V7", "V9", "V65", "V43", "viio7"],
        "vii": ["viio7", "V7", "viio6"],
    },
    "minor": {
        "i": ["i", "i6", "i7", "i(add6)", "i(add9)", "i(maj7)", "VI", "III"],
        "VI": ["VI", "VI(maj7)", "iv6", "i6"],
        "III": ["III", "i6", "III+"],
        "iv": ["iv", "iv7", "iv6", "iv(add6)", "ii%65", "ii%7", "VI", "N6"],
        "ii": ["ii%7", "ii%65", "iv", "iv(add6)", "iv6"],
        "V": ["V", "V7", "V7b9", "V9", "V65", "viio7"],
        "vii": ["viio7", "V7", "viio65"],
        "bVII": ["bVII", "bVII7", "v7"],
        "N": ["N6", "iv", "iv6"],
    },
}
_PLAIN_STYLES = ("classical", "baroque")


def _alternatives(roman: str, key: Key, style: HarmonyStyle) -> list[str]:
    if "/" in roman or roman[:2] in ("It", "Fr", "Ge", "Ca"):
        return []
    table = _ALTERNATIVES["minor" if key.is_minor else "major"]
    c = core(roman)
    opts = table.get(c) or table.get(c.lower()) or []
    if style.name in _PLAIN_STYLES:
        opts = [o for o in opts if "(" not in o and "b9" not in o and "+" not in o]
    return opts


def revise(harmonies: list[Harmony], melody, style: HarmonyStyle, key: Key, beat: F,
           protect: int = 2, keep_first: bool = True) -> list[Harmony]:
    """Recolour or replace chords that fight the melody written over them,
    keeping each chord's function, and leaving the cadence alone (its last
    ``protect`` chords). A long or accented melody note that is not in its
    chord and does not resolve like a passing note is what counts."""
    notes = sorted((n for n in melody), key=lambda n: n.onset)
    out: list[Harmony] = []
    fixed_from = max(0, len(harmonies) - protect)
    for i, h in enumerate(harmonies):
        if i >= fixed_from or h.cadence:
            out.append(h)
            continue
        weights = _melody_weights(notes, h, beat)
        if not weights:
            out.append(h)
            continue

        def clash(pcs: set[int]) -> float:
            return sum(w for pc, w in weights if pc not in pcs)

        base = clash(h.pcs)
        if base < 0.6:
            out.append(h)
            continue
        best, best_cost = h, base
        for alt in _alternatives(h.roman, key, style):
            if alt == h.roman:
                continue
            if keep_first and i == 0 and core(alt) != core(h.roman):
                continue          # a phrase keeps its opening chord, at most coloured
            try:
                cand = Harmony(alt, key, h.onset, h.dur, pedal=h.pedal)
            except Exception:
                continue
            cost = clash(cand.pcs)
            cost += 0.35 if core(alt) == core(h.roman) else 0.8
            if cand.bass_pc != h.bass_pc:
                cost += 0.4
            if "(" in alt and style.name not in ("russian", "impressionist", "film"):
                cost += 0.3
            if cost < best_cost - 0.25:
                best, best_cost = cand, cost
        out.append(best)
    return _merge_repeats(out)


def _inversions(roman: str) -> list[str]:
    """The same chord with another note in the bass: a triad in first
    inversion (or back in root position), a seventh chord in any position."""
    import re
    head, slash, target = roman.partition("/")
    if "(" in head or head[:2] in ("It", "Fr", "Ge", "Ca") or head.startswith("N"):
        return []
    m = re.match(r"^([b#]?[ivIV]+[o%+]?)(\d*)(b9)?$", head)
    if not m:
        return []
    base, fig, flat9 = m.groups()
    if flat9:
        return []
    figs = {"": ["6"], "6": [""], "64": ["", "6"], "7": ["65", "43", "42"],
            "65": ["7", "43"], "43": ["7", "65"], "42": ["7", "65"]}.get(fig, [])
    return [base + f + slash + target for f in figs]


def fix_parallels(harmonies: list[Harmony], melody, beat: F, key: Key,
                  protect: int = 1) -> list[Harmony]:
    """Parallel octaves or fifths between the tune and the bass, where the
    chord changes, are taken out the way a composer takes them out: by
    putting another note of the chord in the bass. The cadence (the last
    ``protect`` chords) and the phrase's first chord keep their bass."""
    notes = sorted(melody, key=lambda n: n.onset)
    if not notes:
        return harmonies
    out = list(harmonies)

    def sounding(t: F):
        cur = None
        for n in notes:
            if n.onset <= t < n.onset + n.dur:
                return n
            if n.onset < t:
                cur = n
        return cur

    def before(t: F):
        cur = None
        for n in notes:
            if n.onset < t:
                cur = n
        return cur

    def parallel(h0: Harmony, h1: Harmony) -> bool:
        b = sounding(h1.onset)
        if b is None or h0.bass_pc == h1.bass_pc:
            return False
        # the note just before the change, and the one on the last beat
        # before it (parallels by accent are heard too)
        last_beat = h1.onset - beat if (h1.onset - h0.onset) >= beat else h0.onset
        for a in {id(x): x for x in (before(h1.onset), sounding(last_beat))
                  if x is not None}.values():
            if a is b or a.midi == b.midi:
                continue
            iv0, iv1 = (a.midi - h0.bass_pc) % 12, (b.midi - h1.bass_pc) % 12
            if iv0 != iv1 or iv0 not in (0, 7):
                continue
            d = (h1.bass_pc - h0.bass_pc) % 12
            bass_dir = 1 if 0 < d <= 6 else -1
            if (b.midi > a.midi) == (bass_dir > 0):
                return True
        return False

    last_free = len(out) - protect
    for i in range(1, len(out)):
        if not parallel(out[i - 1], out[i]):
            continue
        fixed = False
        for j in ([i] if i < last_free else []) + ([i - 1] if i - 1 > 0 else []):
            for label in _inversions(out[j].roman):
                try:
                    cand = Harmony(label, key, out[j].onset, out[j].dur, pedal=out[j].pedal,
                                   cadence=out[j].cadence)
                except Exception:
                    continue
                trial = out[:j] + [cand] + out[j + 1:]
                bad = parallel(trial[i - 1], trial[i]) or \
                    (j > 0 and parallel(trial[j - 1], trial[j])) or \
                    (j + 1 < len(trial) and parallel(trial[j], trial[j + 1]))
                if not bad:
                    out = trial
                    fixed = True
                    break
            if fixed:
                break
    return out


def _melody_weights(notes, h: Harmony, beat: F) -> list[tuple[int, float]]:
    """(pitch class, weight) of each melody note sounding over ``h``: how
    long it sounds, more if it starts on a beat, much less if it is a short
    note passing by step."""
    out = []
    for k, n in enumerate(notes):
        a, b = max(n.onset, h.onset), min(n.onset + n.dur, h.onset + h.dur)
        if b <= a:
            continue
        w = float(b - a)
        on_beat = n.onset >= h.onset and (n.onset - h.onset) % beat == 0
        if on_beat:
            w *= 1.5
        prev = notes[k - 1].midi if k else None
        nxt = notes[k + 1].midi if k + 1 < len(notes) else None
        stepwise = prev is not None and nxt is not None and abs(n.midi - prev) <= 2 and \
            abs(nxt - n.midi) <= 2
        if n.dur <= beat / 2 and stepwise:
            w *= 0.2
        out.append((n.midi % 12, w))
    return out


# ---------------------------------------------------------------------------
# judging a progression
# ---------------------------------------------------------------------------
def score_progression(hs: list[Harmony], spec: PhraseHarmonySpec) -> float:
    """Higher is better: a singing bass, no stuck chords, a real cadence, and
    no chord-to-chord moves a composer of the style would avoid."""
    if not hs:
        return -1e9
    s = 0.0
    basses = [h.bass_pc for h in hs]
    for a, b in zip(basses, basses[1:]):
        d = min((a - b) % 12, (b - a) % 12)
        s += {0: 0.2, 1: 1.0, 2: 1.0, 3: 0.4, 4: 0.4, 5: 0.9, 6: -1.5}.get(d, 0.0)
    romans = [h.roman for h in hs]
    for a, b in zip(romans, romans[1:]):
        fa, fb = function_of(a), function_of(b)
        if fa == "D" and fb == "S" and "/" not in a:
            s -= 1.6                      # retrogression
        if a == b:
            s -= 0.8
        tgt = _applied_target(a)
        if tgt is not None and not _goes_to(b, tgt):
            s -= 4.0                      # an applied chord that doesn't resolve
        if a[:2] in ("It", "Fr", "Ge") and not (core(b) == "V" or b.startswith("Cad")):
            s -= 4.0
    distinct = len(set(romans))
    s += 0.35 * min(distinct, 6)
    # the tonic should not keep coming back within a phrase
    tonic = sum(1 for r in romans[1:-1] if core(r) in ("I", "i") and "/" not in r)
    s -= 0.5 * max(0, tonic - 1)
    last = hs[-1]
    if spec.cadence in ("PAC", "IAC", "plagal") and core(last.roman) not in ("I", "i"):
        s -= 5
    if spec.cadence == "HC" and core(last.roman) not in ("V",):
        s -= 5
    return s


# ---------------------------------------------------------------------------
# helpers for the rest of the composer
# ---------------------------------------------------------------------------
def chord_pcs(h: Harmony) -> set[int]:
    return set(h.chord.pcs)


def chord_tone_midis(h: Harmony, low: int, high: int) -> list[int]:
    pcs = chord_pcs(h)
    return [m for m in range(low, high + 1) if m % 12 in pcs]


def spell(midi: int, h: Harmony) -> Pitch:
    """Spell ``midi`` as it belongs to the chord if it's a chord tone, else in
    the key (with the chord's accidentals preferred)."""
    for p in h.chord.pitches(4, h.key):
        if p.pc == midi % 12:
            return Pitch.build(p.step, p.alter, (midi - p.pc) // 12 - 1 +
                               _octave_fix(p.step, p.alter))
    return h.key.spell(midi)


def _octave_fix(step: str, alter: int) -> int:
    """B# and Cb sit across the octave boundary from their MIDI numbers."""
    if step == "B" and alter > 0:
        return -1
    if step == "C" and alter < 0:
        return 1
    return 0


def tension(h: Harmony) -> float:
    """How far a chord pulls away from rest, 0..1, for dynamics and texture."""
    q = h.chord.quality
    base = {"maj": 0.1, "min": 0.15, "six": 0.2, "min_add6": 0.3, "add9": 0.25,
            "min_add9": 0.3, "maj7": 0.3, "min7": 0.3, "min_maj7": 0.45, "dom7": 0.6,
            "dom9": 0.65, "dom7b9": 0.75, "dom13": 0.7, "half_dim7": 0.55, "dim": 0.5,
            "dim7": 0.8, "aug": 0.7, "it6": 0.75, "fr6": 0.8, "ger6": 0.8,
            "sus4": 0.4}.get(q, 0.4)
    if h.function == "D":
        base += 0.1
    if h.roman.startswith("Cad"):
        base = 0.55
    return min(1.0, base)


def roman_distance(a: str, b: str) -> float:
    return 0.0 if a == b else 1.0


def log_weight(w: float) -> float:
    return math.log(max(w, 1e-6))
