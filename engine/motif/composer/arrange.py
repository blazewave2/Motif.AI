"""Scoring a composed piece for an ensemble.

The composer thinks in melody, harmony and bass whatever the forces; this
module hands those to instruments the way an arranger would. The tune goes
to the voice, the violin or the first violins; the inner parts are written
as real voices, led smoothly from chord to chord below the tune, and move in
the rhythm the passage calls for — held in calm music, pulsing when it
presses forward, broken into arpeggios where the piano would have flowed;
the bass sings its own line. In an orchestra the winds double the strings
as the music grows, and trumpets and timpani join only at its height. A
piano accompanying a soloist keeps its left hand and gains chords in the
right, never doubling the tune.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F

from ..theory.pitch import Key, Pitch
from .harmony import Harmony, harmony_at, spell
from .notation import Mark, Note, Voice
from .texture import TextureContext, realise, voicing


@dataclass(frozen=True)
class PartDef:
    id: str            # the part's id in the score (letters and digits)
    instrument: str    # an instrument the notation knows
    name: str
    role: str          # lead | lead8 | lead_solo | alto | alto_w | tenor | bass | bass8 |
    #                    bass_w | horn | tutti | timpani | accomp | organ | keys | guitar
    low: int = 36
    high: int = 96


ENSEMBLE_PARTS: dict[str, list[PartDef]] = {
    "voice_piano": [PartDef("V", "voice", "Voice", "lead", 57, 79),
                    PartDef("Pno", "piano", "Piano", "accomp", 21, 108)],
    "violin_piano": [PartDef("Vn", "violin", "Violin", "lead", 55, 96),
                     PartDef("Pno", "piano", "Piano", "accomp", 21, 108)],
    "cello_piano": [PartDef("Vc", "cello", "Violoncello", "lead", 36, 76),
                    PartDef("Pno", "piano", "Piano", "accomp", 21, 108)],
    "piano_trio": [PartDef("Vn", "violin", "Violin", "lead", 55, 96),
                   PartDef("Vc", "cello", "Violoncello", "tenor", 43, 72),
                   PartDef("Pno", "piano", "Piano", "accomp", 21, 108)],
    "string_quartet": [PartDef("Vn1", "violin", "Violin I", "lead", 55, 96),
                       PartDef("Vn2", "violin", "Violin II", "alto", 55, 84),
                       PartDef("Vla", "viola", "Viola", "tenor", 48, 76),
                       PartDef("Vc", "cello", "Violoncello", "bass", 36, 67)],
    "string_orchestra": [PartDef("Vn1", "violin", "Violin I", "lead", 55, 96),
                         PartDef("Vn2", "violin", "Violin II", "alto", 55, 84),
                         PartDef("Vla", "viola", "Viola", "tenor", 48, 76),
                         PartDef("Vc", "cello", "Violoncello", "bass", 36, 67),
                         PartDef("Cb", "double_bass", "Contrabass", "bass8", 28, 55)],
    "orchestra": [PartDef("Fl", "flute", "Flute", "lead8", 60, 93),
                  PartDef("Ob", "oboe", "Oboe", "lead_solo", 60, 88),
                  PartDef("Cl", "clarinet", "Clarinet in B♭", "alto_w", 52, 84),
                  PartDef("Bsn", "bassoon", "Bassoon", "bass_w", 36, 67),
                  PartDef("Hn", "horn", "Horn in F", "horn", 48, 74),
                  PartDef("Tpt", "trumpet", "Trumpet in B♭", "tutti", 58, 80),
                  PartDef("Timp", "timpani", "Timpani", "timpani", 38, 55),
                  PartDef("Vn1", "violin", "Violin I", "lead", 55, 96),
                  PartDef("Vn2", "violin", "Violin II", "alto", 55, 84),
                  PartDef("Vla", "viola", "Viola", "tenor", 48, 76),
                  PartDef("Vc", "cello", "Violoncello", "bass", 36, 67),
                  PartDef("Cb", "double_bass", "Contrabass", "bass8", 28, 55)],
    "chamber": [PartDef("Fl", "flute", "Flute", "lead", 60, 93),
                PartDef("Cl", "clarinet", "Clarinet in B♭", "alto", 52, 84),
                PartDef("Vn", "violin", "Violin", "lead8lo", 55, 88),
                PartDef("Vc", "cello", "Violoncello", "bass", 36, 67),
                PartDef("Pno", "piano", "Piano", "accomp", 21, 108)],
    "organ": [PartDef("Org", "organ", "Organ", "organ", 36, 96)],
    "harpsichord": [PartDef("Hpd", "harpsichord", "Harpsichord", "keys", 29, 89)],
    "guitar": [PartDef("Gtr", "guitar", "Guitar", "guitar", 40, 83)],
}

#: Where the tune sits for each ensemble's lead: (low, high, climax).
LEAD_RANGE: dict[str, tuple[int, int, int]] = {
    "voice_piano": (62, 76, 79),
    "violin_piano": (64, 86, 93),
    "cello_piano": (48, 67, 72),
    "piano_trio": (64, 86, 91),
    "string_quartet": (64, 86, 91),
    "string_orchestra": (64, 86, 91),
    "orchestra": (64, 86, 91),
    "chamber": (65, 86, 91),
    "organ": (60, 81, 84),
    "harpsichord": (60, 81, 84),
    "guitar": (57, 76, 79),
}


def supported(ensemble: str | None) -> bool:
    return (ensemble or "solo_piano") in ENSEMBLE_PARTS


# ---------------------------------------------------------------------------
# inner voices
# ---------------------------------------------------------------------------
@dataclass
class _Chordal:
    """A chord's inner voices for its whole span."""

    onset: F
    dur: F
    alto: int | None
    tenor: int | None
    bass: int
    harmony: Harmony


def _inner_voices(written, key: Key, bass_low: int, parts: list[PartDef],
                  reach: int | None = None) -> list[_Chordal]:
    """Alto and tenor for every chord, led smoothly under the tune and above
    the bass, each inside its instrument's range."""
    alto_def = next((p for p in parts if p.role in ("alto", "alto_w")), None)
    tenor_def = next((p for p in parts if p.role == "tenor"), None)
    a_lo, a_hi = (alto_def.low, alto_def.high) if alto_def else (55, 79)
    t_lo, t_hi = (tenor_def.low, tenor_def.high) if tenor_def else (48, 69)
    out: list[_Chordal] = []
    prev_a = prev_t = prev_b = None
    for w in written:
        mel = sorted(w.melody, key=lambda n: n.onset)
        for h in w.harmony:
            # the lowest the tune goes over this chord
            over = [n.midi for n in mel if n.onset < h.end and n.end > h.onset]
            ceiling = (min(over) - 2) if over else 76
            floor_a = (max(over) - reach) if (over and reach) else a_lo
            pcs = sorted(h.pcs)
            bpc = h.bass_pc
            bass_c = [m for m in range(max(36, bass_low + 12), 62) if m % 12 == bpc]
            b = min(bass_c, key=lambda m: abs(m - (prev_b if prev_b is not None else 48)))
            best, best_cost = None, 1e9
            alto_c = [m for m in range(max(a_lo, floor_a), min(a_hi, ceiling) + 1)
                      if m % 12 in pcs]
            tenor_c = [m for m in range(t_lo, t_hi + 1) if m % 12 in pcs]
            for a in alto_c or [None]:
                for t in tenor_c or [None]:
                    if a is not None and t is not None and not (b < t < a) and not (t <= a):
                        continue
                    if a is not None and t is not None and (a - t < 2 or a - t > 12):
                        continue
                    if t is not None and t <= b:
                        continue
                    have = {x % 12 for x in (a, t, b) if x is not None}
                    have |= {n % 12 for n in over[:1]}
                    cost = 2.0 * sum(1 for pc in pcs if pc not in have)
                    if a is not None and prev_a is not None:
                        cost += 0.35 * abs(a - prev_a)
                    if t is not None and prev_t is not None:
                        cost += 0.35 * abs(t - prev_t)
                    if a is not None and t is not None and a % 12 == t % 12:
                        cost += 1.0
                    if cost < best_cost:
                        best, best_cost = (a, t), cost
            a, t = best if best else (None, None)
            out.append(_Chordal(h.onset, h.dur, a, t, b, h))
            prev_a = a if a is not None else prev_a
            prev_t = t if t is not None else prev_t
            prev_b = b
    return out


def _pulse(onset: F, dur: F, beat: F, style: str) -> list[tuple[F, F]]:
    """The rhythm an inner part moves in over one chord."""
    if style == "hold":
        return [(onset, dur)]
    unit = beat if style == "beat" else beat / 2
    out, t = [], onset
    while t < onset + dur:
        d = min(unit, onset + dur - t)
        out.append((t, d))
        t += d
    return out


def _motion(phrase, prof_harmony: str) -> str:
    """How the inner parts move in a phrase: held, on the beat, or pulsing."""
    e = phrase.spec.energy
    tex = phrase.spec.texture
    if tex in ("alberti", "repeated") or e >= 0.8:
        return "pulse"
    if tex in ("waltz",):
        return "beat"
    if e >= 0.6 or prof_harmony == "baroque":
        return "beat"
    return "hold"


# ---------------------------------------------------------------------------
# the arrangement
# ---------------------------------------------------------------------------
def arrange(composer, written, end: F) -> tuple[list[tuple[str, str, str]], list[Voice]]:
    """(parts, voices) for ``composer``'s ensemble."""
    ensemble = composer.ensemble
    parts = ENSEMBLE_PARTS[ensemble]
    bar, beat = composer.bar, composer.beat
    key = composer.key
    chords = _inner_voices(written, key, composer.prof.bass_low, parts,
                           reach=12 if ensemble == "organ" else None)
    phrase_at = _phrase_lookup(written)
    voices: list[Voice] = []
    declared: list[tuple[str, str, str]] = []
    for p in parts:
        declared.append((p.id, p.instrument, p.name))
        if p.role in ("accomp", "keys"):
            voices += _keyboard(composer, written, end, p, accompany=(p.role == "accomp"))
        elif p.role == "organ":
            voices += _organ(composer, written, chords, p)
        elif p.role == "guitar":
            voices.append(_guitar(composer, written, chords, p))
        else:
            voices.append(_line(composer, written, chords, p, phrase_at, bar, beat))
    return declared, voices


def _phrase_lookup(written):
    spans = [(w.start, w.start + sum((h.dur for h in w.harmony), F(0)), w) for w in written]

    def at(t: F):
        for a, b, w in spans:
            if a <= t < b:
                return w
        return written[-1]
    return at


def _fit(m: int, low: int, high: int) -> int | None:
    while m > high:
        m -= 12
    while m < low:
        m += 12
    return m if low <= m <= high else None


def _line(composer, written, chords, p: PartDef, phrase_at, bar: F, beat: F) -> Voice:
    v = Voice(p.id)
    key_spell = composer.key
    for w in written:
        e = w.spec.energy
        # -- the tune and its doublings
        if p.role in ("lead", "lead8", "lead8lo", "lead_solo", "tutti"):
            play = {
                "lead": True,
                "lead8": e >= 0.6,
                "lead8lo": w.spec.role in ("contrast", "climax", "development"),
                "lead_solo": e < 0.6 and w.spec.role in ("theme", "return", "closing"),
                "tutti": e >= 0.85,
            }[p.role]
            if not play:
                continue
            shift = 12 if p.role == "lead8" else 0
            for n in w.melody:
                m = _fit(n.midi + shift, p.low, p.high)
                if m is None:
                    continue
                h = harmony_at(w.harmony, n.onset)
                pitch = n.pitch if (m == n.midi and n.pitch is not None) else spell(m, h)
                v.add(Note(n.onset, n.dur, [pitch], marks=list(n.marks),
                           slur_start=n.slur_start, slur_stop=n.slur_stop))
            continue
        motion = _motion(w, composer.prof.harmony)
        span = [c for c in chords if w.start <= c.onset < w.start + bar * w.spec.bars]
        for c in span:
            h = c.harmony
            if p.role in ("alto", "alto_w", "tenor", "horn"):
                if p.role == "alto_w" and e < 0.5:
                    continue
                if p.role == "horn":
                    if e < 0.5:
                        continue
                    pcs = [h.root_pc, (h.root_pc + 7) % 12]
                    cands = [m for m in range(p.low, p.high + 1) if m % 12 in pcs]
                    if not cands:
                        continue
                    m = min(cands, key=lambda x: abs(x - 62))
                    v.add(Note(c.onset, c.dur, [spell(m, h)]))
                    continue
                m = c.alto if p.role in ("alto", "alto_w") else c.tenor
                if m is None:
                    continue
                m = _fit(m, p.low, p.high)
                if m is None:
                    continue
                for on, d in _pulse(c.onset, c.dur, beat, motion):
                    v.add(Note(on, d, [spell(m, h)]))
            elif p.role in ("bass", "bass8", "bass_w"):
                if p.role == "bass_w" and e < 0.45:
                    continue
                m = c.bass - (12 if p.role == "bass8" else 0)
                m = _fit(m, p.low, p.high)
                if m is None:
                    continue
                style = "beat" if motion == "pulse" else ("hold" if motion == "hold" else "beat")
                if p.role == "bass8" and style == "beat":
                    style = "hold" if e < 0.8 else "beat"
                for on, d in _pulse(c.onset, c.dur, beat * (2 if style == "beat" and
                                                            composer.time[0] == 4 else 1),
                                    style):
                    v.add(Note(on, d, [spell(m, h)]))
            elif p.role == "timpani":
                if e < 0.8:
                    continue
                if h.bass_pc not in (key_spell.tonic_pc, (key_spell.tonic_pc + 7) % 12):
                    continue
                cands = [m for m in range(p.low, p.high + 1) if m % 12 == h.bass_pc]
                if not cands:
                    continue
                m = min(cands, key=lambda x: abs(x - 45))
                v.add(Note(c.onset, min(beat, c.dur), [spell(m, h)], marks=["accent"]))
    _dynamics_for(v, written, composer)
    return v


def _dynamics_for(v: Voice, written, composer) -> None:
    """Each part gets the phrase dynamics wherever it plays."""
    from .core import _energy_dynamic
    last = None
    for w in written:
        notes = [n for n in v.notes if w.start <= n.onset < w.start + composer.bar * w.spec.bars]
        if not notes:
            last = None
            continue
        dyn = _energy_dynamic(composer.prof, w.spec.energy)
        if w.spec.role == "closing":
            dyn = composer.prof.dynamics[0]
        if dyn != last:
            v.marks.append(Mark(notes[0].onset, "dyn", dyn))
            last = dyn


def _keyboard(composer, written, end: F, p: PartDef, accompany: bool) -> list[Voice]:
    """A piano accompanying a soloist, or a harpsichord playing alone."""
    prefix = p.id + "."
    rh = Voice(prefix + "RH")
    rh2 = Voice(prefix + "RH2", secondary=True)
    lh = Voice(prefix + "LH")
    ctx = TextureContext(composer.time, composer.bar, composer.beat, composer.key,
                         bass_low=composer.prof.bass_low, rng=composer.rng,
                         tempo=float(composer.tempo))
    if not accompany:
        from .core import _group_tuplets, _melody_to_voice
        for w in written:
            _melody_to_voice(rh, w.melody, "", w.harmony, w.start, None)
        _group_tuplets(rh.notes)
    from .core import _rh_extent
    ctx.melody_floor, ctx.melody_top = _rh_extent(rh, composer.bar, end) if rh.notes else ({}, {})
    for w in written:
        ctx.key = w.spec.key
        ctx.energy = w.spec.energy
        span_end = w.start + composer.bar * w.spec.bars
        tex = realise(w.spec.texture, w.harmony, w.start, span_end, ctx)
        for n in tex:
            h = harmony_at(w.harmony, n.onset)
            pitches = sorted((spell(m, h) for m in n.midis), key=lambda x: x.midi)
            (rh2 if n.staff == "RH" else lh).add(
                Note(n.onset, n.dur, pitches, marks=list(n.marks), tuplet=n.tuplet,
                     tuplet_start=n.tuplet_start, tuplet_stop=n.tuplet_stop))
        if accompany:
            _rh_chords(rh, w, composer, ctx)
    _dynamics_for(lh, written, composer)
    if composer.prof.pedal == "harmony" and p.instrument == "piano":
        for w in written:
            for h in w.harmony:
                lh.marks.append(Mark(h.onset, "ped"))
    out = [rh, lh]
    if rh2.notes:
        out.insert(1, rh2)
    return out


def _rh_chords(rh: Voice, w, composer, ctx) -> None:
    """The accompanist's right hand: chords under the soloist, on the
    off-beats when the music moves and held when it is calm."""
    beat = composer.beat
    prev: list[int] = []
    for h in w.harmony:
        v = voicing(h, ctx, 3, 57, 74, prev, max_span=10)
        if not v:
            continue
        prev = v
        e = w.spec.energy
        pitches = [spell(m, h) for m in v]
        if e < 0.45 or w.spec.texture in ("sustained",):
            rh.add(Note(h.onset, h.dur, pitches))
            continue
        t = h.onset
        while t < h.end:
            d = min(beat, h.end - t)
            if w.spec.texture == "waltz":
                # the chord on two and three
                pos = (t - w.start) % composer.bar
                if pos == 0:
                    rh.add(Note(t, d, []))
                else:
                    rh.add(Note(t, d, pitches, marks=["stacc"] if e > 0.55 else []))
            elif e >= 0.7:
                half = d / 2
                rh.add(Note(t, half, []))
                rh.add(Note(t + half, d - half, pitches))
            else:
                rh.add(Note(t, d, pitches))
            t += d
    rh.notes = [n for n in rh.notes if n.pitches or True]


def _organ(composer, written, chords, p: PartDef) -> list[Voice]:
    """Tune and alto in the right hand, tenor in the left, bass in the pedals."""
    rh = Voice(p.id + ".RH")
    rh2 = Voice(p.id + ".RH2", secondary=True)
    lh = Voice(p.id + ".LH")
    ped = Voice(p.id + ".PED")
    for w in written:
        for n in w.melody:
            rh.add(Note(n.onset, n.dur, [n.pitch or spell(n.midi, harmony_at(w.harmony,
                                                                            n.onset))],
                        slur_start=n.slur_start, slur_stop=n.slur_stop))
    from .core import _group_tuplets
    _group_tuplets(rh.notes)
    for c in chords:
        h = c.harmony
        if c.alto is not None:
            rh2.add(Note(c.onset, c.dur, [spell(c.alto, h)]))
        if c.tenor is not None:
            lh.add(Note(c.onset, c.dur, [spell(c.tenor, h)]))
        b = _fit(c.bass, 36, 55)
        if b is not None:
            ped.add(Note(c.onset, c.dur, [spell(b, h)]))
    _dynamics_for(rh, written, composer)
    return [rh, rh2, lh, ped]


def _guitar(composer, written, chords, p: PartDef) -> Voice:
    """The tune with its bass under it wherever the two begin together."""
    v = Voice(p.id)
    bass_at = {c.onset: c for c in chords}
    for w in written:
        for n in w.melody:
            m = _fit(n.midi, 55, p.high)
            if m is None:
                continue
            h = harmony_at(w.harmony, n.onset)
            pitches = [n.pitch if m == n.midi and n.pitch else spell(m, h)]
            c = bass_at.get(n.onset)
            if c is not None:
                b = _fit(c.bass, 40, 52)
                if b is not None and m - b >= 7:
                    pitches = [spell(b, h)] + pitches
            v.add(Note(n.onset, n.dur, pitches, slur_start=n.slur_start,
                       slur_stop=n.slur_stop))
    from .core import _group_tuplets
    _group_tuplets(v.notes)
    _dynamics_for(v, written, composer)
    return v


__all__ = ["ENSEMBLE_PARTS", "LEAD_RANGE", "PartDef", "arrange", "supported", "Pitch"]
