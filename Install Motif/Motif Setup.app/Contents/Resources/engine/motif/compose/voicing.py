"""Chord voicing with real voice leading.

Chords are voiced by searching arrangements of the chord tones and scoring them
for total motion, spacing, doubling and forbidden parallels — the same criteria
a harmony teacher marks against.
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass

from ..theory.harmony import Chord
from ..theory.pitch import Key, Pitch

# Comfortable ranges for four-part writing (MIDI numbers).
SATB_RANGES = [(40, 60), (52, 72), (57, 77), (60, 81)]   # bass, tenor, alto, soprano


@dataclass
class VoicingStyle:
    n_voices: int = 4
    low: int = 40
    high: int = 84
    max_spacing: int = 12          # max gap between adjacent upper voices
    max_span: int = 24
    double_root: float = 1.0
    allow_open: bool = True
    keep_common_tone: float = 1.2


def spell_in_chord(midi: int, chord: Chord, key: Key) -> Pitch:
    """Spell a note using the chord's own letter names where it is a chord tone."""
    for cp in chord.pitches(key=key):
        if cp.midi % 12 == midi % 12:
            cand = Pitch.build(cp.step, cp.alter, cp.octave)
            shift = midi - cand.midi
            if shift % 12 == 0:
                return Pitch.build(cp.step, cp.alter, cp.octave + shift // 12)
    return key.spell(midi)


def voice_chord(chord: Chord, key: Key, style: VoicingStyle,
                previous: list[Pitch] | None = None,
                soprano: Pitch | None = None,
                bass: Pitch | None = None,
                rng: random.Random | None = None,
                prev_chord: Chord | None = None) -> list[Pitch]:
    """Voice a single chord, optionally against a previous voicing."""
    rng = rng or random.Random(0)
    n = style.n_voices
    pcs = list(chord.pcs)

    bass_pitch = bass
    if bass_pitch is None:
        bpc = chord.bass_pc
        bass_center = style.low + 8
        cand = [m for m in range(style.low, min(style.low + 26, style.high - 12) + 1)
                if m % 12 == bpc]
        if cand:
            prev_midi = previous[0].midi if previous else bass_center
            # Stay in the bass register first, move smoothly second — a bass that
            # chases the nearest note climbs into the tenor and breeds parallels.
            cand.sort(key=lambda m: (abs(m - bass_center) * 1.0 + abs(m - prev_midi) * 0.7))
            bass_pitch = spell_in_chord(cand[0], chord, key)
        else:
            bass_pitch = chord.bass_pitch(2, key)

    upper_count = n - 1
    lo = max(style.low, bass_pitch.midi + 3)
    hi = style.high
    if soprano is not None:
        hi = min(hi, soprano.midi)

    # Candidate notes for the upper voices.
    pool: list[int] = [m for m in range(lo, hi + 1) if m % 12 in pcs]
    if len(pool) < upper_count:
        pool = list(range(lo, hi + 1))

    best: list[int] | None = None
    best_score = -1e9
    combos = itertools.combinations(pool, upper_count) if len(pool) <= 24 else \
        (tuple(sorted(rng.sample(pool, upper_count))) for _ in range(400))
    for combo in combos:
        voices = [bass_pitch.midi] + list(combo)
        if soprano is not None and voices[-1] != soprano.midi:
            continue
        score = _score_voicing(voices, chord, style, previous, prev_chord, key)
        if score > best_score:
            best_score, best = score, voices
    if best is None:
        best = [bass_pitch.midi] + sorted(pool)[:upper_count]
    return [bass_pitch if m == bass_pitch.midi else spell_in_chord(m, chord, key)
            for m in best]


def _score_voicing(voices: list[int], chord: Chord, style: VoicingStyle,
                   previous: list[Pitch] | None,
                   prev_chord: Chord | None = None, key: Key | None = None) -> float:
    s = 0.0
    pcs_present = {v % 12 for v in voices}
    required = set(chord.pcs)

    # Completeness: every chord tone should appear; the third is essential.
    missing = required - pcs_present
    s -= len(missing) * 6.0
    third_pc = (chord.root.pc + chord.intervals[1]) % 12 if len(chord.intervals) > 1 else None
    if third_pc is not None and third_pc in missing:
        s -= 8.0
    if chord.is_seventh:
        seventh = (chord.root.pc + chord.intervals[-1]) % 12
        if seventh in missing:
            s -= 7.0

    # Tessitura: the upper three voices belong in the middle of the range, not
    # packed just above the bass. Without this the opening chord sits muddy and
    # low, and every voice then has to leap upward into the next one.
    if len(voices) > 1:
        upper_mean = sum(voices[1:]) / (len(voices) - 1)
        target = style.low + (style.high - style.low) * 0.58
        s -= abs(upper_mean - target) * 0.42
        soprano_target = style.low + (style.high - style.low) * 0.80
        s -= abs(voices[-1] - soprano_target) * 0.22

    # Spacing: upper voices close, bass allowed to sit low.
    for i in range(1, len(voices) - 1):
        gap = voices[i + 1] - voices[i]
        if gap < 0:
            return -1e9
        if gap > style.max_spacing:
            s -= (gap - style.max_spacing) * 1.4
        if gap == 0:
            s -= 1.0
    if len(voices) > 1:
        if voices[1] - voices[0] > 19:
            s -= (voices[1] - voices[0] - 19) * 0.6
        if voices[-1] - voices[0] > style.max_span + 12:
            s -= 3.0

    # Doubling: prefer doubling the root, never the leading tone or the seventh.
    counts: dict[int, int] = {}
    for v in voices:
        counts[v % 12] = counts.get(v % 12, 0) + 1
    for pc, c in counts.items():
        if c > 1:
            if pc == chord.root.pc:
                s += 1.6 * style.double_root
            elif third_pc is not None and pc == third_pc:
                s -= 2.0
            elif chord.is_seventh and pc == (chord.root.pc + chord.intervals[-1]) % 12:
                s -= 4.0
            if c > 2:
                s -= 2.0

    if previous and len(previous) == len(voices):
        prev = [p.midi for p in previous]
        motion = sum(abs(a - b) for a, b in zip(voices, prev))
        s -= motion * 0.55
        common = sum(1 for a, b in zip(voices, prev) if a == b)
        s += common * style.keep_common_tone
        # Forbidden parallels between any pair of voices.
        for i in range(len(voices)):
            for j in range(i + 1, len(voices)):
                iv_now = (voices[j] - voices[i]) % 12
                iv_prev = (prev[j] - prev[i]) % 12
                if iv_now in (0, 7) and iv_now == iv_prev:
                    if voices[i] != prev[i] and voices[j] != prev[j]:
                        s -= 9.0
                # Direct (hidden) fifths/octaves into an outer-voice pair.
                if (i == 0 and j == len(voices) - 1 and iv_now in (0, 7)
                        and (voices[i] - prev[i]) * (voices[j] - prev[j]) > 0
                        and abs(voices[j] - prev[j]) > 2):
                    s -= 3.0
        # Voice crossing and overlap.
        for i in range(len(voices) - 1):
            if voices[i] > voices[i + 1]:
                s -= 8.0
        for i in range(1, len(voices)):
            if voices[i] < prev[i - 1] or (i + 1 < len(voices) and voices[i] > prev[i + 1]):
                s -= 1.0
        # A leap in an inner voice is more awkward than in the outer ones.
        for i in range(1, len(voices) - 1):
            if abs(voices[i] - prev[i]) > 4:
                s -= (abs(voices[i] - prev[i]) - 4) * 0.8

        # Tendency tones: a chordal seventh falls by step, a leading tone rises.
        if prev_chord is not None:
            if prev_chord.is_seventh:
                sev_pc = (prev_chord.root.pc + prev_chord.intervals[-1]) % 12
                for i, pm in enumerate(prev):
                    if pm % 12 != sev_pc:
                        continue
                    moved = voices[i] - pm
                    if moved in (-1, -2):
                        s += 4.5
                    elif moved == 0 and sev_pc in {v % 12 for v in voices}:
                        s += 1.0          # held over as a common tone
                    elif moved > 0:
                        s -= 9.0
            if key is not None and prev_chord.is_dominant_function:
                lt_pc = (key.tonic_pc - 1) % 12
                for i, pm in enumerate(prev):
                    if pm % 12 != lt_pc or i == 0:
                        continue
                    moved = voices[i] - pm
                    if moved == 1:
                        s += 3.5
                    elif moved < 0 and abs(moved) > 2:
                        s -= 2.0
    return s


def voice_progression(chords: list[Chord], key: Key, style: VoicingStyle | None = None,
                      soprano_line: list[Pitch] | None = None,
                      rng: random.Random | None = None) -> list[list[Pitch]]:
    """Voice a whole progression, carrying voice leading from chord to chord."""
    style = style or VoicingStyle()
    rng = rng or random.Random(0)
    out: list[list[Pitch]] = []
    prev: list[Pitch] | None = None
    for i, c in enumerate(chords):
        sop = soprano_line[i] if soprano_line and i < len(soprano_line) else None
        v = voice_chord(c, key, style, prev, soprano=sop, rng=rng,
                        prev_chord=chords[i - 1] if i else None)
        out.append(v)
        prev = v
    return out


def spread_voicing(chord: Chord, key: Key, low: int, high: int,
                   density: int = 4, shape: str = "open") -> list[Pitch]:
    """A pianistic voicing that ignores strict part writing — for textures."""
    pcs = list(chord.pcs)
    root_pc = chord.bass_pc
    notes: list[int] = []
    bass = next((m for m in range(low, low + 24) if m % 12 == root_pc), low)
    notes.append(bass)
    if shape == "open":
        order = [(chord.root.pc + i) % 12 for i in chord.intervals]
        m = bass + 7
        for pc in order[1:] + order[:1]:
            cand = next((x for x in range(m, min(high, m + 12) + 1) if x % 12 == pc), None)
            if cand is None:
                continue
            notes.append(cand)
            m = cand + 1
            if len(notes) >= density:
                break
    else:  # close position above the bass
        m = bass + 12
        while len(notes) < density and m <= high:
            if m % 12 in pcs:
                notes.append(m)
            m += 1
    notes = sorted(set(n for n in notes if low <= n <= high))
    return [key.spell(n) for n in notes]
