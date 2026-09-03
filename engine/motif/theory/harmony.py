"""Chords, roman-numeral analysis and functional progressions."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Sequence

from .pitch import Interval, Key, Pitch, STEPS, STEP_INDEX, from_midi

# Chord qualities as (diatonic-step, semitone) pairs above the root.  Carrying
# the letter distance is what lets a diminished seventh come out as D-F-Ab-Cb
# instead of the unreadable D-F-G#-B.
CHORD_SPEC: dict[str, tuple[tuple[int, int], ...]] = {
    "maj": ((0, 0), (2, 4), (4, 7)),
    "min": ((0, 0), (2, 3), (4, 7)),
    "dim": ((0, 0), (2, 3), (4, 6)),
    "aug": ((0, 0), (2, 4), (4, 8)),
    "sus4": ((0, 0), (3, 5), (4, 7)),
    "sus2": ((0, 0), (1, 2), (4, 7)),
    "maj7": ((0, 0), (2, 4), (4, 7), (6, 11)),
    "dom7": ((0, 0), (2, 4), (4, 7), (6, 10)),
    "min7": ((0, 0), (2, 3), (4, 7), (6, 10)),
    "min_maj7": ((0, 0), (2, 3), (4, 7), (6, 11)),
    "half_dim7": ((0, 0), (2, 3), (4, 6), (6, 10)),
    "dim7": ((0, 0), (2, 3), (4, 6), (6, 9)),
    "aug7": ((0, 0), (2, 4), (4, 8), (6, 10)),
    "maj9": ((0, 0), (2, 4), (4, 7), (6, 11), (8, 14)),
    "dom9": ((0, 0), (2, 4), (4, 7), (6, 10), (8, 14)),
    "min9": ((0, 0), (2, 3), (4, 7), (6, 10), (8, 14)),
    "dom11": ((0, 0), (2, 4), (4, 7), (6, 10), (8, 14), (10, 17)),
    "dom13": ((0, 0), (2, 4), (4, 7), (6, 10), (8, 14), (12, 21)),
    "add9": ((0, 0), (2, 4), (4, 7), (8, 14)),
    "min_add9": ((0, 0), (2, 3), (4, 7), (8, 14)),
    "six": ((0, 0), (2, 4), (4, 7), (5, 9)),
    "min6": ((0, 0), (2, 3), (4, 7), (5, 9)),
    "quartal": ((0, 0), (3, 5), (6, 10), (9, 15)),
    "mystic": ((0, 0), (3, 6), (6, 10), (9, 16), (12, 21), (15, 26)),
    "it6": ((0, 0), (2, 4), (5, 10)),    # b6 - 1 - #4
    "fr6": ((0, 0), (2, 4), (3, 6), (5, 10)),
    "ger6": ((0, 0), (2, 4), (4, 7), (5, 10)),
}

#: Semitone-only view, kept for pitch-class queries and the neural tokenizer.
CHORD_INTERVALS: dict[str, tuple[int, ...]] = {
    k: tuple(s for _, s in v) for k, v in CHORD_SPEC.items()
}


# MusicXML <kind> text for chord symbols.
KIND_XML = {
    "maj": "major", "min": "minor", "dim": "diminished", "aug": "augmented",
    "sus4": "suspended-fourth", "sus2": "suspended-second", "maj7": "major-seventh",
    "dom7": "dominant", "min7": "minor-seventh", "min_maj7": "major-minor",
    "half_dim7": "half-diminished", "dim7": "diminished-seventh",
    "aug7": "augmented-seventh", "maj9": "major-ninth", "dom9": "dominant-ninth",
    "min9": "minor-ninth", "dom11": "dominant-11th", "dom13": "dominant-13th",
    "add9": "major", "min_add9": "minor", "six": "major-sixth", "min6": "minor-sixth",
}

_ROMAN_VALUES = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7}
_ROMAN_RE = re.compile(
    r"^(?P<pre>[b#]*)(?P<roman>[ivIV]+)(?P<qual>o|\+|%|ø|)?(?P<fig>7|65|43|42|2|9|11|13|6|64)?"
    r"(?:/(?P<sec>[b#]*[ivIV]+))?$")


@dataclass(frozen=True)
class Chord:
    """A rooted sonority with an optional bass note (for inversions)."""

    root: Pitch
    quality: str = "maj"
    inversion: int = 0
    added: tuple[int, ...] = ()          # extra semitone offsets above the root
    omitted: tuple[int, ...] = ()        # chord-tone indices to drop
    roman: str = ""                      # analytic label, e.g. "V65/V"
    duration: float = 4.0                # in quarter notes; used by progressions

    @property
    def spec(self) -> tuple[tuple[int, int], ...]:
        base = list(CHORD_SPEC.get(self.quality, CHORD_SPEC["maj"]))
        for i in sorted(self.omitted, reverse=True):
            if 0 <= i < len(base):
                base.pop(i)
        for semis in self.added:
            steps = _DEFAULT_STEPS.get(semis, round(semis * 7 / 12))
            base.append((steps, semis))
        return tuple(sorted(set(base), key=lambda t: (t[1], t[0])))

    @property
    def intervals(self) -> tuple[int, ...]:
        return tuple(s for _, s in self.spec)

    @property
    def pcs(self) -> tuple[int, ...]:
        return tuple(sorted({(self.root.pc + i) % 12 for i in self.intervals}))

    def pitches(self, octave: int | None = None, key: Key | None = None) -> list[Pitch]:
        """Spelled chord tones, stacked upward from the root and then inverted."""
        root = self.root if octave is None else self.root.with_octave(octave)
        out = [_spell_step(root, st, se, key) for st, se in self.spec]
        for _ in range(min(self.inversion, len(out) - 1)):
            lo = out.pop(0)
            out.append(Pitch.build(lo.step, lo.alter, lo.octave + 1))
        return out

    @property
    def bass_pc(self) -> int:
        iv = self.intervals
        return (self.root.pc + iv[min(self.inversion, len(iv) - 1)]) % 12

    def bass_pitch(self, octave: int = 2, key: Key | None = None) -> Pitch:
        st, se = self.spec[min(self.inversion, len(self.spec) - 1)]
        return _spell_step(self.root.with_octave(octave), st, se, key)

    @property
    def is_seventh(self) -> bool:
        return len(self.intervals) >= 4

    @property
    def is_dominant_function(self) -> bool:
        return self.quality in ("dom7", "dom9", "dom11", "dom13", "dim7",
                                "half_dim7", "fr6", "ger6", "it6")

    def with_duration(self, d: float) -> "Chord":
        return replace(self, duration=d)

    def symbol(self) -> str:
        suffix = {"maj": "", "min": "m", "dim": "dim", "aug": "+", "dom7": "7",
                  "maj7": "maj7", "min7": "m7", "dim7": "dim7", "half_dim7": "m7b5",
                  "sus4": "sus4", "sus2": "sus2", "six": "6", "min6": "m6",
                  "min_maj7": "mMaj7", "dom9": "9", "maj9": "maj9", "min9": "m9",
                  "add9": "add9", "min_add9": "m(add9)", "it6": "It+6",
                  "fr6": "Fr+6", "ger6": "Ger+6"}.get(self.quality, self.quality)
        s = f"{self.root.name}{suffix}"
        if self.inversion:
            s += f"/{self.bass_pitch(3).name}"
        return s

    def __str__(self) -> str:  # pragma: no cover
        return self.roman or self.symbol()


#: Letter-distance a musician would write for a bare semitone count, used only
#: for user-supplied added tones where no chord spec exists.
_DEFAULT_STEPS = {0: 0, 1: 0, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4, 9: 5,
                  10: 6, 11: 6, 12: 7, 13: 7, 14: 8, 15: 8, 16: 9, 17: 10,
                  18: 10, 19: 11, 20: 12, 21: 12, 22: 13, 23: 13, 24: 14, 26: 15}


def _spell_step(root: Pitch, steps: int, semitones: int, key: Key | None = None) -> Pitch:
    """Spell the note ``steps`` letters and ``semitones`` above ``root``."""
    from .pitch import STEP_SEMITONE
    d = root.diatonic + steps
    octv, idx = divmod(d, 7)
    step = STEPS[idx]
    target = root.midi + semitones
    alter = target - (STEP_SEMITONE[step] + (octv + 1) * 12)
    if abs(alter) > 2:
        return key.spell(target) if key else from_midi(target)
    return Pitch.build(step, alter, octv)


def _spell_above(root: Pitch, semitones: int, key: Key | None = None) -> Pitch:
    steps = _DEFAULT_STEPS.get(semitones, round(semitones * 7 / 12))
    return _spell_step(root, steps, semitones, key)


# ---------------------------------------------------------------------------
# Roman numerals
# ---------------------------------------------------------------------------
_FIGURE_INVERSION = {"": 0, "6": 1, "64": 2, "7": 0, "65": 1, "43": 2, "42": 3,
                     "2": 3, "9": 0, "11": 0, "13": 0}


def roman_to_chord(roman: str, key: Key, octave: int = 4) -> Chord:
    """Turn ``V65/V``, ``bII``, ``viio7`` etc. into a spelled chord in ``key``."""
    text = roman.strip().replace("°", "o").replace("ø", "%")
    m = _ROMAN_RE.match(text)
    if not m:
        return Chord(key.degree_pitch(1, octave), "maj", roman=roman)
    pre, num, qual, fig, sec = (m.group("pre") or "", m.group("roman"),
                                m.group("qual") or "", m.group("fig") or "",
                                m.group("sec"))
    if sec:  # applied chord: build in the key of the secondary target
        target = roman_to_chord(sec, key, octave)
        tgt_mode = "minor" if target.quality in ("min", "min7", "dim", "dim7") else "major"
        local = Key(target.root.name, tgt_mode)
        base = roman_to_chord(pre + num + qual + fig, local, octave)
        return replace(base, roman=roman)

    degree = _ROMAN_VALUES[num.upper()]
    is_lower = num.islower()
    chrom = pre.count("#") - pre.count("b")

    variant = "harmonic_minor" if key.is_minor else key.mode
    root = key.degree_pitch(degree, octave, variant=variant if key.is_minor else None)
    if chrom:
        root = Pitch.build(root.step, root.alter + chrom, root.octave)

    if qual == "o":
        quality = "dim7" if fig in ("7", "65", "43", "42") else "dim"
    elif qual == "%":
        quality = "half_dim7"
    elif qual == "+":
        quality = "aug"
    elif is_lower:
        quality = "min7" if fig in ("7", "65", "43", "42") else "min"
    else:
        if fig in ("7", "65", "43", "42"):
            # V7 is dominant; other major-triad sevenths are major sevenths.
            quality = "dom7" if degree == 5 or (chrom and degree == 7) else "maj7"
        elif fig == "9":
            quality = "dom9" if degree == 5 else "maj9"
        elif fig in ("11", "13"):
            quality = "dom" + fig
        else:
            quality = "maj"
    inv = _FIGURE_INVERSION.get(fig, 0)
    return Chord(root, quality, inversion=inv, roman=roman)


def progression(romans: Sequence[str], key: Key, octave: int = 4,
                durations: Sequence[float] | None = None) -> list[Chord]:
    chords = [roman_to_chord(r, key, octave) for r in romans]
    if durations:
        chords = [c.with_duration(durations[i % len(durations)]) for i, c in enumerate(chords)]
    return chords


# ---------------------------------------------------------------------------
# Cadence and progression vocabulary
# ---------------------------------------------------------------------------
CADENCES: dict[str, list[str]] = {
    "authentic": ["V", "I"],
    "perfect_authentic": ["ii6", "V", "I"],
    "half": ["IV", "V"],
    "plagal": ["IV", "I"],
    "deceptive": ["V", "vi"],
    "phrygian": ["iv6", "V"],
    "picardy": ["V", "I"],
    "romantic": ["ii%7", "V7", "i"],
    "neapolitan": ["bII6", "V7", "i"],
    "rach": ["iv", "bII6", "V7", "i"],
}

#: Idiomatic chord successions keyed by stylistic family.
PROGRESSION_LIBRARY: dict[str, list[list[str]]] = {
    "classical_major": [
        ["I", "V", "vi", "iii", "IV", "I", "IV", "V"],
        ["I", "vi", "IV", "V"],
        ["I", "IV", "V", "I"],
        ["I", "V6", "vi", "V", "IV", "I6", "ii6", "V"],
        ["I", "V/V", "V", "I"],
    ],
    "classical_minor": [
        ["i", "iv", "V", "i"],
        ["i", "VI", "III", "VII", "iv", "V", "i"],
        ["i", "iv6", "V7", "i"],
        ["i", "V6", "i", "iv", "V", "i"],
    ],
    "romantic_minor": [
        ["i", "VI", "iv", "bII6", "V7", "i"],
        ["i", "iv", "V7/III", "III", "iv", "V7", "i"],
        ["i", "V43/iv", "iv6", "V7", "VI", "V7", "i"],
        ["i", "iio65", "V7", "i", "iv", "i64", "V7", "i"],
    ],
    "romantic_major": [
        ["I", "V7/vi", "vi", "V7/V", "V", "I"],
        ["I", "IV", "iv", "I", "V/V", "V7", "I"],
        ["I", "vi", "bVI", "IV", "V7", "I"],
    ],
    "baroque_major": [
        ["I", "V", "I", "IV", "V", "I"],
        ["I", "vi", "ii", "V", "I", "IV", "V", "I"],
        ["I", "V6", "vi", "iii6", "IV", "I6", "IV", "V"],
    ],
    "baroque_minor": [
        ["i", "V", "i", "iv", "V", "i"],
        ["i", "VII", "III", "VI", "iio6", "V", "i"],
    ],
    "impressionist": [
        ["I", "II", "bVII", "I"],
        ["i", "bVII", "bVI", "bVII"],
        ["Imaj9", "IVmaj7", "Imaj9", "bVIImaj7"],
    ],
    "modal": [
        ["i", "bVII", "bVI", "bVII"],
        ["i", "iv", "bVII", "i"],
    ],
    "pop": [
        ["I", "V", "vi", "IV"],
        ["vi", "IV", "I", "V"],
        ["I", "IV", "vi", "V"],
    ],
}

#: The classic descending-fifths engine, useful for sequences everywhere.
CIRCLE_OF_FIFTHS_MAJOR = ["I", "IV", "viio", "iii", "vi", "ii", "V", "I"]
CIRCLE_OF_FIFTHS_MINOR = ["i", "iv", "VII", "III", "VI", "iio", "V", "i"]


def sequence_progression(start: str, key: Key, length: int, pattern: str = "fifths") -> list[str]:
    """Generate a harmonic sequence — the workhorse of development sections."""
    circle = CIRCLE_OF_FIFTHS_MINOR if key.is_minor else CIRCLE_OF_FIFTHS_MAJOR
    if pattern == "fifths":
        try:
            i = circle.index(start)
        except ValueError:
            i = 0
        return [circle[(i + n) % len(circle)] for n in range(length)]
    if pattern == "descending_thirds":
        base = ["i", "VI", "iv", "ii%7", "VII", "V"] if key.is_minor else \
               ["I", "vi", "IV", "ii", "viio", "V"]
        return [base[n % len(base)] for n in range(length)]
    if pattern == "rosalia":       # ascending stepwise sequence
        base = ["i", "V6", "i", "iv", "i6", "iv"] if key.is_minor else \
               ["I", "V6", "I", "IV", "I6", "IV"]
        return [base[n % len(base)] for n in range(length)]
    if pattern == "chromatic_descent":
        base = ["i", "V43/iv", "iv6", "bII6", "V7"] if key.is_minor else \
               ["I", "V43/IV", "IV6", "iv6", "V7"]
        return [base[n % len(base)] for n in range(length)]
    return [start] * length


def harmonic_rhythm(bars: int, beats_per_bar: float, density: str = "moderate") -> list[float]:
    """Chord durations (in quarter notes) spanning ``bars`` bars."""
    total = bars * beats_per_bar
    per_bar = {"slow": beats_per_bar * 2, "moderate": beats_per_bar,
               "fast": beats_per_bar / 2, "very_fast": beats_per_bar / 4}
    step = per_bar.get(density, beats_per_bar)
    step = max(0.5, min(step, total))
    out: list[float] = []
    acc = 0.0
    while acc < total - 1e-6:
        d = min(step, total - acc)
        out.append(d)
        acc += d
    return out
