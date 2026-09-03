"""A compact text rendering of a score — for CLI output and plugin summaries."""
from __future__ import annotations

from ..score import DIVISIONS, Score

_GLYPH = {4.0: "𝅝", 3.0: "𝅗𝅥.", 2.0: "𝅗𝅥", 1.5: "♩.", 1.0: "♩",
          0.75: "♪.", 0.5: "♪", 0.25: "𝅘𝅥𝅯"}


def summarise(score: Score, max_bars: int = 8) -> str:
    lines = [f"{score.title}" + (f" — {score.subtitle}" if score.subtitle else ""),
             f"{score.key}, {score.time[0]}/{score.time[1]}, ♩ = {int(score.tempo)}",
             f"{len(score.parts)} part(s), {score.measure_count} bars", ""]
    part = score.parts[0] if score.parts else None
    if part is None:
        return "\n".join(lines)
    for m in part.measures[:max_bars]:
        voice = min(m.voices) if m.voices else None
        if voice is None:
            continue
        cells = []
        for n in m.voices[voice]:
            beats = n.duration / DIVISIONS
            g = _GLYPH.get(round(beats, 2), f"{beats:g}")
            name = "/".join(str(p) for p in n.pitches) if n.pitches else "rest"
            cells.append(f"{name}{'' if n.grace else ''}")
        lines.append(f"  {m.number:>3} | " + "  ".join(cells))
    if len(part.measures) > max_bars:
        lines.append(f"  ... {len(part.measures) - max_bars} more bars")
    return "\n".join(lines)
