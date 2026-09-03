"""Accompaniment textures.

A Chopin nocturne and a Mozart sonata can share a chord progression and sound
nothing alike; the difference is texture.  Each function here renders one
idiomatic left-hand (or inner-voice) pattern across a harmonic timeline.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..score import (DIVISIONS, EIGHTH, HALF, Note, QUARTER, SIXTEENTH,
                     THIRTYSECOND, WHOLE, split_duration)
from ..theory.harmony import Chord
from ..theory.pitch import Key, Pitch
from .harmony_timeline import HarmonyTimeline, Span
from .voicing import spell_in_chord, spread_voicing


@dataclass
class TextureContext:
    timeline: HarmonyTimeline
    key: Key
    rng: random.Random
    bar_ticks: int = WHOLE
    beat_ticks: int = QUARTER
    low: int = 36
    high: int = 64
    staff: int = 2
    voice: int = 5
    density: float = 0.5
    style: str = "classical"
    dynamic: float = 0.5           # 0..1, drives velocity
    hand_span: int = 14            # semitones a hand can stretch
    pedal: bool = True
    extra: dict = field(default_factory=dict)

    @property
    def center(self) -> int:
        return (self.low + self.high) // 2

    def note(self, pitches, dur, **kw) -> Note:
        kw.setdefault("voice", self.voice)
        kw.setdefault("staff", self.staff)
        kw.setdefault("velocity", int(48 + self.dynamic * 46))
        return Note(list(pitches), dur, **kw)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _tones(chord: Chord, key: Key, low: int, high: int) -> list[Pitch]:
    pcs = set(chord.pcs)
    return [spell_in_chord(m, chord, key) for m in range(low, high + 1) if m % 12 in pcs]


def _bass(chord: Chord, key: Key, low: int, high: int) -> Pitch:
    pc = chord.bass_pc
    cands = [m for m in range(low, high + 1) if m % 12 == pc]
    if not cands:
        return chord.bass_pitch(low // 12 - 1, key)
    target = low + 5
    cands.sort(key=lambda m: abs(m - target))
    return spell_in_chord(cands[0], chord, key)


def _stack(chord: Chord, key: Key, above: Pitch, count: int, max_span: int) -> list[Pitch]:
    """Chord tones climbing from ``above``, strictly inside ``max_span`` semitones.

    Callers index this with a modulo, so returning a short list is correct: the
    figure cycles within the hand instead of walking off the top of the staff.
    """
    out: list[Pitch] = []
    m = above.midi + 1
    limit = above.midi + max_span
    pcs = set(chord.pcs)
    while len(out) < count and m <= limit:
        if m % 12 in pcs:
            out.append(spell_in_chord(m, chord, key))
        m += 1
    return out or [above]


def _spans_in_bars(ctx: TextureContext):
    """Yield (bar_start, bar_end) pairs over the timeline."""
    t = ctx.timeline.start
    while t < ctx.timeline.end:
        yield t, min(t + ctx.bar_ticks, ctx.timeline.end)
        t += ctx.bar_ticks


def _subdivide(span_start: int, span_end: int, unit: int) -> list[tuple[int, int]]:
    out, t = [], span_start
    while t < span_end:
        d = min(unit, span_end - t)
        out.append((t, d))
        t += d
    return out


# ---------------------------------------------------------------------------
# textures
# ---------------------------------------------------------------------------
def block_chords(ctx: TextureContext) -> list[Note]:
    out: list[Note] = []
    for span in ctx.timeline.spans:
        v = spread_voicing(span.chord, ctx.key, ctx.low, ctx.high,
                           density=3 + int(ctx.density * 2))
        for d in split_duration(span.duration, (span.start - ctx.timeline.start) % ctx.bar_ticks,
                                ctx.beat_ticks, ctx.bar_ticks):
            out.append(ctx.note(v, d))
        for i in range(len(out) - 1):
            pass
    return out


def sustained(ctx: TextureContext) -> list[Note]:
    """Whole-bar sonorities — orchestral pads and hymn-like writing."""
    out: list[Note] = []
    for start, end in _spans_in_bars(ctx):
        chord = ctx.timeline.at(start)
        v = spread_voicing(chord, ctx.key, ctx.low, ctx.high, density=3)
        out.append(ctx.note(v, end - start))
    return out


def alberti(ctx: TextureContext) -> list[Note]:
    """The classical low-high-middle-high figure."""
    unit = SIXTEENTH if ctx.density > 0.62 else EIGHTH
    out: list[Note] = []
    for start, end in _spans_in_bars(ctx):
        for t, d in _subdivide(start, end, unit):
            chord = ctx.timeline.at(t)
            b = _bass(chord, ctx.key, ctx.low, ctx.low + 12)
            up = _stack(chord, ctx.key, b, 2, ctx.hand_span)
            hi = up[-1] if up else b
            mid = up[0] if up else b
            pattern = [b, hi, mid, hi]
            idx = ((t - start) // unit) % 4
            out.append(ctx.note([pattern[idx]], d))
    return out


def waltz(ctx: TextureContext) -> list[Note]:
    """Bass on one, chords on two and three."""
    out: list[Note] = []
    for start, end in _spans_in_bars(ctx):
        beats = _subdivide(start, end, ctx.beat_ticks)
        for i, (t, d) in enumerate(beats):
            chord = ctx.timeline.at(t)
            if i == 0:
                b = _bass(chord, ctx.key, ctx.low, ctx.low + 10)
                pitches = [b, b.transpose_chromatic(12)] if ctx.density > 0.6 else [b]
                out.append(ctx.note(pitches, d))
            else:
                b = _bass(chord, ctx.key, ctx.low, ctx.low + 10)
                out.append(ctx.note(_stack(chord, ctx.key, b, 3, ctx.hand_span), d))
    return out


def march(ctx: TextureContext) -> list[Note]:
    out: list[Note] = []
    for start, end in _spans_in_bars(ctx):
        for i, (t, d) in enumerate(_subdivide(start, end, ctx.beat_ticks)):
            chord = ctx.timeline.at(t)
            b = _bass(chord, ctx.key, ctx.low, ctx.low + 10)
            if i % 2 == 0:
                out.append(ctx.note([b], d))
            else:
                out.append(ctx.note(_stack(chord, ctx.key, b, 3, ctx.hand_span), d))
    return out


def nocturne(ctx: TextureContext) -> list[Note]:
    """Chopin's wide left hand: low bass, then a rising span of chord tones.

    The bass is left alone for a beat and the upper notes fill in above it, which
    is what gives the texture its characteristic breadth under the pedal.
    """
    unit = EIGHTH if ctx.density < 0.7 else SIXTEENTH
    out: list[Note] = []
    for start, end in _spans_in_bars(ctx):
        steps = _subdivide(start, end, unit)
        n = len(steps)
        if n == 0:
            continue
        chord = ctx.timeline.at(start)
        b = _bass(chord, ctx.key, ctx.low, ctx.low + 9)
        upper = _stack(chord, ctx.key, b.transpose_chromatic(7), max(3, n - 1),
                       ctx.hand_span + 4)
        for i, (t, d) in enumerate(steps):
            c2 = ctx.timeline.at(t)
            if c2 is not chord:
                chord = c2
                b = _bass(chord, ctx.key, ctx.low, ctx.low + 9)
                upper = _stack(chord, ctx.key, b.transpose_chromatic(7),
                               max(3, n - 1), ctx.hand_span + 4)
            if i == 0:
                out.append(ctx.note([b], d))
            else:
                out.append(ctx.note([upper[(i - 1) % len(upper)]], d))
    return out


def rachmaninoff_wide(ctx: TextureContext) -> list[Note]:
    """A very wide left hand: deep octave bass then a sweeping arpeggio."""
    unit = EIGHTH
    out: list[Note] = []
    for start, end in _spans_in_bars(ctx):
        steps = _subdivide(start, end, unit)
        chord = ctx.timeline.at(start)
        b = _bass(chord, ctx.key, ctx.low, ctx.low + 8)
        arp = _stack(chord, ctx.key, b, 6, 26)
        for i, (t, d) in enumerate(steps):
            c2 = ctx.timeline.at(t)
            if c2 is not chord:
                chord = c2
                b = _bass(chord, ctx.key, ctx.low, ctx.low + 8)
                arp = _stack(chord, ctx.key, b, 6, 26)
            if i == 0:
                low_oct = [b] if b.midi - 12 < ctx.low - 2 else [b.transpose_chromatic(-12), b]
                out.append(ctx.note(low_oct, d))
            else:
                out.append(ctx.note([arp[(i - 1) % len(arp)]], d))
    return out


def arpeggio(ctx: TextureContext) -> list[Note]:
    """Continuous broken chord — the figuration under a Bach prelude or a study."""
    unit = SIXTEENTH if ctx.density > 0.5 else EIGHTH
    out: list[Note] = []
    direction = 1
    for start, end in _spans_in_bars(ctx):
        for t, d in _subdivide(start, end, unit):
            chord = ctx.timeline.at(t)
            b = _bass(chord, ctx.key, ctx.low, ctx.low + 12)
            tones = _stack(chord, ctx.key, b.transpose_chromatic(-1), 5, ctx.high - b.midi + 12)
            i = ((t - ctx.timeline.start) // unit)
            n = len(tones)
            if n == 0:
                continue
            k = i % (2 * n - 2) if n > 1 else 0
            idx = k if k < n else 2 * n - 2 - k
            out.append(ctx.note([tones[idx]], d))
    return out


def broken_octaves(ctx: TextureContext) -> list[Note]:
    unit = SIXTEENTH
    out: list[Note] = []
    for start, end in _spans_in_bars(ctx):
        for i, (t, d) in enumerate(_subdivide(start, end, unit)):
            chord = ctx.timeline.at(t)
            b = _bass(chord, ctx.key, ctx.low, ctx.low + 12)
            p = b if i % 2 == 0 else b.transpose_chromatic(12)
            out.append(ctx.note([p], d))
    return out


def octave_bass(ctx: TextureContext) -> list[Note]:
    out: list[Note] = []
    for span in ctx.timeline.spans:
        b = _bass(span.chord, ctx.key, ctx.low, ctx.low + 12)
        pair = [b.transpose_chromatic(-12), b] if b.midi - 12 >= 21 else [b]
        for d in split_duration(span.duration,
                                (span.start - ctx.timeline.start) % ctx.bar_ticks,
                                ctx.beat_ticks, ctx.bar_ticks):
            out.append(ctx.note(pair, d))
    return out


def tremolo(ctx: TextureContext) -> list[Note]:
    """Alternating dyads — orchestral agitation, Liszt's storm writing."""
    unit = SIXTEENTH
    out: list[Note] = []
    for start, end in _spans_in_bars(ctx):
        for i, (t, d) in enumerate(_subdivide(start, end, unit)):
            chord = ctx.timeline.at(t)
            b = _bass(chord, ctx.key, ctx.low, ctx.low + 12)
            up = _stack(chord, ctx.key, b, 2, ctx.hand_span)
            p = [b] if i % 2 == 0 else ([up[-1]] if up else [b])
            out.append(ctx.note(p, d))
    return out


def repeated_chords(ctx: TextureContext) -> list[Note]:
    """Schubert/Rachmaninoff pulsing chords."""
    unit = EIGHTH if ctx.density < 0.7 else SIXTEENTH
    out: list[Note] = []
    for start, end in _spans_in_bars(ctx):
        for t, d in _subdivide(start, end, unit):
            chord = ctx.timeline.at(t)
            b = _bass(chord, ctx.key, ctx.low + 7, ctx.low + 16)
            out.append(ctx.note(_stack(chord, ctx.key, b, 3, ctx.hand_span), d))
    return out


def walking_bass(ctx: TextureContext) -> list[Note]:
    """A stepwise bass connecting the roots — continuo and Baroque writing."""
    out: list[Note] = []
    unit = ctx.beat_ticks
    pcs = set(ctx.key.scale_pcs)
    prev: Pitch | None = None
    for start, end in _spans_in_bars(ctx):
        for t, d in _subdivide(start, end, unit):
            chord = ctx.timeline.at(t)
            if ctx.timeline.is_change(t) or prev is None:
                p = _bass(chord, ctx.key, ctx.low, ctx.low + 14)
            else:
                nxt_tick = ctx.timeline.next_change(t)
                nxt = _bass(ctx.timeline.at(min(nxt_tick, ctx.timeline.end - 1)),
                            ctx.key, ctx.low, ctx.low + 14)
                step = 1 if nxt.midi > prev.midi else -1
                cand = prev.midi + step
                while cand % 12 not in pcs and abs(cand - prev.midi) < 4:
                    cand += step
                p = ctx.key.spell(max(ctx.low, min(ctx.high, cand)))
            out.append(ctx.note([p], d))
            prev = p
    return out


def pedal_point(ctx: TextureContext) -> list[Note]:
    """A held tonic or dominant under changing harmony."""
    pc = ctx.extra.get("pedal_pc", ctx.key.tonic_pc)
    cands = [m for m in range(ctx.low, ctx.low + 13) if m % 12 == pc]
    p = ctx.key.spell(cands[0]) if cands else ctx.key.degree_pitch(1, 2)
    out: list[Note] = []
    for start, end in _spans_in_bars(ctx):
        out.append(ctx.note([p], end - start))
    return out


def ostinato(ctx: TextureContext) -> list[Note]:
    """A one-bar figure repeated, re-fitted to each new harmony."""
    unit = EIGHTH
    shape = ctx.extra.get("ostinato_shape") or [0, 2, 1, 2, 0, 2, 1, 2]
    out: list[Note] = []
    for start, end in _spans_in_bars(ctx):
        for i, (t, d) in enumerate(_subdivide(start, end, unit)):
            chord = ctx.timeline.at(t)
            b = _bass(chord, ctx.key, ctx.low, ctx.low + 12)
            tones = [b] + _stack(chord, ctx.key, b, 3, ctx.hand_span)
            out.append(ctx.note([tones[shape[i % len(shape)] % len(tones)]], d))
    return out


def chorale(ctx: TextureContext) -> list[Note]:
    """Homophonic block writing that moves with the harmonic rhythm."""
    out: list[Note] = []
    for span in ctx.timeline.spans:
        v = spread_voicing(span.chord, ctx.key, ctx.low, ctx.high, density=3, shape="close")
        for d in split_duration(span.duration,
                                (span.start - ctx.timeline.start) % ctx.bar_ticks,
                                ctx.beat_ticks, ctx.bar_ticks):
            out.append(ctx.note(v, d))
    return out


def two_part_invention(ctx: TextureContext) -> list[Note]:
    """A running counterpoint line: mostly steps with chord tones on the beat."""
    unit = SIXTEENTH if ctx.density > 0.55 else EIGHTH
    pcs = set(ctx.key.scale_pcs_for("harmonic_minor" if ctx.key.is_minor else ctx.key.mode))
    out: list[Note] = []
    cur = ctx.center
    direction = 1
    for start, end in _spans_in_bars(ctx):
        for t, d in _subdivide(start, end, unit):
            chord = ctx.timeline.at(t)
            on_beat = (t % ctx.beat_ticks) == 0
            allowed = set(chord.pcs) if on_beat else pcs | set(chord.pcs)
            cand = cur + direction
            guard = 0
            while cand % 12 not in allowed and guard < 12:
                cand += direction
                guard += 1
            if cand > ctx.high - 2 or cand < ctx.low + 2:
                direction *= -1
                cand = cur + direction
                guard = 0
                while cand % 12 not in allowed and guard < 12:
                    cand += direction
                    guard += 1
            if ctx.rng.random() < 0.16:
                direction *= -1
            cur = max(ctx.low, min(ctx.high, cand))
            out.append(ctx.note([spell_in_chord(cur, chord, ctx.key)], d))
    return out


def scale_run(ctx: TextureContext) -> list[Note]:
    unit = SIXTEENTH
    pcs = sorted(ctx.key.scale_pcs)
    out: list[Note] = []
    cur = ctx.low + 2
    direction = 1
    for start, end in _spans_in_bars(ctx):
        for t, d in _subdivide(start, end, unit):
            chord = ctx.timeline.at(t)
            cand = cur + direction
            while cand % 12 not in pcs:
                cand += direction
            if cand >= ctx.high or cand <= ctx.low:
                direction *= -1
            cur = max(ctx.low, min(ctx.high, cand))
            out.append(ctx.note([ctx.key.spell(cur)], d))
    return out


def drone(ctx: TextureContext) -> list[Note]:
    root = ctx.key.degree_pitch(1, max(1, ctx.low // 12 - 1))
    fifth = root.transpose_diatonic(4, ctx.key)
    out: list[Note] = []
    for start, end in _spans_in_bars(ctx):
        out.append(ctx.note([root, fifth], end - start))
    return out


def syncopated(ctx: TextureContext) -> list[Note]:
    """Off-beat chords over an on-beat bass — Brahms-flavoured displacement."""
    out: list[Note] = []
    half = ctx.beat_ticks // 2
    for start, end in _spans_in_bars(ctx):
        for i, (t, d) in enumerate(_subdivide(start, end, ctx.beat_ticks)):
            chord = ctx.timeline.at(t)
            b = _bass(chord, ctx.key, ctx.low, ctx.low + 10)
            if i == 0:
                out.append(ctx.note([b], half))
            else:
                out.append(ctx.note([], half))
            out.append(ctx.note(_stack(chord, ctx.key, b, 3, ctx.hand_span), d - half))
    return out


TEXTURES = {
    "block_chords": block_chords, "sustained": sustained, "alberti": alberti,
    "waltz": waltz, "march": march, "nocturne": nocturne,
    "rachmaninoff_wide": rachmaninoff_wide, "arpeggio": arpeggio,
    "broken_octaves": broken_octaves, "octave_bass": octave_bass,
    "tremolo": tremolo, "repeated_chords": repeated_chords,
    "walking_bass": walking_bass, "pedal_point": pedal_point, "ostinato": ostinato,
    "chorale": chorale, "two_part_invention": two_part_invention,
    "scale_run": scale_run, "drone": drone, "syncopated": syncopated,
}


def render_texture(name: str, ctx: TextureContext) -> list[Note]:
    fn = TEXTURES.get(name, block_chords)
    notes = fn(ctx)
    return _normalise(notes, ctx)


def _normalise(notes: list[Note], ctx: TextureContext) -> list[Note]:
    """Guarantee the voice exactly fills the timeline."""
    total = sum(n.duration for n in notes)
    want = ctx.timeline.duration
    if total < want:
        notes.append(ctx.note([], want - total))
    elif total > want:
        over = total - want
        while over > 0 and notes:
            last = notes[-1]
            if last.duration > over:
                last.duration -= over
                over = 0
            else:
                over -= last.duration
                notes.pop()
    return notes
