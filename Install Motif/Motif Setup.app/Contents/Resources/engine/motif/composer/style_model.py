"""What real melodies do, learned from public-domain scores.

``training/learn_style.py`` counts, across more than a thousand songs and
quartets, which interval follows which, which scale degree follows which in
major and in minor, and which note value follows which. This module loads
those counts (a small JSON file shipped with Motif) and turns them into
costs the melody search adds to its own musical rules: the rules say what a
good line must do, the statistics say what real lines usually do, so the
composer's tunes move the way sung melodies move.

Every cost is relative to the most likely choice in its context, which
costs nothing, so the model only ever nudges.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).with_name("data") / "melody.json"


class MelodyModel:
    def __init__(self, data: dict):
        ivs = data["intervals"]
        self.lo, self.hi = ivs[0], ivs[-1]
        self.start = _relative(data["interval_start"])
        self.after = {int(k): _relative(v) for k, v in data["interval_after"].items()}
        self.degree = {mode: {int(k): _relative(v) for k, v in rows.items()}
                       for mode, rows in data["degree_after"].items()}
        self.strong = {mode: _relative(v) for mode, v in data["degree_strong"].items()}
        self.songs = data.get("songs", 0)

    def _clamp(self, iv: int) -> int:
        return max(self.lo, min(self.hi, iv))

    def interval_cost(self, prev_iv: int | None, iv: int) -> float:
        """How unusual interval ``iv`` is after ``prev_iv`` (in semitones)."""
        row = self.start if prev_iv is None else self.after.get(self._clamp(prev_iv), self.start)
        return row[self._clamp(iv) - self.lo]

    def degree_cost(self, minor: bool, prev_deg: int, deg: int) -> float:
        """How unusual it is to move from one chromatic scale degree to another."""
        rows = self.degree["minor" if minor else "major"]
        return rows[prev_deg % 12][deg % 12]

    def strong_cost(self, minor: bool, deg: int) -> float:
        """How unusual a scale degree is on a beat."""
        return self.strong["minor" if minor else "major"][deg % 12]


def _relative(logps: list[float]) -> list[float]:
    best = max(logps)
    return [round(best - x, 3) for x in logps]


@lru_cache(maxsize=1)
def melody_model() -> MelodyModel | None:
    """The shipped model, or None if the data file is missing (the composer
    then relies on its rules alone)."""
    try:
        return MelodyModel(json.loads(_DATA.read_text()))
    except (OSError, ValueError, KeyError):
        return None
