"""Pitch, interval and key representations with correct enharmonic spelling.

Notation quality lives or dies on spelling: a D-flat minor passage written with
C-sharps is unreadable.  Everything downstream therefore carries a *spelled*
pitch (step + alteration + octave) rather than a bare MIDI number.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

# Semitone offset of each diatonic step above C.
STEP_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
STEPS = ("C", "D", "E", "F", "G", "A", "B")
STEP_INDEX = {s: i for i, s in enumerate(STEPS)}

_ACCIDENTAL_TEXT = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}
_ACCIDENTAL_NAME = {-2: "flat-flat", -1: "flat", 0: "natural", 1: "sharp", 2: "double-sharp"}

_PITCH_RE = re.compile(r"^([A-Ga-g])([#b x]*)(-?\d+)?$")


@dataclass(frozen=True, order=True)
class Pitch:
    """A spelled pitch.  ``step`` is a letter name, ``alter`` is in semitones."""

    midi: int
    step: str
    alter: int
    octave: int

    @staticmethod
    def build(step: str, alter: int, octave: int) -> "Pitch":
        step = step.upper()
        midi = STEP_SEMITONE[step] + alter + (octave + 1) * 12
        return Pitch(midi, step, alter, octave)

    @staticmethod
    def parse(text: str) -> "Pitch":
        """Parse ``C4``, ``Bb3``, ``F#5``, ``Ebb2``.  Octave defaults to 4."""
        m = _PITCH_RE.match(text.strip().replace("♯", "#").replace("♭", "b"))
        if not m:
            raise ValueError(f"unparseable pitch {text!r}")
        step, accs, octv = m.group(1).upper(), m.group(2) or "", m.group(3)
        alter = accs.count("#") + 2 * accs.count("x") - accs.count("b")
        return Pitch.build(step, alter, int(octv) if octv is not None else 4)

    # -- naming -----------------------------------------------------------
    @property
    def name(self) -> str:
        return f"{self.step}{_ACCIDENTAL_TEXT.get(self.alter, '?')}"

    @property
    def accidental_name(self) -> str:
        return _ACCIDENTAL_NAME.get(self.alter, "natural")

    @property
    def diatonic(self) -> int:
        """Absolute diatonic index — lets us measure intervals by letter."""
        return self.octave * 7 + STEP_INDEX[self.step]

    @property
    def pc(self) -> int:
        return self.midi % 12

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.name}{self.octave}"

    # -- arithmetic -------------------------------------------------------
    def transpose_chromatic(self, semitones: int, prefer_sharps: bool | None = None) -> "Pitch":
        return from_midi(self.midi + semitones, prefer_sharps=prefer_sharps)

    def transpose_diatonic(self, steps: int, key: "Key | None" = None,
                           pcs: Sequence[int] | None = None) -> "Pitch":
        """Move ``steps`` letter-names, taking the accidental from the key.

        Deriving the alteration from the key signature (rather than searching
        pitch classes) is what keeps E-flat minor spelled with flats: a step
        below Eb is Db, never the enharmonic D#.
        """
        d = self.diatonic + steps
        octave, idx = divmod(d, 7)
        step = STEPS[idx]
        base = STEP_SEMITONE[step]

        if key is None and pcs is None:
            return Pitch.build(step, self.alter, octave)

        sig = key.signature_alters.get(step, 0) if key is not None else 0
        allowed = set(pcs) if pcs is not None else (set(key.scale_pcs) if key else set())
        if not allowed:
            return Pitch.build(step, sig, octave)
        if (base + sig) % 12 in allowed:
            return Pitch.build(step, sig, octave)
        # Chromatic variants (harmonic/melodic minor, borrowed chords): take the
        # alteration closest to the signature so the page stays readable.
        cands = [a for a in (-2, -1, 0, 1, 2) if (base + a) % 12 in allowed]
        if not cands:
            return Pitch.build(step, sig, octave)
        cands.sort(key=lambda a: (abs(a - sig), abs(a)))
        return Pitch.build(step, cands[0], octave)

    def transpose_by(self, iv: "Interval") -> "Pitch":
        """Transpose by a spelled interval, preserving letter-name logic."""
        d = self.diatonic + iv.steps
        octave, idx = divmod(d, 7)
        step = STEPS[idx]
        target = self.midi + iv.semitones
        alter = target - (STEP_SEMITONE[step] + (octave + 1) * 12)
        if abs(alter) > 2:  # fall back to a plain chromatic respelling
            return from_midi(target)
        return Pitch.build(step, alter, octave)

    def respell(self, sharps: bool) -> "Pitch":
        return from_midi(self.midi, prefer_sharps=sharps)

    def with_octave(self, octave: int) -> "Pitch":
        return Pitch.build(self.step, self.alter, octave)


_SHARP_SPELL = [("C", 0), ("C", 1), ("D", 0), ("D", 1), ("E", 0), ("F", 0),
                ("F", 1), ("G", 0), ("G", 1), ("A", 0), ("A", 1), ("B", 0)]
_FLAT_SPELL = [("C", 0), ("D", -1), ("D", 0), ("E", -1), ("E", 0), ("F", 0),
               ("G", -1), ("G", 0), ("A", -1), ("A", 0), ("B", -1), ("B", 0)]


def from_midi(midi: int, prefer_sharps: bool | None = None, key: "Key | None" = None) -> Pitch:
    """Spell a MIDI number.  A key, when supplied, drives the choice."""
    midi = max(0, min(127, int(midi)))
    if key is not None:
        return key.spell(midi)
    sharps = True if prefer_sharps is None else prefer_sharps
    table = _SHARP_SPELL if sharps else _FLAT_SPELL
    step, alter = table[midi % 12]
    octave = midi // 12 - 1
    # A B# / Cb crossing would shift the octave; the tables above avoid that.
    return Pitch.build(step, alter, octave)


@dataclass(frozen=True)
class Interval:
    """A spelled interval: ``steps`` letter-names wide, ``semitones`` tall."""

    steps: int
    semitones: int

    @staticmethod
    def between(a: Pitch, b: Pitch) -> "Interval":
        return Interval(b.diatonic - a.diatonic, b.midi - a.midi)

    @staticmethod
    def named(quality: str, number: int) -> "Interval":
        """``Interval.named('m', 3)`` → minor third.  Qualities: P M m A d."""
        sign = 1 if number > 0 else -1
        number = abs(number)
        simple = (number - 1) % 7 + 1
        octaves = (number - 1) // 7
        perfect = simple in (1, 4, 5)
        base = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}[simple]
        if perfect:
            adj = {"P": 0, "A": 1, "d": -1, "AA": 2, "dd": -2}[quality]
        else:
            adj = {"M": 0, "m": -1, "A": 1, "d": -2, "AA": 2, "dd": -3}[quality]
        return Interval(sign * (number - 1), sign * (base + adj + 12 * octaves))

    @property
    def simple_semitones(self) -> int:
        return self.semitones % 12

    def inverted(self) -> "Interval":
        return Interval(-self.steps, -self.semitones)

    def is_consonant(self, strict: bool = False) -> bool:
        s = self.simple_semitones
        if strict:
            return s in (0, 3, 4, 7, 8, 9)
        return s in (0, 3, 4, 5, 7, 8, 9)


# ---------------------------------------------------------------------------
# Scales
# ---------------------------------------------------------------------------
SCALE_INTERVALS: dict[str, tuple[int, ...]] = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "natural_minor": (0, 2, 3, 5, 7, 8, 10),
    "harmonic_minor": (0, 2, 3, 5, 7, 8, 11),
    "melodic_minor": (0, 2, 3, 5, 7, 9, 11),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "aeolian": (0, 2, 3, 5, 7, 8, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
    "whole_tone": (0, 2, 4, 6, 8, 10),
    "octatonic": (0, 2, 3, 5, 6, 8, 9, 11),
    "pentatonic_major": (0, 2, 4, 7, 9),
    "pentatonic_minor": (0, 3, 5, 7, 10),
    "blues": (0, 3, 5, 6, 7, 10),
    "phrygian_dominant": (0, 1, 4, 5, 7, 8, 10),
    "hungarian_minor": (0, 2, 3, 6, 7, 8, 11),
    "acoustic": (0, 2, 4, 6, 7, 9, 10),
}

# Circle-of-fifths position for each major tonic, i.e. the key signature.
_MAJOR_FIFTHS = {"C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7,
                 "F": -1, "Bb": -2, "Eb": -3, "Ab": -4, "Db": -5, "Gb": -6, "Cb": -7,
                 "G#": 8, "D#": 9, "A#": 10}
_MINOR_FIFTHS = {"A": 0, "E": 1, "B": 2, "F#": 3, "C#": 4, "G#": 5, "D#": 6, "A#": 7,
                 "D": -1, "G": -2, "C": -3, "F": -4, "Bb": -5, "Eb": -6, "Ab": -7,
                 "Db": -8}

# Letter spelling implied by each key signature, sharps then flats.
_SHARP_ORDER = ("F", "C", "G", "D", "A", "E", "B")
_FLAT_ORDER = ("B", "E", "A", "D", "G", "C", "F")


@dataclass(frozen=True)
class Key:
    """A tonic plus a mode.  Knows its key signature and how to spell notes."""

    tonic: str = "C"          # spelled letter + accidental, e.g. "Eb"
    mode: str = "major"       # "major", "minor", or any name in SCALE_INTERVALS

    @staticmethod
    def parse(text: str) -> "Key":
        """Parse "Eb minor", "F# dorian", "C".  Raises ValueError on nonsense."""
        raw = (text or "").strip().replace("\u266f", "#").replace("\u266d", "b")
        if not raw:
            raise ValueError("empty key")
        m = re.match(r"^([A-Ga-g])\s*(##|bb|#|b|sharp|flat|)\s*[-\s]*(.*)$", raw)
        if not m:
            raise ValueError(f"unparseable key: {text!r}")
        letter, acc, rest = m.group(1).upper(), m.group(2).lower(), m.group(3).strip().lower()
        acc = {"sharp": "#", "flat": "b", "": ""}.get(acc, acc)
        tonic = letter + acc

        mode = rest.replace("-", "_").replace(" ", "_")
        aliases = {"": "major", "maj": "major", "major": "major", "min": "minor",
                   "m": "minor", "minor": "minor", "natural_minor": "minor",
                   "harmonic_minor": "harmonic_minor", "melodic_minor": "melodic_minor",
                   "whole_tone": "whole_tone", "wholetone": "whole_tone"}
        mode = aliases.get(mode, mode)
        if mode not in SCALE_INTERVALS and mode not in ("major", "minor"):
            raise ValueError(f"unknown mode {rest!r} in key {text!r}")
        return Key(tonic, mode)

    # -- basics -----------------------------------------------------------
    @property
    def is_minor(self) -> bool:
        return self.mode in ("minor", "natural_minor", "harmonic_minor",
                             "melodic_minor", "aeolian", "dorian", "phrygian", "locrian")

    @property
    def tonic_pc(self) -> int:
        p = Pitch.parse(self.tonic + "4")
        return p.pc

    @property
    def fifths(self) -> int:
        """Key-signature position on the circle of fifths (-7..+7)."""
        table = _MINOR_FIFTHS if self.is_minor else _MAJOR_FIFTHS
        if self.tonic in table:
            return table[self.tonic]
        # Modal tonics: reduce to the relative major/minor signature.
        offsets = {"dorian": -2, "phrygian": -4, "lydian": 1, "mixolydian": -1,
                   "locrian": -5, "aeolian": -3}
        off = offsets.get(self.mode, 0)
        base = _MAJOR_FIFTHS.get(self.tonic, 0)
        return max(-7, min(7, base + off))

    @property
    def prefers_sharps(self) -> bool:
        return self.fifths > 0

    @property
    def scale_pcs(self) -> tuple[int, ...]:
        mode = "natural_minor" if self.mode == "minor" else self.mode
        iv = SCALE_INTERVALS.get(mode, SCALE_INTERVALS["major"])
        return tuple(sorted((self.tonic_pc + i) % 12 for i in iv))

    def scale_pcs_for(self, variant: str) -> tuple[int, ...]:
        iv = SCALE_INTERVALS.get(variant, SCALE_INTERVALS["major"])
        return tuple(sorted((self.tonic_pc + i) % 12 for i in iv))

    # -- spelling ---------------------------------------------------------
    @property
    def signature_alters(self) -> dict[str, int]:
        f = self.fifths
        out: dict[str, int] = {}
        if f > 0:
            for i in range(min(f, 7)):
                out[_SHARP_ORDER[i]] = 1
        elif f < 0:
            for i in range(min(-f, 7)):
                out[_FLAT_ORDER[i]] = -1
        return out

    def spell(self, midi: int) -> Pitch:
        """Spell a MIDI number in a way that reads naturally in this key."""
        sig = self.signature_alters
        octave_guess = midi // 12 - 1
        candidates: list[tuple[int, Pitch]] = []
        for step in STEPS:
            for octv in (octave_guess - 1, octave_guess, octave_guess + 1):
                base = STEP_SEMITONE[step] + (octv + 1) * 12
                alter = midi - base
                if abs(alter) > 2:
                    continue
                p = Pitch.build(step, alter, octv)
                if p.midi != midi:
                    continue
                cost = 0.0
                nat = sig.get(step, 0)
                if alter == nat:
                    cost -= 4          # diatonic to the key: strongly preferred
                cost += abs(alter) * 2  # avoid double accidentals
                if alter != 0 and alter == -nat:
                    cost += 1           # a cancelling accidental is a little awkward
                if (alter > 0 and self.fifths < 0) or (alter < 0 and self.fifths > 0):
                    cost += 1.5         # don't mix sharps into a flat key
                candidates.append((cost, p))
        if not candidates:
            return from_midi(midi, prefer_sharps=self.prefers_sharps)
        candidates.sort(key=lambda c: (c[0], abs(c[1].alter)))
        return candidates[0][1]

    def degree_pitch(self, degree: int, octave: int = 4, variant: str | None = None) -> Pitch:
        """Scale degree 1..7 (may exceed for higher octaves) as a spelled pitch."""
        mode = variant or ("natural_minor" if self.mode == "minor" else self.mode)
        iv = SCALE_INTERVALS.get(mode, SCALE_INTERVALS["major"])
        n = len(iv)
        idx = (degree - 1) % n
        oct_add = (degree - 1) // n
        semis = iv[idx]
        tonic = Pitch.parse(self.tonic + str(octave))
        step_idx = (STEP_INDEX[tonic.step] + idx) % 7
        step_oct = tonic.octave + (STEP_INDEX[tonic.step] + idx) // 7 + oct_add
        step = STEPS[step_idx]
        target = tonic.midi + semis + 12 * oct_add
        alter = target - (STEP_SEMITONE[step] + (step_oct + 1) * 12)
        if abs(alter) > 2:
            return from_midi(target, prefer_sharps=self.prefers_sharps)
        return Pitch.build(step, alter, step_oct)

    @property
    def relative(self) -> "Key":
        if self.is_minor:
            return Key(self.degree_pitch(3).name, "major")
        return Key(self.degree_pitch(6).name, "minor")

    @property
    def parallel(self) -> "Key":
        return Key(self.tonic, "major" if self.is_minor else "minor")

    def dominant_key(self) -> "Key":
        return Key(self.degree_pitch(5).name, self.mode)

    def subdominant_key(self) -> "Key":
        return Key(self.degree_pitch(4).name, self.mode)

    def transposed(self, semitones: int) -> "Key":
        p = Pitch.parse(self.tonic + "4").transpose_chromatic(
            semitones, prefer_sharps=self.prefers_sharps)
        return Key(p.name, self.mode)

    def contains(self, pitch: Pitch) -> bool:
        return pitch.pc in self.scale_pcs

    def __str__(self) -> str:  # pragma: no cover - trivial
        pretty = self.mode.replace("_", " ")
        return f"{self.tonic} {pretty}"


def nearest_in_scale(midi: int, pcs: Iterable[int]) -> int:
    """Snap a MIDI number to the closest member of a pitch-class set."""
    pcs = set(pcs)
    for d in range(0, 7):
        for cand in (midi - d, midi + d):
            if cand % 12 in pcs:
                return cand
    return midi
