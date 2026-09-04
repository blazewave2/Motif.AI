"""Automatic beaming.

MusicXML leaves grouping eighth notes (and shorter) into beams entirely to
each note's own ``<beam>`` elements — nothing does this for free, and nothing
upstream of this module ever set them. Left unbeamed, every eighth note and
sixteenth prints as an isolated flagged note, which reads as amateurish no
matter how good the pitches are. This assigns beam levels the way an
engraver would: grouped within each metrical beat, broken at rests, longer
notes and beat boundaries, with a hook for a lone shorter note against a
longer neighbour (as in a dotted-eighth-sixteenth pair).
"""
from __future__ import annotations

from ..score import Note, Part, beat_duration, note_type_and_dots

_LEVELS = {"eighth": 1, "16th": 2, "32nd": 3, "64th": 4, "128th": 5}


def apply_beams(part: Part, default_time: tuple[int, int]) -> None:
    """Assign ``note.beam`` for every voice in every measure of ``part``.

    Recomputing from scratch (rather than trusting whatever a note already
    carries) means this is safe to re-run over a whole score after merging
    in continued material, even though the reader that parses an existing
    file back in never restores beam info of its own.
    """
    time = default_time
    for m in part.measures:
        if m.time is not None:
            time = m.time
        beat_ticks = beat_duration(time)
        for notes in m.voices.values():
            _beam_voice(notes, beat_ticks)


def _beam_voice(notes: list[Note], beat_ticks: int) -> None:
    group: list[Note] = []
    group_beat = -1
    t = 0

    def flush() -> None:
        if len(group) >= 2:
            _assign_group(group)
        group.clear()

    for n in notes:
        if n.grace:
            continue
        level = _level(n)
        if level == 0:
            flush()
        else:
            beat_idx = t // beat_ticks
            if group and beat_idx != group_beat:
                flush()
            if not group:
                group_beat = beat_idx
            group.append(n)
        t += n.duration
    flush()


def _display_ticks(n: Note) -> int:
    if n.tuplet is not None:
        return int(round(n.duration * n.tuplet.actual / n.tuplet.normal))
    return n.duration


def _level(n: Note) -> int:
    """How many beam lines this note's own type carries — 0 means unbeamable."""
    if n.is_rest or n.grace:
        return 0
    ntype, _ = note_type_and_dots(_display_ticks(n))
    return _LEVELS.get(ntype, 0)


def _assign_group(group: list[Note]) -> None:
    for n in group:
        n.beam = []
    levels = [_level(n) for n in group]
    max_level = max(levels)
    for lvl in range(1, max_level + 1):
        active = [i for i, lv in enumerate(levels) if lv >= lvl]
        for run in _runs(active):
            if len(run) >= 2:
                for pos, i in enumerate(run):
                    kind = "begin" if pos == 0 else "end" if pos == len(run) - 1 else "continue"
                    group[i].beam.append(kind)
            else:
                i = run[0]
                # A lone shorter note hooks toward whichever neighbour it has:
                # forward if it opens the group, backward otherwise — the
                # textbook dotted-eighth/sixteenth pairing either way round.
                group[i].beam.append("forward hook" if i == 0 else "backward hook")


def _runs(indices: list[int]) -> list[list[int]]:
    runs: list[list[int]] = []
    cur: list[int] = []
    for i in indices:
        if cur and i != cur[-1] + 1:
            runs.append(cur)
            cur = []
        cur.append(i)
    if cur:
        runs.append(cur)
    return runs
