"""Turning flat streams of notes into properly barred measures.

Notes that straddle a barline are split and tied; notes that obscure the beat
inside a bar are split and tied too.  This is the difference between a score
that reads and a score that is merely correct.
"""
from __future__ import annotations

from ..score import Direction, Note, Part, split_duration


def place_voice(part: Part, notes: list[Note], *, start_tick: int, bar_ticks: int,
                beat_ticks: int, voice: int, staff: int,
                time_map: dict[int, tuple[int, int]] | None = None) -> int:
    """Write a sequential stream of notes into ``part``, barring as we go.

    Returns the tick position just after the last note.
    """
    t = start_tick
    for note in notes:
        if note.grace:
            m_index = t // bar_ticks + 1
            m = part.measure(m_index)
            g = note.copy()
            g.voice, g.staff = voice, staff
            m.add(g)
            continue
        remaining = note.duration
        first = True
        while remaining > 0:
            bar_index = t // bar_ticks
            offset = t - bar_index * bar_ticks
            room = bar_ticks - offset
            take = min(remaining, room)
            pieces = split_duration(take, offset, beat_ticks, bar_ticks)
            m = part.measure(bar_index + 1)
            for pi, d in enumerate(pieces):
                seg = note.copy()
                seg.duration = d
                seg.voice, seg.staff = voice, staff
                last_piece = (pi == len(pieces) - 1) and (take == remaining)
                if not first or pi > 0:
                    seg.tie_stop = True
                    seg.slur_start = 0
                    seg.articulations = []
                    seg.ornaments = []
                    seg.grace = False
                    seg.chord_symbol = None
                if not last_piece:
                    seg.tie_start = True
                    seg.slur_stop = 0
                    seg.fermata = False
                if seg.is_rest:
                    seg.tie_start = seg.tie_stop = False
                m.add(seg)
                t += d
                first = False
            remaining -= take
    return t


def place_direction(part: Part, d: Direction, tick: int, bar_ticks: int) -> None:
    bar_index = tick // bar_ticks
    m = part.measure(bar_index + 1)
    dd = Direction(d.kind, d.value, tick - bar_index * bar_ticks, d.staff,
                   d.placement, d.voice, dict(d.extra))
    m.directions.append(dd)


def fill_empty_measures(part: Part, bar_ticks: int, voices: list[tuple[int, int]]) -> None:
    """Give every measure a full-bar rest in any voice that has nothing."""
    for m in part.measures:
        for voice, staff in voices:
            have = sum(n.duration for n in m.voices.get(voice, []) if not n.grace)
            if have == 0:
                m.voices.setdefault(voice, []).insert(
                    0, Note([], bar_ticks, voice=voice, staff=staff))
            elif have < bar_ticks:
                m.voices[voice].append(
                    Note([], bar_ticks - have, voice=voice, staff=staff))


def merge_tied_rests(part: Part) -> None:
    """Collapse consecutive rests in a voice into one where the metre allows."""
    for m in part.measures:
        for voice, notes in m.voices.items():
            out: list[Note] = []
            for n in notes:
                if (out and n.is_rest and out[-1].is_rest and not n.grace
                        and not out[-1].grace):
                    out[-1].duration += n.duration
                else:
                    out.append(n)
            m.voices[voice] = out
