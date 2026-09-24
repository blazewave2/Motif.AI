"""Texture: how the harmony is laid out under the melody.

Every composer has a sound, and most of it is here — the nocturne left hand
that strikes a deep bass and spreads the chord over a tenth and more (Chopin,
Field), the bass-chord-chord of a waltz, Mozart's Alberti bass, the tolling
octaves and chords of Rachmaninoff's bells, the wide triplet and sixteenth
arpeggios of Rachmaninoff and Liszt that sweep two octaves, the repeated
chords of Schubert and Brahms, a chorale, a walking contrapuntal bass for
Bach, open pedalled sonorities for Debussy.

Each realiser lays out one span of harmony at a time, voice-leading from
what came before (common tones held, the nearest chord position chosen),
keeping clear of the melody above and inside a hand's reach.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from fractions import Fraction as F

from ..theory.pitch import Key, Pitch
from .harmony import Harmony, spell


@dataclass
class TexNote:
    onset: F
    dur: F
    midis: list[int]
    staff: str = "LH"               # LH | RH (inner voices under the melody)
    voice: int = 1                  # 1 main, 2 a second voice on the same staff
    marks: list[str] = field(default_factory=list)
    tuplet: tuple[int, int] | None = None
    tuplet_start: bool = False
    tuplet_stop: bool = False

    @property
    def end(self) -> F:
        return self.onset + self.dur


@dataclass
class TextureContext:
    time: tuple[int, int]
    bar_len: F
    beat: F
    key: Key
    energy: float = 0.5
    bass_low: int = 31             # G1
    bass_high: int = 50            # D3
    mid_low: int = 48              # C3
    mid_high: int = 64             # E4
    melody_floor: dict = field(default_factory=dict)   # (start, end) -> lowest right-hand pitch
    melody_top: dict = field(default_factory=dict)     # (start, end) -> highest right-hand pitch
    rng: random.Random = field(default_factory=random.Random)
    prev_voicing: list[int] = field(default_factory=list)
    prev_bass: int | None = None
    tempo: float = 90.0            # beats per minute, so figuration suits the speed
    melody: list = field(default_factory=list)   # the phrase's tune, for textures that imitate it
    virtuoso: bool = False         # a composer whose runs stay fast at any tempo


def bass_note(h: Harmony, ctx: TextureContext, octave_down: bool = False) -> int:
    """The bass of a chord in the bass register, moving as little as it can
    from the last bass (a pedal note stays put)."""
    pc = h.bass_pc
    cands = [m for m in range(ctx.bass_low, ctx.bass_high + 1) if m % 12 == pc]
    if not cands:
        cands = [m for m in range(24, 60) if m % 12 == pc]
    if ctx.prev_bass is not None:
        best = min(cands, key=lambda m: (abs(m - ctx.prev_bass), m))
    else:
        mid = (ctx.bass_low + ctx.bass_high) // 2
        best = min(cands, key=lambda m: abs(m - mid))
    if octave_down and best - 12 >= 24:
        best -= 12
    return best


def chord_tones_between(h: Harmony, low: int, high: int) -> list[int]:
    pcs = set(h.chord.pcs)
    return [m for m in range(low, high + 1) if m % 12 in pcs]


def voicing(h: Harmony, ctx: TextureContext, n: int, low: int, high: int,
            prev: list[int] | None = None, include_bass_pc: bool = False,
            max_span: int = 12) -> list[int]:
    """``n`` chord tones between ``low`` and ``high``: all the chord's pitch
    classes if there's room (the bass's own pitch class last to be doubled),
    as close as possible to the previous voicing."""
    tones = chord_tones_between(h, low, high)
    if not tones:
        return []
    pcs = list(h.chord.pcs)
    bass_pc = h.chord.bass_pc
    # prefer omitting the fifth, then doubling the root, when there are
    # fewer notes than pitch classes
    fifth_pc = (h.chord.root.pc + 7) % 12
    best, best_cost = None, 1e9
    import itertools
    pool = tones[:14]
    for combo in itertools.combinations(pool, min(n, len(pool))):
        span = combo[-1] - combo[0]
        if span > max_span:
            continue
        cpcs = {m % 12 for m in combo}
        cost = 0.0
        missing = [pc for pc in pcs if pc not in cpcs]
        for pc in missing:
            cost += 1.5 if pc == fifth_pc else 3.0
        if not include_bass_pc and bass_pc in cpcs and len(pcs) > len(combo):
            cost += 0.8
        # spacing: no seconds packed at the bottom
        for a, b in zip(combo, combo[1:]):
            if b - a < 3:
                cost += 0.6
        if prev:
            cost += 0.12 * sum(min(abs(m - p) for p in prev) for m in combo)
        else:
            mid = (low + high) / 2
            cost += 0.05 * abs(sum(combo) / len(combo) - mid)
        if cost < best_cost:
            best, best_cost = list(combo), cost
    return best or tones[:n]


# ---------------------------------------------------------------------------
# the realisers: each lays out one chord (onset, dur) and returns notes
# ---------------------------------------------------------------------------
def _below_melody(ctx: TextureContext, t: F, default: int) -> int:
    """The highest an accompaniment note may go at time ``t``: a third
    under the melody."""
    floor = None
    for (a, b), low in ctx.melody_floor.items():
        if a <= t < b:
            floor = low if floor is None else min(floor, low)
    return min(default, (floor - 3) if floor is not None else default)


def _melody_top(ctx: TextureContext, t0: F, t1: F) -> int | None:
    """The highest right-hand note between ``t0`` and ``t1``."""
    top = None
    for (a, b), hi in ctx.melody_top.items():
        if a < t1 and b > t0:
            top = hi if top is None else max(top, hi)
    return top


def _melody_low(ctx: TextureContext, t0: F, t1: F) -> int | None:
    low = None
    for (a, b), lo in ctx.melody_floor.items():
        if a < t1 and b > t0:
            low = lo if low is None else min(low, lo)
    return low


def inner_chord(h: Harmony, t0: F, dur: F, ctx: TextureContext, n: int = 2) -> list[int]:
    """Chord tones the right hand can hold under its melody for the whole of
    ``dur``: below the melody's lowest note and within a ninth of its
    highest."""
    top = _melody_top(ctx, t0, t0 + dur)
    low = _melody_low(ctx, t0, t0 + dur)
    if top is None or low is None:
        return []
    hi = low - 3
    lo = max(top - 13, 52)
    if hi - lo < 3:
        return []
    return voicing(h, ctx, n, lo, hi, None, max_span=9)


def nocturne(h: Harmony, t0: F, dur: F, ctx: TextureContext) -> list[TexNote]:
    """A deep bass, then the chord spread upward over a tenth and more."""
    out: list[TexNote] = []
    b = bass_note(h, ctx)
    ctx.prev_bass = b
    compound = ctx.beat == F(3, 2)
    unit = F(1, 2) if (compound or ctx.beat == 1) else F(1, 2)
    group = F(3, 2) if compound else (F(2) if ctx.time[0] in (4, 2) else F(3))
    t = t0
    end = t0 + dur
    while t < end:
        span = min(group, end - t)
        top = _below_melody(ctx, t, ctx.mid_high + 4)
        above = chord_tones_between(h, b + 5, min(b + 24, top))
        # choose a rising line of chord tones: fifth or tenth, then higher
        line = []
        for m in above:
            if not line or m - line[-1] >= 3:
                line.append(m)
        if not line:
            line = [b + 12]
        steps = int(span / unit)
        pattern = [b]
        k = 0
        rising = line[:max(1, min(len(line), steps - 1))]
        seq = rising + list(reversed(rising[:-1]))
        while len(pattern) < steps:
            pattern.append(seq[k % len(seq)])
            k += 1
        for i, m in enumerate(pattern):
            onset = t + unit * i
            if onset >= end:
                break
            d = min(unit, end - onset)
            out.append(TexNote(onset, d, [m]))
        t += span
    return out


def waltz(h: Harmony, t0: F, dur: F, ctx: TextureContext) -> list[TexNote]:
    """Bass on the downbeat, the chord on two and three."""
    out: list[TexNote] = []
    t, end = t0, t0 + dur
    while t < end:
        b = bass_note(h, ctx, octave_down=False)
        ctx.prev_bass = b
        out.append(TexNote(t, min(ctx.beat, end - t), [b]))
        top = _below_melody(ctx, t, ctx.mid_high)
        v = voicing(h, ctx, 3, max(b + 7, ctx.mid_low), top, ctx.prev_voicing)
        ctx.prev_voicing = v or ctx.prev_voicing
        for k in (1, 2):
            on = t + ctx.beat * k
            if on >= end or not v:
                break
            out.append(TexNote(on, min(ctx.beat, end - on), list(v),
                               marks=["stacc"] if ctx.energy > 0.55 else []))
        t += ctx.bar_len
    return out


def alberti(h: Harmony, t0: F, dur: F, ctx: TextureContext) -> list[TexNote]:
    """Low, high, middle, high: Mozart's broken chord in the tenor."""
    out: list[TexNote] = []
    unit = F(1, 4) if (ctx.energy >= 0.45 and ctx.tempo * float(ctx.beat) < 110) else F(1, 2)
    top = _below_melody(ctx, t0, 64)
    v = voicing(h, ctx, 3, max(43, top - 14), top, ctx.prev_voicing, include_bass_pc=True)
    if len(v) < 3:
        v = (v * 3)[:3] if v else [48, 52, 55]
    # the chord's bass in the lowest voice when there's room
    low, mid, high = v[0], v[1], v[2]
    bass_pc = h.bass_pc
    for cand in range(low - 12, low + 1):
        if cand % 12 == bass_pc and high - cand <= 12:
            low = cand
            break
    ctx.prev_voicing = [low, mid, high]
    pat = [low, high, mid, high]
    t, i = t0, 0
    while t < t0 + dur:
        d = min(unit, t0 + dur - t)
        out.append(TexNote(t, d, [pat[i % 4]]))
        t += unit
        i += 1
    return out


def block(h: Harmony, t0: F, dur: F, ctx: TextureContext, rh_inner: bool = True
          ) -> list[TexNote]:
    """A chorale: the bass (in octaves when the music is strong) with the
    chord above it, and the chord's upper notes held in the right hand under
    the melody where the hand can reach them."""
    if ctx.energy > 0.8 and dur >= 2 * ctx.beat:
        # at full strength the left hand tolls and answers, as in the bells
        return bells(h, t0, dur, ctx)
    out: list[TexNote] = []
    b = bass_note(h, ctx)
    ctx.prev_bass = b
    octave = ctx.energy > 0.7 and b - 12 >= 24
    lh = [b - 12, b] if octave else [b]
    if not octave:
        top = min(_below_melody(ctx, t0, ctx.mid_high + 2), b + 12)
        lh += voicing(h, ctx, 2, b + 3, top, ctx.prev_voicing, max_span=9)
    ctx.prev_voicing = [m for m in lh if m > b] or ctx.prev_voicing
    if ctx.tempo * float(ctx.beat) >= 110 and dur >= 2 * ctx.beat:
        # at a quick tempo a held chord goes dead: strike it on every beat
        t = t0
        while t < t0 + dur:
            d = min(ctx.beat, t0 + dur - t)
            out.append(TexNote(t, d, sorted(set(lh))))
            t += ctx.beat
    else:
        out.append(TexNote(t0, dur, sorted(set(lh))))
    if rh_inner:
        v = inner_chord(h, t0, dur, ctx, 2)
        if v:
            out.append(TexNote(t0, dur, v, staff="RH", voice=2))
    return out


def bells(h: Harmony, t0: F, dur: F, ctx: TextureContext) -> list[TexNote]:
    """Rachmaninoff's bells: a deep octave tolls on the beat and the left hand
    answers with the chord in the tenor, inside one hand's reach."""
    out: list[TexNote] = []
    b = bass_note(h, ctx)
    low = b - 12 if b - 12 >= 24 else b
    ctx.prev_bass = b
    top = min(_below_melody(ctx, t0, 64), 64)
    v = voicing(h, ctx, 3, max(low + 7, 40), top, ctx.prev_voicing, max_span=11)
    if len(v) < 2:
        v = voicing(h, ctx, 3, max(low + 5, 38), max(top, 55), ctx.prev_voicing, max_span=11)
    ctx.prev_voicing = v or ctx.prev_voicing
    beats = int(dur / ctx.beat) if ctx.beat else 1
    strong_every = 2 if (ctx.energy >= 0.55 and ctx.time[0] == 4) else 0
    t, k = t0, 0
    while t < t0 + dur:
        d = min(ctx.beat, t0 + dur - t)
        pos = int(((t - t0) / ctx.beat)) if ctx.beat else 0
        toll = k == 0 or (strong_every and pos % strong_every == 0 and beats > 2)
        if toll or not v:
            out.append(TexNote(t, d, [low, low + 12],
                               marks=["accent"] if (ctx.energy > 0.6 and k == 0) else []))
        else:
            out.append(TexNote(t, d, list(v)))
        t += ctx.beat
        k += 1
    return out


def sweep(h: Harmony, t0: F, dur: F, ctx: TextureContext, triplets: bool = True
          ) -> list[TexNote]:
    """Wide arpeggios that sweep up two octaves and back — the Rachmaninoff
    and Liszt left hand."""
    out: list[TexNote] = []
    b = bass_note(h, ctx)
    ctx.prev_bass = b
    top = _below_melody(ctx, t0, ctx.mid_high + 5)
    tones = [m for m in chord_tones_between(h, b + 7, min(b + 28, top))]
    line = [b]
    for m in tones:
        if m - line[-1] >= 3:
            line.append(m)
    if len(line) < 3:
        line = [b, b + 7, b + 12]
    wave = line + list(reversed(line[1:-1]))
    quick = ctx.tempo * float(ctx.beat)
    if not triplets and quick >= 120 and ctx.beat == 1 and not ctx.virtuoso:
        triplets = True       # sixteenths would be a blur at this speed: triplet eighths
    if triplets and ctx.beat == 1 and quick >= 150 and not ctx.virtuoso:
        per_beat, unit, tup = 2, F(1, 2), None     # and at a real Allegro, plain eighths
    elif triplets and ctx.beat == 1:
        per_beat, unit, tup = 3, F(1, 3), (3, 2)
    elif ctx.beat == F(3, 2):
        per_beat, unit, tup = 3, F(1, 2), None
    else:
        per_beat, unit, tup = 4, F(1, 4), None
    t, i = t0, 0
    end = t0 + dur
    while t < end:
        for k in range(per_beat):
            on = t + unit * k
            if on >= end:
                break
            n = TexNote(on, unit, [wave[i % len(wave)]])
            if tup:
                n.tuplet = tup
                n.tuplet_start = k == 0
                n.tuplet_stop = k == per_beat - 1
            out.append(n)
            i += 1
        t += ctx.beat
    return out


def repeated(h: Harmony, t0: F, dur: F, ctx: TextureContext) -> list[TexNote]:
    """Bass on the beat, repeated chords on the off-beats (Schubert, Brahms)."""
    out: list[TexNote] = []
    b = bass_note(h, ctx)
    ctx.prev_bass = b
    top = _below_melody(ctx, t0, ctx.mid_high)
    v = voicing(h, ctx, 3, max(b + 5, ctx.mid_low), top, ctx.prev_voicing)
    ctx.prev_voicing = v or ctx.prev_voicing
    t = t0
    while t < t0 + dur:
        out.append(TexNote(t, F(1, 2), [b]))
        if v and t + F(1, 2) < t0 + dur:
            out.append(TexNote(t + F(1, 2), F(1, 2), list(v)))
        t += ctx.beat
    return out


def walking(h: Harmony, t0: F, dur: F, ctx: TextureContext, nxt: Harmony | None = None
            ) -> list[TexNote]:
    """A bass line in eighths that walks through the chord to the next one."""
    out: list[TexNote] = []
    b = bass_note(h, ctx)
    steps = int(dur / F(1, 2))
    target = None
    if nxt is not None:
        save = ctx.prev_bass
        ctx.prev_bass = b
        target = bass_note(nxt, ctx)
        ctx.prev_bass = save
    line = [b]
    scale = sorted({(ctx.key.tonic_pc + i) % 12 for i in (0, 2, 3, 5, 7, 8, 10, 11)}
                   if ctx.key.is_minor else set(ctx.key.scale_pcs))
    pcs = set(h.chord.pcs)
    cur = b
    for k in range(1, steps):
        remaining = steps - k
        if target is not None and remaining <= 2:
            direction = 1 if target > cur else -1
        else:
            direction = ctx.rng.choice([1, 1, -1]) if k % 2 else ctx.rng.choice([1, -1])
        # move by step through the scale, or leap to a chord tone
        cand = []
        for m in range(cur - 7, cur + 8):
            if m == cur or not (ctx.bass_low - 3 <= m <= ctx.bass_high + 7):
                continue
            pc = m % 12
            if (m - cur) * direction <= 0:
                continue
            if pc in pcs or (abs(m - cur) <= 2 and pc in scale):
                cand.append(m)
        cur = min(cand, key=lambda m: abs(m - cur)) if cand else cur
        line.append(cur)
    ctx.prev_bass = line[-1]
    for k, m in enumerate(line):
        out.append(TexNote(t0 + F(1, 2) * k, F(1, 2), [m]))
    return out


def sustained(h: Harmony, t0: F, dur: F, ctx: TextureContext) -> list[TexNote]:
    """An open, pedalled sonority: bass, fifth and ninth or tenth."""
    b = bass_note(h, ctx)
    ctx.prev_bass = b
    top = _below_melody(ctx, t0, 62)
    tones = [m for m in chord_tones_between(h, b + 7, top)][:2]
    return [TexNote(t0, dur, [b] + tones)]


def final_chord(h: Harmony, t0: F, dur: F, ctx: TextureContext) -> list[TexNote]:
    """The last chord of a piece, held: a deep octave with the fifth or
    tenth above it, rolled."""
    b = bass_note(h, ctx)
    low = b - 12 if b - 12 >= 24 else b
    top = min(_below_melody(ctx, t0, 60), 60)
    above = [m for m in chord_tones_between(h, low + 7, min(low + 16, top))][:1]
    notes = sorted({low, low + 12, *above})
    if notes[-1] - notes[0] > 16:
        notes = [low, low + 12]
    return [TexNote(t0, dur, notes, marks=["arp"] if len(notes) > 2 else [])]


def _merge_lh(notes: list[TexNote]) -> list[TexNote]:
    return notes


REALISERS = {
    "nocturne": nocturne, "waltz": waltz, "alberti": alberti, "block": block,
    "bells": bells, "sweep": lambda h, t, d, c: sweep(h, t, d, c, True),
    "sweep16": lambda h, t, d, c: sweep(h, t, d, c, False), "repeated": repeated,
    "sustained": sustained, "final": final_chord,
}


def imitation(harmonies: list[Harmony], start: F, end: F, ctx: TextureContext) -> list[TexNote]:
    """Two-part invention: the right hand states the subject alone, the left
    hand answers it an octave or two lower a bar later, and then walks on in
    counterpoint."""
    bar = ctx.bar_len
    out: list[TexNote] = []
    subject = [n for n in ctx.melody if start <= n.onset < start + bar]
    if not subject or end - start < 3 * bar:
        return realise("walking", harmonies, start, end, ctx)
    top = max(n.midi for n in subject)
    drop = 12
    while top - drop > 60:
        drop += 12
    for n in subject:
        on = n.onset + bar
        if on >= end:
            break
        out.append(TexNote(on, min(n.dur, end - on), [n.midi - drop]))
    ctx.prev_bass = subject[-1].midi - drop
    out += realise("walking", harmonies, start + 2 * bar, end, ctx)
    return out


def realise(kind: str, harmonies: list[Harmony], start: F, end: F, ctx: TextureContext
            ) -> list[TexNote]:
    """Lay out every chord between ``start`` and ``end`` in texture ``kind``."""
    if kind == "imitation":
        return imitation(harmonies, start, end, ctx)
    out: list[TexNote] = []
    for i, h in enumerate(harmonies):
        a, b = max(h.onset, start), min(h.end, end)
        if b <= a:
            continue
        if kind == "walking":
            nxt = harmonies[i + 1] if i + 1 < len(harmonies) else None
            out.extend(walking(h, a, b - a, ctx, nxt))
            continue
        fn = REALISERS.get(kind, block)
        out.extend(fn(h, a, b - a, ctx))
    return out


def spell_notes(notes: list[TexNote], harmonies: list[Harmony]) -> list[tuple[TexNote, list[Pitch]]]:
    from .harmony import harmony_at
    out = []
    for n in notes:
        h = harmony_at(harmonies, n.onset)
        out.append((n, [spell(m, h) for m in n.midis]))
    return out
