"""A tick-indexed view of a chord progression."""
from __future__ import annotations

from dataclasses import dataclass

from ..score import DIVISIONS
from ..theory.harmony import Chord


@dataclass
class Span:
    start: int
    end: int
    chord: Chord

    @property
    def duration(self) -> int:
        return self.end - self.start


class HarmonyTimeline:
    """Maps ticks to the chord sounding at that moment."""

    def __init__(self, chords: list[Chord], start: int = 0):
        self.spans: list[Span] = []
        t = start
        for c in chords:
            d = max(1, int(round(c.duration * DIVISIONS)))
            self.spans.append(Span(t, t + d, c))
            t += d
        self.end = t
        self.start = start

    @property
    def duration(self) -> int:
        return self.end - self.start

    def at(self, tick: int) -> Chord:
        for s in self.spans:
            if s.start <= tick < s.end:
                return s.chord
        return self.spans[-1].chord if self.spans else Chord.__new__(Chord)

    def span_at(self, tick: int) -> Span:
        for s in self.spans:
            if s.start <= tick < s.end:
                return s
        return self.spans[-1]

    def next_change(self, tick: int) -> int:
        for s in self.spans:
            if s.start > tick:
                return s.start
        return self.end

    def is_change(self, tick: int) -> bool:
        return any(s.start == tick for s in self.spans)

    def shifted(self, offset: int) -> "HarmonyTimeline":
        tl = HarmonyTimeline([], self.start + offset)
        tl.spans = [Span(s.start + offset, s.end + offset, s.chord) for s in self.spans]
        tl.end = self.end + offset
        return tl
