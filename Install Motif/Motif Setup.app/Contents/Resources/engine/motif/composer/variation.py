"""Variation: the theme made new while its phrases and harmony stay.

A set of variations keeps what the listener holds on to — the theme's
phrases, its cadences, its chords — and changes what the ear notices first:
the rhythm of the tune (a figuration that decorates each of its notes on the
way to the next), its mode (the *minore*), its register (the tune in the
left hand), its tempo and its dress.

The figuration is found, note by note, by dynamic programming: each note of
the theme becomes a run of shorter notes that starts on it, keeps chord
tones on the beats, lets passing and neighbour notes move only by step, and
arrives by step at the theme's next note. The variation then prefers the
figure it has used most, so it sounds like one idea carried through rather
than a different decoration on every beat.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from fractions import Fraction as F

from ..theory.pitch import _MAJOR_FIFTHS, _MINOR_FIFTHS, Key, Pitch
from .harmony import Harmony, _melody_weights, chord_for, core, harmony_at, spell
from .melody import MelNote, _crooked, _degree_of, _move_to_key, respell_line


# ---------------------------------------------------------------------------
# keys and modes
# ---------------------------------------------------------------------------
def parallel_key(key: Key) -> Key:
    """The key's other mode on the same tonic, spelled so it has a real key
    signature: D flat major's minore is in C sharp minor."""
    p = key.parallel
    table = _MINOR_FIFTHS if p.is_minor else _MAJOR_FIFTHS
    if abs(table.get(p.tonic, 99)) <= 7:
        return p
    same = [name for name in table if abs(table[name]) <= 7 and
            Key(name, p.mode).tonic_pc == p.tonic_pc]
    if not same:
        return p
    return Key(min(same, key=lambda n: abs(table[n])), p.mode)


_TO_MINOR = {"I": "i", "iii": "III", "IV": "iv", "V": "V", "v": "v", "vi": "VI",
             "bVI": "VI", "bIII": "III", "bVII": "bVII", "iv": "iv", "i": "i", "II": "II",
             "bII": "bII", "VI": "VI", "III": "III"}
_TO_MAJOR = {"i": "I", "III": "iii", "iv": "IV", "V": "V", "v": "V", "VI": "vi",
             "bVII": "bVII", "I": "I", "IV": "IV", "bII": "bII", "bIII": "bIII", "bVI": "bVI",
             "iii": "iii", "vi": "vi", "II": "II"}
_SEVENTH_FIGURES = ("7", "65", "43", "42")


def mode_roman(roman: str, minor: bool) -> str:
    """The same chord, degree for degree, in the other mode: I becomes i, IV
    becomes iv and vi becomes VI in the minore — and back again."""
    if roman[:2] in ("It", "Fr", "Ge", "Ca") or roman.startswith("N"):
        return roman
    if "/" in roman:
        head, target = roman.split("/", 1)
        new_target = mode_roman(target, minor)
        c = core(new_target)
        if "o" in new_target or "%" in new_target or c in ("ii", "vii"):
            # a diminished chord cannot be tonicised: lead to it from VI instead
            return "VI" if minor else new_target
        return f"{head}/{c}"
    c = core(roman)
    rest = roman[len(c):] if roman.startswith(c) else ""
    colour = ""
    if "(" in rest:
        rest, colour = rest.split("(", 1)
        colour = "(" + colour
    fig = rest.replace("o", "").replace("%", "")
    seventh = fig.startswith(_SEVENTH_FIGURES)
    if minor:
        if c == "ii":
            return ("ii%" if seventh else "iio") + fig
        if c in ("vii", "viio"):
            return "viio" + fig
        new = _TO_MINOR.get(c, c)
        if colour not in ("(add6)", "(add9)") or new != "i":
            colour = ""
        if colour == "" and c in ("I", "IV") and "(maj7)" in roman:
            fig = fig or "7"
        return new + fig + colour
    if c in ("ii", "iio"):
        return "ii" + fig
    if c in ("vii", "viio"):
        return "viio" + fig
    new = _TO_MAJOR.get(c, c)
    if new in ("iii", "vi") and "(maj7)" in roman:
        return new + "7"
    if colour not in ("(add6)", "(add9)") or new != "I":
        colour = ""
    return new + fig + colour


def change_mode(harmony: list[Harmony], melody: list[MelNote], old: Key, new: Key,
                beat: F) -> tuple[list[Harmony], list[MelNote]]:
    """The theme in the other mode: every chord mapped degree for degree,
    every note of the tune moved to the new scale — keeping the leading tone
    wherever the dominant needs it — and a chord that would then fight the
    tune replaced by the plainest chord of its function."""
    minor = new.is_minor
    out_h: list[Harmony] = []
    for h in harmony:
        label = mode_roman(h.roman, minor)
        try:
            chord_for(label, new)
        except Exception:
            label = {"T": "i" if minor else "I", "S": "iv" if minor else "IV"}.get(
                h.function, "V")
        out_h.append(Harmony(label, new, h.onset, h.dur, cadence=h.cadence,
                             pedal=h.pedal))
    notes = sorted(melody, key=lambda n: n.onset)
    moved: list[MelNote] = []
    for i, n in enumerate(notes):
        h_old = harmony_at(harmony, n.onset)
        h_new = harmony_at(out_h, n.onset)
        m = _move_to_key(n.midi, old, new)
        was_ct = n.midi % 12 in h_old.pcs
        if m % 12 not in h_new.pcs:
            for alt in (n.midi, m + 1, m - 1):
                if alt % 12 in h_new.pcs and (was_ct or alt == n.midi):
                    m = alt
                    break
        moved.append(MelNote(n.onset, n.dur, m, None, n.role, list(n.marks), n.tie,
                             list(n.graces), n.slur_start, n.slur_stop))
    for a, b, (oa, ob) in zip(moved, moved[1:], zip(notes, notes[1:])):
        if a.midi == b.midi and oa.midi != ob.midi and abs(oa.midi - ob.midi) == 1:
            a.midi = oa.midi          # a chromatic step stays a step, not a repeated note
    if minor:
        _melodic_minor(moved, out_h, new)
    for i, h in enumerate(out_h):
        # a chord the moved tune now fights gives way to the plainest one of its kind
        weights = _melody_weights(moved, h, beat)
        clash = sum(w for pc, w in weights if pc not in h.pcs)
        if clash > 1.5 and not h.cadence:
            plain = {"T": "i" if minor else "I", "S": "iv" if minor else "IV",
                     "D": "V"}.get(h.function, "V")
            alt = Harmony(plain, new, h.onset, h.dur, cadence=h.cadence, pedal=h.pedal)
            if sum(w for pc, w in weights if pc not in alt.pcs) < clash:
                out_h[i] = alt
    for n in moved:
        n.pitch = spell(n.midi, harmony_at(out_h, n.onset))
    respell_line(moved, out_h, new)
    return out_h, moved


def _melodic_minor(notes: list[MelNote], harmony: list[Harmony], key: Key) -> None:
    """Minor's sixth and seventh as a singer takes them: the seventh raised
    when it leads to the tonic or sounds over the dominant, the sixth raised
    on the way up to a raised seventh (no augmented second)."""
    t = key.tonic_pc
    for i, n in enumerate(notes):
        rel = (n.midi - t) % 12
        nxt = notes[i + 1] if i + 1 < len(notes) else None
        h = harmony_at(harmony, n.onset)
        if rel == 10 and (h.function == "D" or (nxt is not None and nxt.midi - n.midi == 2
                                                  and (nxt.midi - t) % 12 == 0)):
            n.midi += 1
    for i, n in enumerate(notes[:-1]):
        rel = (n.midi - t) % 12
        nxt = notes[i + 1]
        if rel == 8 and (nxt.midi - t) % 12 == 11 and nxt.midi > n.midi:
            n.midi += 1


# ---------------------------------------------------------------------------
# figuration
# ---------------------------------------------------------------------------
def figurate(melody: list[MelNote], harmony: list[Harmony], key: Key, start: F, unit: F,
             beat: F, bar: F, low: int, high: int, leaps: float = 0.5,
             avoid: set | None = None, adagio: bool = False, rng=None,
             reach: int = 9, sweep: bool = False) -> list[MelNote]:
    """Diminution: each note of the tune (from ``start``, all but the last)
    becomes a run of notes of value ``unit`` that begins on it and finds its
    way to the next. ``leaps`` is how readily the figure arpeggiates rather
    than moving by step (Romantic figuration leaps more). A figure already
    used by an earlier variation (in ``avoid``) is not made the leading one
    again, and the one chosen is added to it.

    An ``adagio`` figuration keeps the theme's long notes and decorates only
    their last beat on the way to the next note — and some single beats —
    as a slow variation sings."""
    notes = sorted(melody, key=lambda n: n.onset)
    if _crooked(unit) != _crooked(beat) and not adagio:
        # triplets run through whole beats: the tune's note on each beat is
        # its skeleton, and what fell between the beats gives way
        notes = _skeleton(notes, start, beat)
    group = int(beat / unit) if (beat / unit).denominator == 1 else 0
    avoid = avoid if avoid is not None else set()
    signature: tuple[int, ...] | None = None
    plans: list[F | None] = []          # per note: how long it is held before its figure
    for i, n in enumerate(notes):
        nxt = notes[i + 1] if i + 1 < len(notes) else None
        hold: F | None = None
        if n.onset >= start and nxt is not None and _can_figure(n, unit, beat):
            if not adagio:
                hold = F(0)
            elif n.dur >= 2 * beat and (n.onset + n.dur - beat) % beat == 0:
                hold = n.dur - beat
            elif n.dur == beat and (rng is None or rng.random() < 0.5):
                hold = F(0)
        plans.append(hold)
    out: list[MelNote] = []
    for rnd in (0, 1):
        out = []
        shapes: Counter = Counter()
        for i, n in enumerate(notes):
            fig = None
            if plans[i] is not None:
                fig = _figure(n, notes[i + 1], harmony, key, unit, beat, bar, low, high, leaps,
                              signature, group, plans[i], reach, sweep)
            if fig is None:
                out.append(replace(n, marks=list(n.marks), graces=list(n.graces)))
                continue
            out.extend(fig)
            run = [x for x in fig if x.dur == unit]
            if group and len(run) >= group and run[0].onset % beat == 0:
                shapes[_shape(run[:group], key)] += 1
        if rnd == 0:
            fresh = [(c, sh) for sh, c in shapes.items() if sh not in avoid]
            if not fresh:
                break
            signature = max(fresh)[1]
            avoid.add(signature)
    for n in out:
        if n.pitch is None:
            n.pitch = spell(n.midi, harmony_at(harmony, n.onset))
    respell_line([n for n in out if n.onset >= start], harmony, key)
    return out


def _skeleton(notes: list[MelNote], start: F, beat: F) -> list[MelNote]:
    """The tune reduced to the note sounding at each beat (from ``start``),
    a note held over several beats kept as one; the last note and anything
    before ``start`` stay as they were."""
    if len(notes) < 2:
        return notes
    last = notes[-1]
    before = [n for n in notes if n.onset < start]
    body = [n for n in notes if start <= n.onset < last.onset]
    if not body:
        return notes
    out: list[MelNote] = []
    t = body[0].onset if body[0].onset % beat == 0 else body[0].onset + (-body[0].onset) % beat
    lead = [n for n in body if n.onset < t]
    out.extend(lead)
    while t < last.onset:
        sounding = next((n for n in reversed(body) if n.onset <= t), None)
        if sounding is None:
            t += beat
            continue
        end = min(last.onset, t + beat)
        if out and out[-1].midi == sounding.midi and out[-1].end == t and \
                out[-1] is not sounding and sounding.onset < t:
            out[-1] = replace(out[-1], dur=out[-1].dur + (end - t))
        else:
            out.append(replace(sounding, onset=t, dur=end - t, marks=list(sounding.marks),
                               graces=list(sounding.graces) if sounding.onset == t else []))
        t = end
    return before + out + [last]


def _can_figure(n: MelNote, unit: F, beat: F) -> bool:
    k = n.dur / unit
    if k.denominator != 1 or k < 2:
        return False
    if _crooked(unit):
        # triplets fill whole beats only
        return n.onset % beat == 0 and n.dur % beat == 0
    return not _crooked(n.onset) and not _crooked(n.dur)


def _shape(fig: list[MelNote], key: Key) -> tuple[int, ...]:
    steps = [_degree_of(n.midi, key)[0] for n in fig]
    return tuple(b - a for a, b in zip(steps, steps[1:]))


def _strength(t: F, beat: F, unit: F, bar: F) -> int:
    pos = t % bar
    if pos % beat == 0:
        return 2
    if unit < beat / 2 and not _crooked(beat / 2) and pos % (beat / 2) == 0:
        return 1
    return 0


def _figure(n: MelNote, nxt: MelNote, harmony: list[Harmony], key: Key, unit: F, beat: F,
            bar: F, low: int, high: int, leaps: float, signature, group: int, hold: F = F(0),
            reach: int = 9, sweep: bool = False) -> list[MelNote] | None:
    """The best figure from note ``n`` to ``nxt``: slot 0 is the note itself
    (sounding for ``hold``, or one ``unit`` when there is no hold), and every
    later slot is a ``unit`` chosen by dynamic programming."""
    first = hold if hold else unit
    k = int((n.dur - first) / unit) + 1            # slots, the first included
    times = [n.onset] + [n.onset + first + unit * (j - 1) for j in range(1, k)]
    hs = [harmony_at(harmony, t) for t in times]
    scale = set(key.scale_pcs)
    if key.is_minor:
        scale |= {(key.tonic_pc + 11) % 12}
    lo, hi = max(low, n.midi - reach), min(high, n.midi + reach)
    target = nxt.midi
    cands: list[list[int]] = [[n.midi]]
    for j in range(1, k):
        allowed = scale | hs[j].pcs
        if key.is_minor and hs[j].function == "D":
            allowed.discard((key.tonic_pc + 10) % 12)
        cands.append([m for m in range(lo, hi + 1) if m % 12 in allowed])
    strength = [_strength(t, beat, unit, bar) for t in times]
    phase = [int((t % beat) / unit) if (t % beat) / unit == int((t % beat) / unit) else 0
             for t in times]
    deg: dict[int, int] = {}

    def degree(m: int) -> int:
        if m not in deg:
            deg[m] = _degree_of(m, key)[0]
        return deg[m]

    def ct(j: int, m: int) -> bool:
        return m % 12 in hs[j].pcs

    def node(j: int, m: int) -> float:
        if ct(j, m) or not strength[j]:
            return 0.0
        return 3.0 if strength[j] == 2 else 0.8

    arpeggio = leaps >= 0.75           # figures that break the chord rather than run

    def pair(j: int, a: int, b: int) -> float:
        """Moving from slot j-1 (pitch a) to slot j (pitch b)."""
        iv = abs(b - a)
        both = ct(j - 1, a) and ct(j, b)
        if iv == 0:
            return 1.6
        if iv <= 2:
            return 0.25 if arpeggio else 0.0
        if not both:
            return 1.6 if iv <= 4 else 3.5 if iv <= 9 else 4.0
        if arpeggio:
            return 0.05 + 0.03 * (iv - 3) if iv <= 9 else 4.0
        if iv <= 4:
            return 0.35 * (1 - leaps) + 0.1
        if iv <= 9:
            return 0.6 * (1 - leaps) + 0.25 + 0.08 * (iv - 5)
        return 4.0

    def motif_bonus(j: int, a: int, b: int) -> float:
        if not signature or not group:
            return 0.0
        pos = phase[j]
        if pos == 0 or pos - 1 >= len(signature):
            return 0.0
        return -0.55 if degree(b) - degree(a) == signature[pos - 1] else 0.0

    # states: (previous pitch, current pitch) -> (cost, path)
    states: dict[tuple[int | None, int], tuple[float, list[int]]] = {
        (None, n.midi): (0.0, [n.midi])}
    for j in range(1, k):
        nxt_states: dict[tuple[int | None, int], tuple[float, list[int]]] = {}
        for (prev, cur), (cost, path) in states.items():
            for m in cands[j]:
                if hold and j == 1 and m == cur:
                    continue                   # a held note is not struck again
                c = cost + node(j, m) + pair(j, cur, m) + motif_bonus(j, cur, m)
                if prev is not None and not ct(j - 1, cur):
                    # a note outside the chord is approached and left by step
                    if abs(cur - prev) > 2 or abs(m - cur) > 2:
                        c += 2.5
                    elif (cur - prev) * (m - cur) > 0 and strength[j - 1] > 0:
                        c += 0.4               # an accented passing note is weaker
                if sweep:
                    # a run sweeps on in one direction rather than circling
                    if prev is not None:
                        c += -0.45 if (cur - prev) * (m - cur) > 0 else 0.45
                elif prev is not None and abs(cur - prev) >= 5 and (m - cur) * (cur - prev) > 0 \
                        and abs(m - prev) > 9:
                    c += 1.0                   # two leaps the same way past a ninth
                if not sweep:
                    c += 0.04 * abs(m - n.midi)
                key2 = (cur, m)
                if key2 not in nxt_states or c < nxt_states[key2][0]:
                    nxt_states[key2] = (c, path + [m])
        states = nxt_states
        if not states:
            return None
    best, best_path = 1e9, None
    for (prev, cur), (cost, path) in states.items():
        iv = abs(target - cur)
        c = cost + (0.0 if 1 <= iv <= 2 else 0.4 if iv <= 4 else 1.4 if iv == 0 else
                    1.6 + 0.1 * iv)
        if not ct(k - 1, cur) and (iv > 2 or iv == 0):
            c += 2.5
        if c < best:
            best, best_path = c, path
    if best_path is None or best > 3.0 * k:
        return None
    out = []
    for j, m in enumerate(best_path):
        role = "CT" if ct(j, m) else "PT"
        note = MelNote(times[j], first if j == 0 else unit, m, None, role,
                       list(n.marks) if j == 0 else [])
        if j == 0:
            note.slur_start = n.slur_start
            note.graces = list(n.graces)
            note.pitch = n.pitch
        if j == k - 1:
            note.slur_stop = n.slur_stop
        out.append(note)
    return out


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------
def to_tenor(melody: list[MelNote], low: int = 47, high: int = 66) -> list[MelNote]:
    """The tune an octave (or two) lower, where the left hand can sing it."""
    if not melody:
        return melody
    top = max(n.midi for n in melody)
    bottom = min(n.midi for n in melody)
    shift = 0
    while top + shift > high and bottom + shift - 12 >= low - 5:
        shift -= 12
    out = []
    for n in melody:
        p = n.pitch
        new = replace(n, midi=n.midi + shift, marks=list(n.marks), graces=[])
        if p is not None:
            new.pitch = Pitch.build(p.step, p.alter, p.octave + shift // 12)
        out.append(new)
    return out
