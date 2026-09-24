"""An objective digest of a draft, for the composer's critic.

A critic reading a hundred bars of notation misses things a program counts
instantly: that the melody touches its highest note six times, that bars
17–20 are bars 1–4 again note for note, that the outer voices move in
octaves through a cadence. This report states those facts plainly, so the
critique is about the music rather than about what was noticed.
"""
from __future__ import annotations

import threading
from collections import Counter
from fractions import Fraction

from ..theory.harmony import CHORD_SPEC
from .msn import MsnPiece, bar_length, pitch_text

_NOTE = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
_STATE = threading.local()     # the key names are spelled in, per report
_QUALITIES = ("maj", "min", "dom7", "min7", "maj7", "dim", "half_dim7", "dim7", "aug", "sus4")
_SUFFIX = {"maj": "", "min": "m", "dom7": "7", "min7": "m7", "maj7": "maj7", "dim": "dim",
           "half_dim7": "m7b5", "dim7": "dim7", "aug": "+", "sus4": "sus4"}


def report(piece: MsnPiece, *, first: int | None = None, last: int | None = None) -> str:
    """The digest as text. ``first``/``last`` limit the bar-by-bar section."""
    if not piece.measures:
        return "The piece has no bars yet."
    _STATE.key = piece.key
    onsets = _onsets(piece)
    melody = _line([o for o in onsets if o[7]], top=True)
    bass = _line(onsets, top=False)
    lines: list[str] = []
    lines.append(_overview(piece))
    lines.append("")
    lines.append("Bar by bar (harmony heard | melody span | bass | dynamics):")
    for m in piece.measures:
        if first is not None and m.number < first:
            continue
        if last is not None and m.number > last:
            continue
        lines.append(_bar_line(piece, m, onsets, melody))
    lines.append("")
    lines.append(_melody_profile(melody))
    rep = _repetition(piece)
    if rep:
        lines.append("Literal repetition: " + rep)
    par = _parallels(melody, bass)
    if par:
        lines.append("Outer voices: " + par)
    lines.append(_texture(piece))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
def _abs_starts(piece: MsnPiece) -> dict[int, tuple[Fraction, Fraction]]:
    out, pos, time = {}, Fraction(0), tuple(piece.time)
    for i, m in enumerate(piece.measures):
        if m.time:
            time = tuple(m.time)
        length = bar_length(time)
        if i == 0 and m.number == 0:
            longest = max((v.duration for v in m.voices if not v.has_bar_rest),
                          default=length)
            length = longest or length
        out[m.number] = (pos, length)
        pos += length
    return out


def _onsets(piece: MsnPiece):
    """Every attack: (position, bar, offset, pitches, part, duration, tied, upper).

    ``upper`` marks lines that can carry a melody — a keyboard's right hand
    or any single-line instrument — so a left-hand arpeggio is never mistaken
    for the tune while the right hand rests.
    """
    starts = _abs_starts(piece)
    out = []
    for m in piece.measures:
        base, _ = starts[m.number]
        for vl in m.voices:
            part = piece.part(vl.part)
            upper = part is None or part.staves == 1 or vl.staff == 1
            for ev in vl.events:
                if ev.kind == "note" and ev.pitches:
                    out.append((base + ev.offset, m.number, ev.offset,
                                [p.midi for p in ev.pitches], vl.part, ev.duration,
                                any(ev.ties), upper))
    out.sort(key=lambda x: x[0])
    return out


def _line(onsets, top: bool):
    """The highest (or lowest) attacked note at each moment."""
    by_time: dict[Fraction, tuple] = {}
    for pos, bar, off, midis, part, dur, tied, upper in onsets:
        cand = max(midis) if top else min(midis)
        cur = by_time.get(pos)
        if cur is None or (cand > cur[3] if top else cand < cur[3]):
            by_time[pos] = (pos, bar, off, cand, dur)
    return [by_time[k] for k in sorted(by_time)]


def _overview(piece: MsnPiece) -> str:
    bars = len(piece.measures)
    keys = [f"{piece.key}"]
    for m in piece.measures:
        if m.key is not None:
            keys.append(f"{m.key} (m{m.number})")
    times = [f"{piece.time[0]}/{piece.time[1]}"]
    for m in piece.measures:
        if m.time:
            times.append(f"{m.time[0]}/{m.time[1]} (m{m.number})")
    tempos = [f"{piece.tempo:g}" + (f" {piece.tempo_text}" if piece.tempo_text else "")]
    for m in piece.measures:
        if m.tempo is not None or m.tempo_text:
            tempos.append((f"{m.tempo:g} " if m.tempo else "") + m.tempo_text + f" (m{m.number})")
    parts = ", ".join(p.display_name for p in piece.parts)
    return (f"{bars} bars for {parts}. Keys: {' → '.join(keys)}. "
            f"Metre: {', '.join(times)}. Tempo: {'; '.join(tempos)}.")


def _bar_line(piece: MsnPiece, m, onsets, melody) -> str:
    starts = _abs_starts(piece)
    base, length = starts[m.number]
    half = length / 2 if length >= 2 and length.denominator == 1 and int(length) % 2 == 0 \
        else length
    segments = []
    t = Fraction(0)
    while t < length:
        seg_end = min(length, t + half)
        weights: Counter[int] = Counter()
        for vl in m.voices:
            for ev in vl.events:
                if ev.kind != "note":
                    continue
                s, e = ev.offset, ev.offset + ev.duration
                overlap = min(e, seg_end) - max(s, t)
                if overlap > 0:
                    for p in ev.pitches:
                        weights[p.midi % 12] += float(overlap) * (1.5 if p.midi < 55 else 1.0)
        segments.append(_chord_name(weights) if weights else "—")
        t = seg_end
    harm = " ".join(segments)
    mel = [x for x in melody if x[1] == m.number]
    span = (f"{_n(min(x[3] for x in mel))}–{_n(max(x[3] for x in mel))}" if mel else "rest")
    lows = [min(o[3]) for o in onsets if o[1] == m.number]
    bass = _n(min(lows)) if lows else "—"
    dyn = []
    for vl in m.voices:
        for mk in vl.markings:
            if mk.kind == "dynamic":
                dyn.append(mk.value)
            elif mk.kind == "hairpin":
                dyn.append("<" if mk.value == "crescendo" else ">")
    stated = (" | stated: " + " ".join(s for _, s in m.harmony)) if m.harmony else ""
    return (f"m{m.number}: {harm} | {span} | {bass} | {' '.join(dyn) or '·'}{stated}")


def _chord_name(weights: Counter) -> str:
    best, best_score = "?", -1e9
    for root in range(12):
        for q in _QUALITIES:
            tones = {(root + s) % 12 for _, s in CHORD_SPEC[q]}
            hit = sum(weights[t] for t in tones)
            miss = sum(w for pc, w in weights.items() if pc not in tones)
            score = hit - miss * 1.3 - len(tones) * 0.15
            if weights.get(root, 0) > 0:
                score += 0.2
            if score > best_score:
                best, best_score = _STATE.key.spell(root + 60).name + _SUFFIX[q], score
    return best


def _melody_profile(melody) -> str:
    if not melody:
        return "Melody: none."
    pitches = [x[3] for x in melody]
    hi = max(pitches)
    peaks = [x for x in melody if x[3] == hi]
    steps = leaps = big = repeats = 0
    for a, b in zip(pitches, pitches[1:]):
        d = abs(b - a)
        if d == 0:
            repeats += 1
        elif d <= 2:
            steps += 1
        elif d <= 7:
            leaps += 1
        else:
            big += 1
    moves = max(1, len(pitches) - 1)
    where = ", ".join(f"m{x[1]}" for x in peaks[:6])
    return (f"Melody (top line): range {_n(min(pitches))}–{_n(hi)}; highest note {_n(hi)} "
            f"reached {len(peaks)}× ({where}); motion {100 * steps // moves}% steps, "
            f"{100 * leaps // moves}% leaps up to a fifth, {100 * big // moves}% wider leaps, "
            f"{100 * repeats // moves}% repeated notes.")


def _bar_signature(m) -> tuple:
    return tuple(sorted((vl.part, vl.staff, vl.voice,
                         tuple((tuple(p.midi for p in e.pitches), e.duration)
                               for e in vl.events)) for vl in m.voices))


def _repetition(piece: MsnPiece) -> str:
    sigs = [(m.number, _bar_signature(m)) for m in piece.measures]
    seen: dict[tuple, int] = {}
    runs: list[tuple[int, int, int]] = []          # (start, end, copy_of_start)
    i = 0
    while i < len(sigs):
        num, sig = sigs[i]
        if sig in seen and any(v for v in sig):
            src = seen[sig]
            j = 1
            while (i + j < len(sigs) and _index(sigs, src) + j < i
                   and sigs[i + j][1] == sigs[_index(sigs, src) + j][1]):
                j += 1
            if j >= 2:
                runs.append((num, sigs[i + j - 1][0], src))
                i += j
                continue
        seen.setdefault(sig, num)
        i += 1
    if not runs:
        return ""
    return "; ".join(f"m{a}–m{b} repeat m{c}–m{c + (b - a)} exactly" for a, b, c in runs[:8])


def _index(sigs, number: int) -> int:
    for i, (n, _) in enumerate(sigs):
        if n == number:
            return i
    return 0


def _parallels(melody, bass) -> str:
    """Consecutive perfect fifths or octaves between the outer voices."""
    common = {x[0]: x for x in bass}
    pairs = [(m, common[m[0]]) for m in melody if m[0] in common]
    found = []
    run = 0
    for (m1, b1), (m2, b2) in zip(pairs, pairs[1:]):
        i1 = (m1[3] - b1[3]) % 12
        i2 = (m2[3] - b2[3]) % 12
        moved = m2[3] != m1[3] and b2[3] != b1[3]
        same_dir = (m2[3] - m1[3]) * (b2[3] - b1[3]) > 0
        if moved and same_dir and i1 == i2 and i1 in (0, 7) and m1[3] != b1[3]:
            run += 1
            kind = "octaves" if i1 == 0 else "fifths"
            found.append(f"parallel {kind} into m{m2[1]} beat {float(m2[2] + 1):g}")
        else:
            run = 0
    if not found:
        return ""
    if len(found) > 6:
        return (f"{len(found)} parallel perfect intervals between melody and bass, e.g. "
                + "; ".join(found[:4]) + " (octave doubling passages count here too)")
    return "; ".join(found)


def _texture(piece: MsnPiece) -> str:
    counts: Counter[str] = Counter()
    per_bar: list[tuple[int, int]] = []
    for m in piece.measures:
        n = 0
        for vl in m.voices:
            k = sum(len(e.pitches) for e in vl.events if e.kind == "note")
            counts[vl.label or vl.part] += k
            n += k
        per_bar.append((n, m.number))
    if not per_bar:
        return ""
    avg = sum(n for n, _ in per_bar) / len(per_bar)
    dense = sorted(per_bar, reverse=True)[:3]
    sparse = sorted(per_bar)[:3]
    return (f"Texture: {avg:.1f} notes per bar on average; densest "
            + ", ".join(f"m{b} ({n})" for n, b in dense) + "; sparsest "
            + ", ".join(f"m{b} ({n})" for n, b in sparse) + ".")


def _n(midi: int) -> str:
    return pitch_text(_STATE.key.spell(midi))
