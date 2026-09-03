"""Harmonic planning for a section: choose romans, colour them, land a cadence."""
from __future__ import annotations

import random
import re

from ..theory.harmony import CADENCES, PROGRESSION_LIBRARY, sequence_progression
from ..theory.pitch import Key
from .styles import StyleProfile


def build_progression(key: Key, style: StyleProfile, rng: random.Random, *,
                      chords_needed: int, energy: float = 0.5,
                      cadence: str = "authentic", role: str = "theme",
                      explicit: list[str] | None = None) -> list[str]:
    """Return exactly ``chords_needed`` roman numerals ending in a cadence."""
    if explicit:
        out = list(explicit)
        while len(out) < chords_needed:
            out.append(out[len(out) % len(explicit)])
        return out[:chords_needed]

    cad = CADENCES.get(cadence, CADENCES["authentic"])
    cad = _fit_mode(cad, key)
    body_len = max(1, chords_needed - len(cad))

    pool_name = style.progression_pool_minor if key.is_minor else style.progression_pool_major
    pool = PROGRESSION_LIBRARY.get(pool_name, PROGRESSION_LIBRARY["classical_major"])

    body: list[str] = []
    if role in ("development", "transition", "cadenza") or energy > 0.72:
        pattern = rng.choice(["fifths", "descending_thirds", "rosalia", "chromatic_descent"])
        body = sequence_progression("i" if key.is_minor else "I", key, body_len, pattern)
    else:
        base = list(rng.choice(pool))
        while len(body) < body_len:
            body.extend(base)
        body = body[:body_len]

    prog = body + cad
    prog = prog[:chords_needed] if len(prog) > chords_needed else prog
    while len(prog) < chords_needed:
        prog.insert(0, "i" if key.is_minor else "I")

    prog = _colour(prog, key, style, rng, energy)
    # Guarantee the cadence survives colouring.
    prog[-len(cad):] = cad
    return prog


def _fit_mode(romans: list[str], key: Key) -> list[str]:
    if not key.is_minor:
        return [r.replace("i", "I").replace("iv", "IV") if r in ("i", "iv") else r
                for r in romans]
    out = []
    for r in romans:
        if r == "I":
            out.append("i")
        elif r == "IV":
            out.append("iv")
        elif r == "vi":
            out.append("VI")
        elif r == "ii6":
            out.append("iio6")
        else:
            out.append(r)
    return out


def _colour(romans: list[str], key: Key, style: StyleProfile, rng: random.Random,
            energy: float) -> list[str]:
    """Apply sevenths, applied dominants and borrowed chords at style rates."""
    out: list[str] = []
    chrom = style.chromaticism * (0.6 + energy * 0.9)
    for i, r in enumerate(romans):
        nxt = romans[i + 1] if i + 1 < len(romans) else None
        cur = r
        # Tonicise the next chord with an applied dominant.
        if (nxt and rng.random() < chrom * 0.6 and nxt not in ("I", "i")
                and "/" not in nxt and not nxt.startswith("b")):
            # The tonicised target is named by its bare numeral: "V7/ii", never
            # "V7/ii65", which would reparse as a chord of a chord.
            target = re.match(r"[b#]*[ivIV]+[o+%]?", nxt)
            if target:
                out.append(f"V{'7' if rng.random() < 0.6 else ''}/{target.group(0)}")
                continue
        # Figures belong on the numeral itself, never after a "/target" suffix.
        head, sep, target = cur.partition("/")
        if rng.random() < style.seventh_rate and "7" not in head and "6" not in head:
            if head in ("V", "v"):
                head = "V7"
            elif head.islower():
                head = head + "7"
            elif rng.random() < 0.4:
                head = head + "7"
        if rng.random() < style.extension_rate and head.endswith("7") and not sep:
            head = head[:-1] + rng.choice(["9", "9", "11"])
        if not sep and rng.random() < chrom * 0.3:
            borrow = {"IV": "iv", "vi": "bVI", "ii": "iio", "VI": "bVI",
                      "III": "bIII", "VII": "bVII"}.get(head)
            if borrow:
                head = borrow
        cur = head + sep + target
        out.append(cur)
    return out


def chord_durations(total_beats: float, style: StyleProfile, rng: random.Random,
                    beats_per_bar: float, density: str | None = None) -> list[float]:
    """Split a section's length into chord durations in quarter notes."""
    d = density or style.harmonic_rhythm
    step = {"slow": beats_per_bar * 2, "moderate": beats_per_bar,
            "fast": beats_per_bar / 2, "very_fast": beats_per_bar / 4}.get(
                d, beats_per_bar)
    step = max(0.5, min(step, total_beats))
    out: list[float] = []
    acc = 0.0
    while acc < total_beats - 1e-6:
        cur = step
        # Occasionally halve or double so the harmonic rhythm breathes.
        if rng.random() < 0.16 and step >= 2:
            cur = step / 2
        elif rng.random() < 0.10 and acc + step * 2 <= total_beats:
            cur = step * 2
        cur = min(cur, total_beats - acc)
        out.append(cur)
        acc += cur
    return out
