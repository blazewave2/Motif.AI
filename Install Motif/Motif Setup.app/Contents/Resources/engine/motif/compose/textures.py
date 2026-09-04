"""Accompaniment textures.

A Chopin nocturne and a Mozart sonata can share a chord progression and sound
nothing alike; the difference is texture.  Each function here renders one
idiomatic left-hand (or inner-voice) pattern across a harmonic timeline.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..score import (EIGHTH, Note, QUARTER, SIXTEENTH, THIRTYSECOND, Tuplet,
                     WHOLE, split_duration)
from ..theory.harmony import Chord
from ..theory.pitch import Key, Pitch
from .harmony_timeline import HarmonyTimeline
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
    variety: float = 0.5           # how much the figuration is allowed to change
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


def _bar_rhythm(ctx: TextureContext, start: int, end: int, unit: int
                ) -> list[tuple[int, int, Tuplet | None]]:
    """One bar of accompaniment rhythm, varied the way a player varies it.

    A figuration that repeats the same subdivision for forty bars is the single
    most mechanical thing an accompaniment can do.  Each bar therefore has a
    chance of breathing: pausing on the last beat, holding a note through,
    thinning to a slower pulse, or turning over in triplets.
    """
    span = end - start
    if span <= 0:
        return []
    plain = [(t, d, None) for t, d in _subdivide(start, end, unit)]
    if ctx.variety <= 0.01:
        return plain

    roll = ctx.rng.random()
    v = ctx.variety

    # Triplets: the same span turned over in threes.
    if roll < 0.10 * v and span % 3 == 0 and unit * 3 <= span:
        group = unit * 2                     # three notes per two units
        out: list[tuple[int, int, Tuplet | None]] = []
        t = start
        n = 0
        while t + group <= end:
            each = group // 3
            for i in range(3):
                tup = Tuplet(3, 2, "eighth" if each >= SIXTEENTH else "16th",
                             start=(i == 0), stop=(i == 2), number=1)
                out.append((t + i * each, each, tup))
            t += group
            n += 1
        if t < end:
            out.extend((tt, dd, None) for tt, dd in _subdivide(t, end, unit))
        if out:
            return out

    # Rest on the final beat: lets the melody speak.
    if roll < 0.10 + 0.16 * v:
        cut = max(start + unit, end - max(unit, ctx.beat_ticks))
        return [(t, d, None) for t, d in _subdivide(start, cut, unit)]

    # Hold the last note of the bar instead of repeating the figure.
    if roll < 0.26 + 0.18 * v:
        cut = max(start + unit, end - ctx.beat_ticks)
        out = [(t, d, None) for t, d in _subdivide(start, cut, unit)]
        if cut < end:
            out.append((cut, end - cut, None))
        return out

    # Halve the motion for a bar — a natural place to lean back.
    if roll < 0.44 + 0.12 * v and unit * 2 <= span:
        return [(t, d, None) for t, d in _subdivide(start, end, unit * 2)]

    # Double the motion at an intense moment.
    if roll < 0.52 + 0.14 * v and unit // 2 >= THIRTYSECOND and ctx.density > 0.55:
        return [(t, d, None) for t, d in _subdivide(start, end, unit // 2)]

    # Begin off the beat, letting the bar start with air.
    if roll < 0.60 + 0.10 * v and span > unit * 2:
        return [(t, d, None) for t, d in _subdivide(start + unit, end, unit)]

    # A dotted lilt instead of even motion.
    if roll < 0.68 + 0.10 * v and unit >= SIXTEENTH * 2:
        out: list[tuple[int, int, Tuplet | None]] = []
        t = start
        long, short = unit + unit // 2, unit // 2
        while t + long + short <= end:
            out.append((t, long, None))
            out.append((t + long, short, None))
            t += long + short
        if t < end:
            out.extend((tt, dd, None) for tt, dd in _subdivide(t, end, unit))
        if out:
            return out

    # An uneven 3+3+2 grouping, which stops a bar from ticking.
    if roll < 0.74 + 0.08 * v and span == unit * 8:
        return [(start, unit * 3, None), (start + unit * 3, unit * 3, None),
                (start + unit * 6, unit * 2, None)]

    return plain


# ---------------------------------------------------------------------------
# textures
# ---------------------------------------------------------------------------
def _figuration(ctx: TextureContext, unit: int, pick) -> list[Note]:
    """Drive a repeating figure through varied bar rhythms.

    ``pick(chord, step, count, bass)`` returns the pitches for one slot, so a
    texture only has to say *which notes*, not *when* — the rhythmic breathing
    is shared by every figuration.
    """
    out: list[Note] = []
    for start, end in _spans_in_bars(ctx):
        pattern = _bar_rhythm(ctx, start, end, unit)
        if not pattern:
            continue
        count = len(pattern)
        filled = 0
        for step, (t, d, tup) in enumerate(pattern):
            chord = ctx.timeline.at(t)
            bass = _bass(chord, ctx.key, ctx.low, ctx.low + 12)
            pitches = pick(chord, step, count, bass)
            note = ctx.note(list(pitches), d)
            if tup is not None:
                note.tuplet = tup
            out.append(note)
            filled += d
        # A bar the figure left short is a real rest, not a gap.
        if filled < end - start:
            out.append(ctx.note([], end - start - filled))
    return out


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

    def pick(chord, step, count, bass):
        up = _stack(chord, ctx.key, bass, 2, ctx.hand_span)
        hi = up[-1] if up else bass
        mid = up[0] if up else bass
        return [[bass, hi, mid, hi][step % 4]]

    return _figuration(ctx, unit, pick)

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
    """Chopin's wide left hand: a low bass, then chord tones rising above it.

    Leaving the bass alone for a beat and filling in above it is what gives the
    texture its breadth under the pedal.
    """
    unit = EIGHTH if ctx.density < 0.7 else SIXTEENTH

    def pick(chord, step, count, bass):
        if step == 0:
            return [bass]
        upper = _stack(chord, ctx.key, bass.transpose_chromatic(7),
                       max(3, count - 1), ctx.hand_span + 4)
        return [upper[(step - 1) % len(upper)]]

    return _figuration(ctx, unit, pick)

def rachmaninoff_wide(ctx: TextureContext) -> list[Note]:
    """A very wide left hand: a deep octave bass, then a sweeping arpeggio."""
    def pick(chord, step, count, bass):
        if step == 0:
            low = bass.midi - 12
            if low >= max(21, ctx.low - 2):
                return [spell_in_chord(low, chord, ctx.key), bass]
            return [bass]
        arp = _stack(chord, ctx.key, bass, 6, 26)
        return [arp[(step - 1) % len(arp)]]

    return _figuration(ctx, EIGHTH, pick)

def arpeggio(ctx: TextureContext) -> list[Note]:
    """Continuous broken chord — the figuration under a prelude or a study."""
    unit = SIXTEENTH if ctx.density > 0.5 else EIGHTH

    def pick(chord, step, count, bass):
        tones = _stack(chord, ctx.key, bass.transpose_chromatic(-1), 5,
                       max(12, ctx.high - bass.midi + 12))
        n = len(tones)
        if n == 1:
            return [tones[0]]
        k = step % (2 * n - 2)
        return [tones[k if k < n else 2 * n - 2 - k]]

    return _figuration(ctx, unit, pick)

def broken_octaves(ctx: TextureContext) -> list[Note]:
    def pick(chord, step, count, bass):
        return [bass if step % 2 == 0
                else spell_in_chord(bass.midi + 12, chord, ctx.key)]

    return _figuration(ctx, SIXTEENTH, pick)

def octave_bass(ctx: TextureContext) -> list[Note]:
    out: list[Note] = []
    for span in ctx.timeline.spans:
        b = _bass(span.chord, ctx.key, ctx.low, ctx.low + 12)
        pair = ([spell_in_chord(b.midi - 12, span.chord, ctx.key), b]
            if b.midi - 12 >= 21 else [b])
        for d in split_duration(span.duration,
                                (span.start - ctx.timeline.start) % ctx.bar_ticks,
                                ctx.beat_ticks, ctx.bar_ticks):
            out.append(ctx.note(pair, d))
    return out


def tremolo(ctx: TextureContext) -> list[Note]:
    """Alternating dyads — orchestral agitation, storm writing."""
    def pick(chord, step, count, bass):
        up = _stack(chord, ctx.key, bass, 2, ctx.hand_span)
        return [bass] if step % 2 == 0 else [up[-1] if up else bass]

    return _figuration(ctx, SIXTEENTH, pick)

def repeated_chords(ctx: TextureContext) -> list[Note]:
    """Schubert/Rachmaninoff pulsing chords."""
    unit = EIGHTH if ctx.density < 0.7 else SIXTEENTH

    def pick(chord, step, count, bass):
        top = _bass(chord, ctx.key, ctx.low + 7, ctx.low + 16)
        return _stack(chord, ctx.key, top, 3, ctx.hand_span) or [top]

    return _figuration(ctx, unit, pick)

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
    shape = ctx.extra.get("ostinato_shape") or [0, 2, 1, 2, 0, 2, 1, 2]

    def pick(chord, step, count, bass):
        tones = [bass] + _stack(chord, ctx.key, bass, 3, ctx.hand_span)
        return [tones[shape[step % len(shape)] % len(tones)]]

    return _figuration(ctx, EIGHTH, pick)

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
