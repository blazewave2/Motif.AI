"""Listening to a score that is already written.

When the musician asks Motif to continue or develop a piece, the composer
should work with *their* theme, not invent a new one. This module reads the
opening of the tune on the page — the top line of the first part — and turns
it into what the composer thinks in: a two-bar idea (rhythm, contour in
scale steps, the degree it starts on, the harmony it implies) and the
remembered bars themselves, so later phrases can restate, sequence and
fragment them.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F

from ..score import QUARTER, Score
from ..theory.pitch import Key
from .melody import MelNote, Motif, _scale_steps, implied_harmony, key_degree


@dataclass
class Theme:
    motif: Motif
    bars: list[list[MelNote]]      # the first bars of the tune, bar by bar
    key: Key


def _top_line(score: Score) -> list[tuple[F, F, int, int]]:
    """(onset, duration, midi, bar index) of the highest note of every event
    in the first part's upper staff, ties joined, rests left out."""
    part = score.parts[0] if score.parts else None
    if part is None:
        return []
    out: list[tuple[F, F, int, int]] = []
    t = F(0)
    time = tuple(score.time)
    for bi, m in enumerate(part.measures):
        if m.time:
            time = tuple(m.time)
        bar_len = F(time[0] * 4, time[1])
        staff1 = [v for v, notes in m.voices.items() if notes and notes[0].staff == 1] or \
            sorted(m.voices)[:1]
        voice = min(staff1) if staff1 else None
        pos = F(0)
        for n in (m.voices.get(voice, []) if voice is not None else []):
            if n.grace:
                continue
            d = F(n.duration, QUARTER)
            if not n.is_rest:
                top = max(p.midi for p in n.pitches)
                if n.tie_stop and out and out[-1][2] == top and out[-1][0] + out[-1][1] == t + pos:
                    on, dd, mm, b = out[-1]
                    out[-1] = (on, dd + d, mm, b)
                else:
                    out.append((t + pos, d, top, bi))
            pos += d
        t += max(bar_len, pos) if not m.implicit else pos
    return out


def theme_from_score(score: Score) -> Theme | None:
    """The opening idea of the tune on the page, or None if there is no tune."""
    line = _top_line(score)
    if len(line) < 3:
        return None
    key = score.key or Key("C", "major")
    time = tuple(score.time)
    bar_len = F(time[0] * 4, time[1])
    first_bar = line[0][3]
    bars: dict[int, list[tuple[F, F, int, int]]] = {}
    for ev in line:
        b = ev[3] - first_bar
        if b < 4:
            bars.setdefault(b, []).append(ev)
    b0 = [e for e in bars.get(0, [])]
    b1 = [e for e in bars.get(1, [])]
    if not b0:
        return None
    if not b1:
        b1 = b0
    rhythm = [min(e[1], bar_len) for e in b0]
    second = [min(e[1], bar_len) for e in b1]
    notes = b0 + b1
    steps = [_scale_steps(a[2], b[2], key) for a, b in zip(notes, notes[1:])]
    motif = Motif(rhythm=rhythm, steps=steps, anacrusis=[], second=second)
    _fit, start, bar2 = implied_harmony(motif, time)
    motif.start_degree = key_degree(notes[0][2], key)
    motif.bar2 = bar2
    memory: list[list[MelNote]] = []
    for b in range(4):
        evs = bars.get(b, [])
        memory.append([MelNote(on, d, midi) for on, d, midi, _ in evs])
    while memory and not memory[-1]:
        memory.pop()
    return Theme(motif, memory, key)
