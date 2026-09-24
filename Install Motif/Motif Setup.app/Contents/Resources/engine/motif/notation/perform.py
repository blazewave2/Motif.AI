"""How a notated piece should *sound* — the playback a score implies.

The composer marks the page the way a composer does: *rit.* before a
cadence, *a tempo* after it, a hairpin across a phrase, *sfz* on one chord.
MuseScore plays printed dynamics and hairpins itself, but words like *rit.*
are just text to it, so the tempo map here turns them into invisible tempo
changes that ease in the way a player eases in. Per-note velocities follow
the same markings — interpolating through hairpins, treating *sf* and *fp*
as momentary rather than as new levels — and balance a melody over its
accompaniment the way a pianist voices the hands.
"""
from __future__ import annotations

import random
from fractions import Fraction

from ..score import DIVISIONS, Score, TempoMark

#: Momentary dynamics: an accent on one note, not a new level.
MOMENTARY = {"sf": 18, "sfz": 22, "sffz": 28, "fz": 20, "rf": 14, "rfz": 16}
LEVELS = {"pppp": 16, "ppp": 26, "pp": 38, "p": 52, "mp": 66, "mf": 80, "f": 95,
          "ff": 110, "fff": 120, "ffff": 126}
#: Attack-then-level dynamics: loud on the note, then the level that follows.
SPLIT = {"fp": ("f", "p"), "sfp": ("sf", "p"), "sfpp": ("sf", "pp"), "mfp": ("mf", "p")}


def _word_kind(text: str) -> tuple[str, float]:
    """Classify a tempo word: (kind, factor)."""
    t = text.lower()
    molto = "molto" in t
    poco = "poco" in t and "poco a poco" not in t
    if any(w in t for w in ("a tempo", "tempo i", "tempo primo", "tempo 1",
                            "come prima", "l'istesso")):
        return "reset", 1.0
    if "riten" in t:
        return "immediate", 0.85
    if any(w in t for w in ("rit", "rall", "slentando")):
        return "ramp", 0.72 if molto else 0.9 if poco else 0.8
    if "allarg" in t or "largamente" in t:
        return "ramp", 0.85
    if any(w in t for w in ("morendo", "smorz", "calando")):
        return "ramp", 0.82
    if any(w in t for w in ("accel", "string", "affrett", "incalz", "stretto")):
        return "ramp", 1.25 if molto else 1.08 if poco else 1.15
    if "animando" in t:
        return "ramp", 1.12
    if "più mosso" in t or "piu mosso" in t:
        return "immediate", 1.08 if poco else 1.15
    if any(w in t for w in ("meno mosso", "più lento", "piu lento")):
        return "immediate", 0.93 if poco else 0.87
    return "none", 1.0


def playback_tempos(bars, score: Score, words) -> list[TempoMark]:
    """Invisible tempo marks that realise *rit.*, *accel.*, *a tempo* and friends.

    ``bars`` are the builder's bar records (start, length, msn); ``words`` are
    (bar index, offset, text) triples in order.
    """
    if not bars or not words:
        return []
    starts = [b.start for b in bars]
    ends = [b.start + b.length for b in bars]
    piece_end = ends[-1]

    visible = sorted(((starts[_bar_index_of(bars, t.measure)] + Fraction(t.offset, DIVISIONS),
                       t.quarter_bpm) for t in score.tempos if t.visible),
                     key=lambda x: x[0])
    first_tempo = visible[0][1] if visible else score.tempo

    def base_at(pos: Fraction) -> float:
        cur = first_tempo
        for p, bpm in visible:
            if p <= pos:
                cur = bpm
        return cur

    events = []
    for bi, off, text in words:
        events.append((bars[bi].start + off, text))
    events.sort(key=lambda e: e[0])
    event_positions = [p for p, _ in events] + [p for p, _ in visible]

    out: list[TempoMark] = []
    current = first_tempo
    last_visible_pos = Fraction(-1)
    for pos, text in events:
        # A printed tempo since the last word resets what we are bending.
        for p, bpm in visible:
            if last_visible_pos < p <= pos:
                current = bpm
                last_visible_pos = p
        kind, factor = _word_kind(text)
        if kind == "none":
            continue
        if kind == "reset":
            target = first_tempo if "tempo i" in text.lower() or "primo" in text.lower() \
                else base_at(pos)
            if abs(target - current) > 0.5:
                out.append(_mark(bars, pos, target))
            current = target
            continue
        if kind == "immediate":
            current = current * factor
            out.append(_mark(bars, pos, current))
            continue
        # A gradual change runs until the next instruction, and for no more
        # than two bars — after that the new tempo simply holds.
        later = [p for p in event_positions if p > pos]
        span_end = min([piece_end] + later)
        bar_i = _bar_at(starts, pos)
        two_bars = ends[min(len(ends) - 1, bar_i + 1)]
        span_end = min(span_end, max(two_bars, pos + Fraction(2)))
        if span_end <= pos:
            continue
        start_tempo = current
        target = start_tempo * factor
        step = Fraction(1, 2) if span_end - pos <= 2 else Fraction(1)
        t = pos
        while t < span_end:
            frac = float((t - pos + step) / (span_end - pos))
            frac = min(1.0, frac)
            eased = frac ** 1.4 if factor < 1 else frac ** 0.9
            bpm = start_tempo + (target - start_tempo) * eased
            out.append(_mark(bars, t, bpm))
            t += step
        current = target
    return out


def _bar_index_of(bars, measure_number: int) -> int:
    for i, b in enumerate(bars):
        if b.msn.number == measure_number:
            return i
    return 0


def _bar_at(starts: list[Fraction], pos: Fraction) -> int:
    idx = 0
    for i, s in enumerate(starts):
        if s <= pos:
            idx = i
    return idx


def _mark(bars, pos: Fraction, bpm: float) -> TempoMark:
    starts = [b.start for b in bars]
    i = _bar_at(starts, pos)
    offset = int(round((pos - bars[i].start) * DIVISIONS))
    return TempoMark(bars[i].msn.number, round(max(20.0, min(300.0, bpm)), 2),
                     "quarter", "", False, offset=offset, visible=False)


# ---------------------------------------------------------------------------
# velocities
# ---------------------------------------------------------------------------
def shape_velocities(score: Score, seed: int = 0) -> None:
    """Give every note a velocity that follows the page's dynamics."""
    rng = random.Random(seed or 1)
    starts = _measure_starts(score)
    for part in score.parts:
        levels, momentary, wedges = _dynamic_events(part, starts)
        keyboard = part.staves >= 2
        for mi, m in enumerate(part.measures):
            base_tick = starts[mi] if mi < len(starts) else 0
            bar_len = _measure_length(m)
            for voice, notes in m.voices.items():
                t = 0
                for n in notes:
                    if n.grace:
                        n.velocity = _clamp(_level_at(levels, wedges, base_tick + t) - 12)
                        continue
                    if n.is_rest:
                        t += n.duration
                        continue
                    abs_t = base_tick + t
                    v = _level_at(levels, wedges, abs_t)
                    v += momentary.get((abs_t, n.staff), momentary.get((abs_t, 0), 0))
                    if keyboard:
                        if n.staff >= 2:
                            v -= 7
                        elif voice % 4 != 1:
                            v -= 4
                        else:
                            v += 4
                    pos = t % bar_len if bar_len else t
                    if pos == 0:
                        v += 4
                    elif pos % DIVISIONS == 0:
                        v += 1
                    else:
                        v -= 2
                    if "accent" in n.articulations:
                        v += 10
                    if "strong-accent" in n.articulations:
                        v += 14
                    if "staccato" in n.articulations or "staccatissimo" in n.articulations:
                        v -= 2
                    if "tenuto" in n.articulations:
                        v += 2
                    v += rng.gauss(0, 1.8)
                    n.velocity = _clamp(v)
                    t += n.duration


def _measure_starts(score: Score) -> list[int]:
    if not score.parts:
        return []
    out, t = [], 0
    for m in score.parts[0].measures:
        out.append(t)
        t += _measure_length(m)
    return out


def _measure_length(m) -> int:
    return max((sum(n.duration for n in notes if not n.grace)
                for notes in m.voices.values()), default=0)


def _dynamic_events(part, starts):
    """Level changes, momentary accents and hairpin spans for one part."""
    levels: list[tuple[int, float]] = []
    momentary: dict[tuple[int, int], float] = {}
    open_w: dict[int, tuple[int, str]] = {}
    spans: list[list] = []                    # [start, stop, kind, from, to]
    for mi, m in enumerate(part.measures):
        base = starts[mi] if mi < len(starts) else 0
        for d in sorted(m.directions, key=lambda d: d.offset):
            tick = base + d.offset
            if d.kind == "dynamics":
                v = d.value
                if v in SPLIT:
                    hit, after = SPLIT[v]
                    momentary[(tick, 0)] = LEVELS.get(hit, MOMENTARY.get(hit, 0) + 80) - \
                        LEVELS.get(after, 52)
                    levels.append((tick, float(LEVELS[after])))
                elif v in MOMENTARY:
                    momentary[(tick, 0)] = MOMENTARY[v]
                elif v in LEVELS:
                    levels.append((tick, float(LEVELS[v])))
            elif d.kind == "wedge":
                number = d.extra.get("number", 1)
                if d.value in ("crescendo", "diminuendo"):
                    open_w[number] = (tick, d.value)
                elif d.value == "stop" and number in open_w:
                    start, kind = open_w.pop(number)
                    spans.append([start, max(start + 1, tick), kind, None, None])
    levels.sort()
    wedges = []
    for start, stop, kind, _, _ in spans:
        before = _plain_level(levels, start)
        after = next((v for t, v in levels if stop - DIVISIONS <= t <= stop + DIVISIONS),
                     None)
        if after is None or (kind == "crescendo" and after <= before) or \
                (kind == "diminuendo" and after >= before):
            after = before + (14 if kind == "crescendo" else -14)
        wedges.append((start, stop, before, max(20.0, min(122.0, after))))
    return levels, momentary, wedges


def _plain_level(levels, tick: int) -> float:
    cur = 80.0
    for t, v in levels:
        if t <= tick:
            cur = v
        else:
            break
    return cur


def _level_at(levels, wedges, tick: int) -> float:
    base = _plain_level(levels, tick)
    for start, stop, before, after in wedges:
        if start <= tick <= stop:
            frac = (tick - start) / max(1, stop - start)
            return before + (after - before) * frac
    # After a hairpin with no dynamic to land on, the new level holds.
    last = None
    for start, stop, before, after in wedges:
        if stop < tick and not any(stop < t <= tick for t, _ in levels):
            last = after
    return last if last is not None else base


def _clamp(v: float) -> int:
    return int(max(12, min(126, round(v))))
