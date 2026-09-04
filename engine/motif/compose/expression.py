"""Performance shaping — the layer that makes a score sound played, not printed.

Three things separate a human performance from a metronome: the tempo breathes,
the volume moves continuously rather than in steps, and the accompaniment sits
behind the melody instead of beside it.  All three are applied here, after the
notes exist, so the musical structure stays intact.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from ..plan import SectionPlan
from ..score import Direction, Note, QUARTER, TempoMark
from .styles import StyleProfile

DYN_VELOCITY = {"ppp": 26, "pp": 38, "p": 52, "mp": 66, "mf": 80,
                "f": 95, "ff": 110, "fff": 122}
DYN_ORDER = ["ppp", "pp", "p", "mp", "mf", "f", "ff", "fff"]

#: How freely each style is played.  Bach is nearly metronomic; Chopin,
#: Rachmaninov and Liszt are anything but.
RUBATO: dict[str, float] = {
    "bach": 0.03, "handel": 0.04, "scarlatti": 0.04, "vivaldi": 0.04,
    "mozart": 0.06, "haydn": 0.06, "clementi": 0.05,
    "beethoven": 0.11, "schubert": 0.12, "mendelssohn": 0.09,
    "brahms": 0.14, "grieg": 0.11, "tchaikovsky": 0.15,
    "chopin": 0.20, "liszt": 0.22, "rachmaninoff": 0.21, "scriabin": 0.19,
    "debussy": 0.16, "ravel": 0.13, "satie": 0.07,
    "einaudi": 0.08, "film": 0.10, "classical": 0.07,
}

#: Words a performer would actually see on the page.
RIT_WORDS = ["rit.", "poco rit.", "ritardando", "cedendo", "allargando"]
ACCEL_WORDS = ["accel.", "poco accel.", "stringendo", "animando", "più mosso"]


@dataclass
class Phrase:
    """One breath of music, used to shape both tempo and volume."""

    start: int
    end: int
    peak: int
    energy: float = 0.5
    cadential: bool = False

    @property
    def length(self) -> int:
        return max(1, self.end - self.start)

    def position(self, tick: int) -> float:
        return max(0.0, min(1.0, (tick - self.start) / self.length))


def detect_phrases(notes: list[Note], start: int, bar_ticks: int,
                   section_bars: int, energy: float) -> list[Phrase]:
    """Split a section into musical phrases.

    Slurs mark legato groups, which are usually shorter than a phrase, so
    adjacent groups are merged until they reach a period's length.  Shaping
    every slur instead would put a hairpin under every bar and a swell on
    every gesture — the opposite of phrasing.
    """
    if not notes:
        return []
    stops: list[int] = []
    t = start
    for n in notes:
        if n.grace:
            continue
        t += n.duration
        if n.slur_stop:
            stops.append(t)
    end = t
    if end <= start:
        return []

    target = bar_ticks * (4 if section_bars >= 8 else 2)
    # Merge slur ends into phrase-sized spans; fall back to a regular period
    # when the line carries too few slurs to read.
    boundaries: list[int] = []
    anchor = start
    for stop in stops:
        if stop - anchor >= target * 0.75:
            boundaries.append(stop)
            anchor = stop
    if not boundaries:
        step = target
        b = start + step
        while b < end - step * 0.4:
            boundaries.append(b)
            b += step
    if not boundaries or boundaries[-1] < end:
        boundaries.append(end)

    phrases: list[Phrase] = []
    prev = start
    for i, b in enumerate(boundaries):
        if b - prev < bar_ticks:
            continue
        peak = prev + int((b - prev) * 0.62)
        phrases.append(Phrase(prev, b, peak, energy, cadential=(i == len(boundaries) - 1)))
        prev = b
    if not phrases:
        phrases = [Phrase(start, end, start + int((end - start) * 0.62), energy, True)]
    return phrases


class ExpressionPlanner:
    """Applies tempo, dynamics and balance once the notes are written."""

    def __init__(self, rng: random.Random, style: StyleProfile, base_tempo: float):
        self.rng = rng
        self.style = style
        self.base_tempo = base_tempo
        self.rubato = RUBATO.get(style.name, 0.08)

    # -- tempo ------------------------------------------------------------
    def tempo_marks(self, sections: list[SectionPlan], bar_offsets: list[int],
                    bar_ticks: int) -> list[TempoMark]:
        """A tempo map with real give and take between the sections."""
        out: list[TempoMark] = []
        r = self.rubato
        # The opening tempo is always stated; only the give and take is
        # stylistic. A Baroque movement holds its pulse but still has a tempo.
        out.append(TempoMark(1, round(self.base_tempo, 1)))
        if r < 0.05:
            if sections:
                total = bar_offsets[-1] + sections[-1].bars
                out.append(TempoMark(max(1, total - 1),
                                     round(self.base_tempo * 0.94, 1), text="rit."))
            return out

        for sec, first_bar in zip(sections, bar_offsets):
            tempo = self.base_tempo * sec.tempo_scale
            # Lyrical middles relax; developments and codas press forward.
            if sec.role in ("theme",) and sec.energy < 0.45:
                tempo *= 1.0 - r * 0.45
            elif sec.role in ("development", "transition"):
                tempo *= 1.0 + r * 0.35
            elif sec.role == "cadenza":
                tempo *= 1.0 + r * 0.15
            elif sec.role == "coda":
                tempo *= 1.0 - r * 0.25

            if sec.bars >= 4 and first_bar > 0:
                word = self._section_word(sec, tempo)
                out.append(TempoMark(first_bar + 1, round(tempo, 1), text=word))
            elif first_bar == 0:
                out[0] = TempoMark(1, round(tempo, 1))

            # Ease into the cadence, then restore.
            if sec.bars >= 6 and r >= 0.08:
                rit_bar = first_bar + sec.bars - 2
                out.append(TempoMark(rit_bar + 1, round(tempo * (1 - r * 0.9), 1),
                                     text=self.rng.choice(RIT_WORDS)))
                if sec is not sections[-1]:
                    out.append(TempoMark(first_bar + sec.bars + 1,
                                         round(tempo, 1), text="a tempo"))

            # Press toward the high point of an intense section.
            if sec.energy > 0.7 and sec.bars >= 8 and r >= 0.1:
                out.append(TempoMark(first_bar + max(2, sec.bars // 3) + 1,
                                     round(tempo * (1 + r * 0.5), 1),
                                     text=self.rng.choice(ACCEL_WORDS)))

        # Every piece slows into its last bars.
        if sections and r >= 0.06:
            last_start = bar_offsets[-1]
            total = last_start + sections[-1].bars
            out.append(TempoMark(max(1, total - 1),
                                 round(self.base_tempo * (1 - r * 1.6), 1),
                                 text="rall." if r > 0.12 else "poco rit."))
        out.sort(key=lambda t: t.measure)
        deduped: list[TempoMark] = []
        for t in out:
            if deduped and deduped[-1].measure == t.measure:
                deduped[-1] = t
            else:
                deduped.append(t)
        return deduped

    def _section_word(self, sec: SectionPlan, tempo: float) -> str:
        if tempo > self.base_tempo * 1.06:
            return self.rng.choice(["più mosso", "animato", "poco più mosso"])
        if tempo < self.base_tempo * 0.94:
            return self.rng.choice(["meno mosso", "poco meno mosso", "tranquillo"])
        return ""

    # -- dynamics ---------------------------------------------------------
    def shape(self, notes: list[Note], phrases: list[Phrase], start: int, *,
              bar_ticks: int, beat_ticks: int, base: str, melody: bool = True,
              lead_offset: int = 0) -> None:
        """Give every note its own velocity.

        Volume in a performance is continuous: it follows the phrase, the
        contour and the metre together.  Stepping between eight printed marks
        is what makes playback sound typed rather than played.
        """
        if not notes:
            return
        centre = DYN_VELOCITY.get(base, 80) + lead_offset
        volatility = 0.55 + self.style.dynamic_volatility * 0.9

        pitched = [n for n in notes if n.pitches and not n.grace]
        if pitched:
            highs = [max(p.midi for p in n.pitches) for n in pitched]
            lo, hi = min(highs), max(highs)
            span = max(6, hi - lo)
        else:
            lo, span = 60, 12

        t = start
        for n in notes:
            if n.grace:
                n.velocity = self._clamp(centre - 14 + self.rng.randint(-3, 3))
                continue
            if not n.pitches:
                t += n.duration
                continue

            v = float(centre)
            phrase = self._phrase_at(phrases, t)

            # 1. The phrase arch: a swell toward its high point, easing after.
            if phrase is not None:
                pos = phrase.position(t)
                peak = phrase.position(phrase.peak) or 0.62
                arc = (pos / peak) if pos <= peak else (1 - (pos - peak) / max(0.05, 1 - peak))
                v += (arc - 0.45) * 13.0 * volatility
                # Phrase endings taper.
                if pos > 0.9 and phrase.cadential:
                    v -= 6.0 * volatility

            # 2. Register: a rising line naturally grows.
            top = max(p.midi for p in n.pitches)
            v += ((top - lo) / span - 0.5) * 9.0 * volatility

            # 3. Metre.
            pos_in_bar = (t - start) % bar_ticks
            if pos_in_bar == 0:
                v += 5.0
            elif beat_ticks and pos_in_bar % beat_ticks == 0:
                v += 1.5
            elif beat_ticks and pos_in_bar % max(1, beat_ticks // 2) == 0:
                v -= 1.5
            else:
                v -= 3.5

            # 4. Longer notes carry more weight; a chord sounds fuller.
            if n.duration >= beat_ticks * 2:
                v += 3.0
            if len(n.pitches) > 2:
                v += 2.0

            # 5. Marked articulation.
            if "accent" in n.articulations:
                v += 9.0
            if "strong-accent" in n.articulations:
                v += 14.0
            if "staccato" in n.articulations:
                v -= 2.0
            if "tenuto" in n.articulations:
                v += 2.5

            # 6. The unevenness of a real hand.
            v += self.rng.gauss(0, 2.2)

            n.velocity = self._clamp(v)
            t += n.duration

    def _phrase_at(self, phrases: list[Phrase], tick: int) -> Phrase | None:
        for p in phrases:
            if p.start <= tick < p.end:
                return p
        return phrases[-1] if phrases else None

    @staticmethod
    def _clamp(v: float) -> int:
        return int(max(12, min(126, round(v))))

    # -- hairpins ---------------------------------------------------------
    def hairpins(self, phrases: list[Phrase], base: str, staff: int = 1,
                 wedge_id_start: int = 1, bar_ticks: int = QUARTER * 4
                 ) -> list[tuple[int, Direction]]:
        """A swell and a fall over each phrase, as an editor would mark it."""
        out: list[tuple[int, Direction]] = []
        if self.style.dynamic_volatility < 0.3 or not phrases:
            return out
        n = wedge_id_start
        shortest = max(QUARTER * 3, int(bar_ticks * 1.5))
        # Marking every phrase the same way is its own kind of mechanical, so
        # some phrases swell, some fall away, and some are simply left alone.
        chance = 0.45 + self.style.dynamic_volatility * 0.45
        for ph in phrases:
            if ph.length < shortest:
                continue
            if not ph.cadential and self.rng.random() > chance:
                continue
            roll = self.rng.random()
            shape = "both" if roll < 0.5 else ("grow" if roll < 0.78 else "fade")
            if ph.cadential:
                shape = "fade" if self.rng.random() < 0.6 else "both"

            if shape in ("both", "grow"):
                out.append((ph.start, Direction("wedge", "crescendo", 0, staff,
                                                "below", extra={"number": n})))
                out.append((ph.peak, Direction("wedge", "stop", 0, staff, "below",
                                               extra={"number": n})))
                n = n % 6 + 1
            if shape in ("both", "fade") and ph.end - ph.peak > bar_ticks:
                out.append((ph.peak, Direction("wedge", "diminuendo", 0, staff,
                                               "below", extra={"number": n})))
                out.append((max(ph.peak + QUARTER, ph.end - 1),
                            Direction("wedge", "stop", 0, staff, "below",
                                      extra={"number": n})))
                n = n % 6 + 1
        return out


def shift_dynamic(mark: str, steps: int) -> str:
    try:
        i = DYN_ORDER.index(mark)
    except ValueError:
        i = 4
    return DYN_ORDER[max(0, min(len(DYN_ORDER) - 1, i + steps))]
