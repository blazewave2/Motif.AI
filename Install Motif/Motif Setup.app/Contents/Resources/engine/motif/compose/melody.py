"""Melodic line generation.

The line is built in two passes.  First a *structural skeleton* places one
well-chosen chord tone per harmony, shaped by a registral contour; then the
remaining rhythmic slots are filled by a scored search that prefers stepwise
connection, resolves leaps, and treats dissonance the way a musician would
(passing, neighbour, appoggiatura, suspension).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ..score import Note, QUARTER, Tuplet
from ..theory.harmony import Chord
from ..theory.pitch import Key, Pitch
from .harmony_timeline import HarmonyTimeline
from .material import Contour, Motif


@dataclass
class MelodyStyle:
    """Knobs the style profiles turn to colour a line."""

    colours: tuple[str, ...] = ()      # extra scale collections to draw on
    colour_rate: float = 0.0

    leap_tolerance: float = 1.0        # >1 permits wider leaps
    chromaticism: float = 0.08         # chance of a chromatic approach note
    ornament_rate: float = 0.08
    step_preference: float = 1.0
    repeat_tolerance: float = 0.35
    appoggiatura_rate: float = 0.14
    suspension_rate: float = 0.12
    range_low: int = 55
    range_high: int = 84
    peak_uniqueness: float = 1.0       # penalise re-touching the phrase climax


METRIC_STRONG, METRIC_BEAT, METRIC_OFF, METRIC_WEAK = 3, 2, 1, 0


def metric_strength(tick: int, bar_ticks: int, beat_ticks: int) -> int:
    pos = tick % bar_ticks
    if pos == 0:
        return METRIC_STRONG
    if pos % beat_ticks == 0:
        # The half-bar point in duple meters is stronger than other beats.
        return METRIC_BEAT + (1 if bar_ticks % (beat_ticks * 2) == 0
                              and pos % (bar_ticks // 2) == 0 else 0) - 0
    if pos % (beat_ticks // 2 or 1) == 0:
        return METRIC_OFF
    return METRIC_WEAK


class MelodyWriter:
    def __init__(self, rng: random.Random, key: Key, style: MelodyStyle | None = None,
                 scale_variant: str | None = None):
        self.rng = rng
        self.key = key
        self.style = style or MelodyStyle()
        self.scale_variant = scale_variant or (
            "harmonic_minor" if key.is_minor else None)
        self._colour: set[int] | None = None

    # -- scale helpers ----------------------------------------------------
    def _scale_pcs(self, chord: Chord) -> set[int]:
        pcs = set(self.key.scale_pcs)
        if self.key.is_minor:
            pcs |= set(self.key.scale_pcs_for("harmonic_minor"))
            pcs |= set(self.key.scale_pcs_for("melodic_minor"))
        pcs |= set(chord.pcs)          # applied chords bring their own colour
        if self._colour is not None:
            pcs |= self._colour
        return pcs

    def recolour(self) -> None:
        """Pick the scale collection colouring the next phrase.

        A whole-tone or pentatonic phrase is what separates Debussy from a
        major scale with added ninths; the collection is chosen per phrase so
        the colour shifts rather than saturating the whole piece.
        """
        self._colour = None
        colours = self.style.colours
        if not colours or self.rng.random() >= self.style.colour_rate:
            return
        name = self.rng.choice(list(colours))
        # Transpose the collection onto a chord tone, not always the tonic, so
        # the colour floats the way it does in the repertoire.
        roots = [self.key.tonic_pc]
        roots += [(self.key.tonic_pc + i) % 12 for i in (5, 7)]
        root = self.rng.choice(roots)
        from ..theory.pitch import SCALE_INTERVALS
        intervals = SCALE_INTERVALS.get(name)
        if not intervals:
            return
        self._colour = {(root + i) % 12 for i in intervals}

    def _candidates(self, prev: Pitch | None, chord: Chord, lo: int, hi: int) -> list[Pitch]:
        pcs = self._scale_pcs(chord)
        out: list[Pitch] = []
        center = prev.midi if prev else (lo + hi) // 2
        for m in range(max(lo, center - 14), min(hi, center + 15) + 1):
            if m % 12 in pcs:
                out.append(self.key.spell(m))
        if not out:
            out = [self.key.spell(m) for m in range(lo, hi + 1)]
        return out

    # -- structural skeleton ---------------------------------------------
    def skeleton(self, timeline: HarmonyTimeline, contour: Contour,
                 center: int, amplitude: float = 7.0,
                 start_pitch: Pitch | None = None) -> dict[int, Pitch]:
        """One chord tone per harmony, tracing the contour with smooth motion."""
        targets: dict[int, Pitch] = {}
        prev: Pitch | None = start_pitch
        total = max(1, timeline.duration)
        for span in timeline.spans:
            t = (span.start - timeline.start) / total
            height = contour.at(t)
            want = center + height * amplitude
            tones = [p for p in self._chord_tones(span.chord,
                                                  self.style.range_low, self.style.range_high)]
            if not tones:
                continue
            best, best_score = tones[0], -1e9
            for p in tones:
                score = -abs(p.midi - want) * 1.0
                if prev is not None:
                    d = abs(p.midi - prev.midi)
                    score -= (0 if d <= 2 else (d - 2) * 0.75 / max(0.3, self.style.leap_tolerance))
                    if d == 0:
                        score -= 2.5
                if p.midi < self.style.range_low or p.midi > self.style.range_high:
                    score -= 25
                score += self.rng.uniform(-0.7, 0.7)
                if score > best_score:
                    best, best_score = p, score
            targets[span.start] = best
            prev = best
        return targets

    def _chord_tones(self, chord: Chord, lo: int, hi: int) -> list[Pitch]:
        pcs = set(chord.pcs)
        return [self.key.spell(m) for m in range(lo, hi + 1) if m % 12 in pcs]

    # -- main entry -------------------------------------------------------
    def write(self, timeline: HarmonyTimeline,
              rhythm: list[tuple[int, int, "Tuplet | None"]],
              contour: Contour, *, center: int = 72, amplitude: float = 7.0,
              bar_ticks: int = 1920, beat_ticks: int = QUARTER,
              motif: Motif | None = None, motif_positions: set[int] | None = None,
              motif_op: str = "develop",
              start_pitch: Pitch | None = None,
              cadence_pitch: Pitch | None = None) -> list[Note]:
        """Render a melody.  ``rhythm`` is (start_tick, duration, tuplet) triples.

        When a seed motif is given, the whole line is spun continuously from
        it — every phrase a developing variation of the last, the way a
        piece is actually built from a small number of cells rather than
        generated fresh note by note. A free harmonic search only ever
        supplies the final cadence note and, if no motif was given at all,
        the entire line (kept for callers with no thematic material).
        """
        if not rhythm:
            return []
        targets = self.skeleton(timeline, contour, center, amplitude, start_pitch)

        notes: list[Note] = []
        prev: Pitch | None = start_pitch
        prev_interval = 0
        peak_midi = -1
        motif_queue: list[Pitch] = []
        cur_motif = motif
        spins = 0

        for idx, (tick, dur, tup) in enumerate(rhythm):
            chord = timeline.at(tick)
            strength = metric_strength(tick, bar_ticks, beat_ticks)
            is_last = idx == len(rhythm) - 1

            if is_last and cadence_pitch is not None:
                pitch = cadence_pitch
            elif motif is not None:
                if not motif_queue:
                    # Only the very first statement anchors to the contour
                    # skeleton; every later one continues from the note that
                    # was actually just played. Re-anchoring to the skeleton
                    # on every refill fights the motif's own rising or
                    # falling shape and produces an artificial sawtooth —
                    # climb, snap back, climb again — instead of a line.
                    if spins == 0 or prev is None:
                        anchor = targets.get(tick) or self._nearest_target(targets, tick) or prev
                        anchor = anchor or self.key.degree_pitch(1, center // 12 - 1)
                    else:
                        anchor = prev
                        # Steer toward whichever direction the phrase needs
                        # next, so a steadily rising cell doesn't just climb
                        # forever (needing constant octave correction) once
                        # the contour should turn back down — a real
                        # composer picks the transformation that serves
                        # where the line is going, not a fixed shape on
                        # repeat.
                        base = cur_motif
                        nxt_target = self._next_target(targets, tick)
                        if nxt_target is not None and cur_motif.steps:
                            want_up = nxt_target[1].midi > prev.midi
                            is_up = sum(cur_motif.steps) >= 0
                            if want_up != is_up:
                                base = cur_motif.invert()
                        cur_motif = self._spin(base, motif_op)
                    spins += 1
                    realized = cur_motif.realize(self.key, anchor, self.scale_variant)
                    # Register correction moves the whole statement by an
                    # octave, keeping its shape exactly. It has to stay rare:
                    # a singer or a pianist leaps an octave to reposition a
                    # line once in a while, at the start of a phrase — not
                    # every couple of bars, which is just a line sawing up
                    # and down. So it waits for a bar line, and for real
                    # drift rather than a few notes of wandering.
                    target = targets.get(tick) or self._nearest_target(targets, tick)
                    at_bar = tick % bar_ticks == 0
                    if (target is not None and at_bar
                            and abs(realized[0].midi - target.midi) > 14):
                        shift = -12 if realized[0].midi > target.midi else 12
                        realized = [self.key.spell(p.midi + shift) for p in realized]
                    pitch = realized[0]
                    motif_queue = list(realized[1:])
                else:
                    pitch = motif_queue.pop(0)
                pitch = self._fit(pitch, chord, strength)
            else:
                pitch = self._choose(prev, prev_interval, chord, strength, tick, dur,
                                     targets, timeline, peak_midi)

            pitch = self._clamp(self._limit_leap(pitch, prev))
            note = Note([pitch], dur, velocity=self._velocity(strength))
            if tup is not None:
                note.tuplet = tup
            notes.append(note)
            if prev is not None:
                prev_interval = pitch.midi - prev.midi
            prev = pitch
            peak_midi = max(peak_midi, pitch.midi)
        return notes

    def _spin(self, motif: Motif, op: str) -> Motif:
        """The next statement in a developing-variation chain.

        Each refill grows out of the one before it — an evolving line, not
        the same four notes pasted end to end — while staying mild enough
        (a step of transposition, an inversion, a fragment) that it is still
        recognisably the same idea a few statements later.
        """
        # A fresh anchor is picked from the contour skeleton on every refill,
        # so restating the plain cell already reads as a melodic sequence —
        # the shape repeating at a new pitch level — without touching its
        # intervals at all. Only transformations that actually change
        # ``.steps`` belong here; a transposition applied to the motif
        # itself has nothing to act on once the anchor comes from outside it.
        pool = {
            "sequence": [lambda m: m, lambda m: m,
                        lambda m: m.fragment(0, max(2, m.length - 1))],
            "invert": [lambda m: m.invert(),
                      lambda m: m.invert().fragment(0, max(2, m.length - 1))],
            "fragment": [lambda m: m.fragment(0, max(2, m.length - 1))],
            "augment": [lambda m: m, lambda m: m.smooth()],
            "state": [lambda m: m],
            "recall": [lambda m: m],
        }.get(op, [lambda m: m.invert(),
                   lambda m: m.fragment(0, max(2, m.length - 1)),
                   lambda m: m.retrograde(),
                   lambda m: m.smooth(),
                   lambda m: m])
        return self.rng.choice(pool)(motif)

    # -- note choice ------------------------------------------------------
    def _choose(self, prev: Pitch | None, prev_interval: int, chord: Chord,
                strength: int, tick: int, dur: int, targets: dict[int, Pitch],
                timeline: HarmonyTimeline, peak_midi: int) -> Pitch:
        if tick in targets and strength >= METRIC_BEAT:
            return targets[tick]
        if prev is None:
            return targets.get(tick) or self._chord_tones(
                chord, self.style.range_low, self.style.range_high)[0]

        nxt = self._next_target(targets, tick)
        cands = self._candidates(prev, chord, self.style.range_low, self.style.range_high)
        chord_pcs = set(chord.pcs)
        scored: list[tuple[float, Pitch]] = []
        for p in cands:
            s = 0.0
            interval = p.midi - prev.midi
            a = abs(interval)

            # 1. Consonance against the prevailing harmony, weighted by metre.
            is_tone = p.pc in chord_pcs
            if is_tone:
                s += 2.0 + strength * 1.1
            else:
                s -= (strength ** 1.6) * 1.5
                if a <= 2:                       # a passing/neighbour tone is fine
                    s += 2.0
                else:
                    s -= 2.5
                if strength >= METRIC_BEAT and a <= 2:
                    s += self.style.appoggiatura_rate * 6.0   # deliberate appoggiatura

            # 2. Prefer conjunct motion; leaps must earn their place.
            if a == 0:
                s -= 3.5 * (1.0 - self.style.repeat_tolerance)
            elif a <= 2:
                s += 2.2 * self.style.step_preference
            elif a <= 4:
                s += 0.6
            else:
                s -= (a - 4) * 0.55 / max(0.35, self.style.leap_tolerance)
                if not is_tone:
                    s -= 3.0                      # never leap to a dissonance

            # 3. Recover from the previous leap by stepping back the other way.
            if abs(prev_interval) >= 5:
                if interval * prev_interval < 0 and a <= 3:
                    s += 3.0
                elif interval * prev_interval > 0 and a >= 3:
                    s -= 2.5

            # 4. Head toward the next structural note.
            if nxt is not None:
                gap = nxt[1].midi - p.midi
                dist_ticks = max(1, nxt[0] - tick)
                reachable = dist_ticks / max(1, dur)
                if abs(gap) > 2 * (reachable + 1):
                    s -= (abs(gap) - 2 * (reachable + 1)) * 0.35
                if 0 < abs(gap) <= 2:
                    s += 0.8

            # 5. Register discipline.
            if p.midi > self.style.range_high - 2 or p.midi < self.style.range_low + 2:
                s -= 2.0
            if peak_midi > 0 and p.midi >= peak_midi and strength < METRIC_BEAT:
                s -= 1.8 * self.style.peak_uniqueness   # keep the climax singular

            # 6. Leading-tone gravity.
            if self._is_leading_tone(p) and chord.is_dominant_function:
                s += 1.2

            s += self.rng.uniform(-0.55, 0.55)
            scored.append((s, p))

        scored.sort(key=lambda x: -x[0])
        top = scored[: max(1, min(4, len(scored)))]
        weights = [math.exp(s * 1.3) for s, _ in top]
        return self.rng.choices([p for _, p in top], weights=weights, k=1)[0]

    def _fit(self, pitch: Pitch, chord: Chord, strength: int) -> Pitch:
        """Nudge a motif note onto a chord tone when the metre demands it."""
        if strength < METRIC_BEAT or pitch.pc in set(chord.pcs):
            return pitch
        if self.rng.random() > 0.62:
            return pitch                      # keep some expressive dissonance
        for d in (0, -1, 1, -2, 2):
            m = pitch.midi + d
            if m % 12 in set(chord.pcs) and self.style.range_low <= m <= self.style.range_high:
                return self.key.spell(m)
        return pitch

    def _limit_leap(self, p: Pitch, prev: Pitch | None) -> Pitch:
        """Keep a melody singable: fold a wild jump back toward the last note.

        A transformed motif can ask for an interval no line would actually
        take — a tenth, a twelfth, two octaves — especially once inversions
        and expansions have compounded. Folding by octaves keeps the note's
        identity (its place in the harmony) and only fixes where it sits.
        """
        if prev is None:
            return p
        limit = int(round(9 + 5 * self.style.leap_tolerance))
        limit = max(7, min(16, limit))
        midi = p.midi
        while midi - prev.midi > limit and midi - 12 >= self.style.range_low:
            midi -= 12
        while prev.midi - midi > limit and midi + 12 <= self.style.range_high:
            midi += 12
        return p if midi == p.midi else self.key.spell(midi)

    def _clamp(self, p: Pitch) -> Pitch:
        m = p.midi
        while m > self.style.range_high:
            m -= 12
        while m < self.style.range_low:
            m += 12
        return p if m == p.midi else self.key.spell(m)

    def _is_leading_tone(self, p: Pitch) -> bool:
        return p.pc == (self.key.tonic_pc - 1) % 12

    def _velocity(self, strength: int) -> int:
        return {3: 84, 2: 78, 1: 72, 0: 68}.get(strength, 74)

    @staticmethod
    def _next_target(targets: dict[int, Pitch], tick: int) -> tuple[int, Pitch] | None:
        later = sorted(t for t in targets if t > tick)
        return (later[0], targets[later[0]]) if later else None

    @staticmethod
    def _nearest_target(targets: dict[int, Pitch], tick: int) -> Pitch | None:
        if not targets:
            return None
        k = min(targets, key=lambda t: abs(t - tick))
        return targets[k]


def flatten_rhythm(bars, start: int = 0) -> list[tuple[int, int, "Tuplet | None"]]:
    """Lay bars of rhythm end to end as (tick, duration, tuplet) triples.

    Accepts either plain durations or (duration, tuplet) pairs, so a caller
    that does not care about tuplets need not build them.
    """
    out: list[tuple[int, int, Tuplet | None]] = []
    t = start
    for bar in bars:
        for item in bar:
            if isinstance(item, tuple):
                d, tup = item
            else:
                d, tup = item, None
            out.append((t, d, tup))
            t += d
    return out
