"""Harmonising a melody the musician wrote.

The tune on the page is kept exactly as it is. Underneath it Motif chooses a
chord for every half bar — the whole bar when one chord serves it — by
dynamic programming over the composer's own vocabulary: every chord is
scored for how well it fits the notes above it (long and accented notes must
belong to it; quick passing notes need not), every change of chord for how
naturally one function leads to the next, and every fourth bar for the
cadence a phrase wants there. The chosen progression is then laid out in the
composer's accompaniment idiom, under the tune and inside the hand.
"""
from __future__ import annotations

import random
from fractions import Fraction as F

from ..control import Progress, report
from ..notation import parse as parse_msn
from ..notation.to_score import to_score
from ..score import Score
from ..theory.pitch import Key
from .harmony import (Harmony, core, function_of, harmony_at, harmony_style, spell,
                      _applied_target, _goes_to, _merge_repeats)
from .listen import _top_line
from .notation import Mark, Note, Sheet, Voice, bar_length, beat_length, group_tuplets
from .profiles import profile
from .texture import TextureContext, realise

#: Chords worth considering under a tune, beyond the style's own vocabulary.
_DIATONIC = {
    "major": ["I", "ii", "iii", "IV", "V", "vi", "V7", "ii7", "IV(maj7)", "vi7", "I6", "V65",
              "V7/V", "V7/ii", "V7/vi", "V7/IV", "viio7", "iv", "Cad64"],
    "minor": ["i", "iio", "III", "iv", "V", "VI", "bVII", "V7", "ii%7", "iv7", "VI(maj7)",
              "i6", "V65", "V7/iv", "V7/VI", "V7/III", "viio7", "N6", "Cad64"],
}


def _vocabulary(style, key: Key) -> list[str]:
    mode = "minor" if key.is_minor else "major"
    seen: list[str] = []
    pools = [style.tonic[mode], style.predominant[mode], style.dominant[mode]]
    pools += [c[mode] for c in style.cadence.values()]
    for pool in pools:
        for _w, pat in pool:
            for r in pat:
                if r not in seen:
                    seen.append(r)
    for r in _DIATONIC[mode]:
        if r not in seen:
            seen.append(r)
    return seen


def _fit_cost(chord: Harmony, notes, beat: F) -> float:
    """How badly a chord fits the tune sounding over it."""
    cost = 0.0
    pcs = chord.pcs
    for k, (on, d, midi) in enumerate(notes):
        a, b = max(on, chord.onset), min(on + d, chord.end)
        if b <= a:
            continue
        w = float(b - a) * (2.0 if (on >= chord.onset and (on - chord.onset) % beat == 0)
                            else 1.0)
        if midi % 12 in pcs:
            continue
        prev = notes[k - 1][2] if k else None
        nxt = notes[k + 1][2] if k + 1 < len(notes) else None
        passing = (prev is not None and nxt is not None and abs(midi - prev) <= 2 and
                   abs(nxt - midi) <= 2 and d <= beat)
        cost += w * (0.2 if passing else 1.0)
    return cost


def _move_cost(a: str, b: str, same_bar: bool) -> float:
    if a == b or (core(a) == core(b) and "/" not in a and "/" not in b):
        # the same harmony held: natural within a bar, static across bars
        return (0.0 if a == b else 0.3) if same_bar else 0.9
    fa, fb = function_of(a), function_of(b)
    c = 0.0
    if fa == "D" and fb == "S" and "/" not in a:
        c += 1.6                                   # retrogression
    if fa == "T" and fb == "D":
        c += 0.2
    if fa == "S" and fb == "T":
        c += 0.3
    tgt = _applied_target(a)
    if tgt is not None and not _goes_to(b, tgt):
        c += 3.0
    if a.startswith("Cad") and core(b) != "V":
        c += 3.0
    if same_bar:
        c += 0.6                                   # prefer one chord a bar
    return c


def choose_chords(line, key: Key, time: tuple[int, int], bars: int, style,
                  width: int = 12) -> list[Harmony]:
    """The progression under the tune: a chord per half bar (merged where one
    chord serves the whole bar), by dynamic programming."""
    bar = bar_length(time)
    beat = beat_length(time)
    half = bar / 2 if time[0] % 2 == 0 or time[1] == 8 else bar
    slots = []
    t = F(0)
    while t < bar * bars:
        slots.append((t, half))
        t += half
    notes = [(on, d, midi) for on, d, midi, _b in line]
    vocab = _vocabulary(style, key)
    tonic = "i" if key.is_minor else "I"
    # best[j][label] = (cost, back-pointer label)
    prev_layer: dict[str, tuple[float, str | None]] = {}
    back: list[dict[str, str | None]] = []
    for j, (on, d) in enumerate(slots):
        layer: dict[str, tuple[float, str | None]] = {}
        bar_index = int(on / bar)
        in_bar = on % bar
        last_slot = j == len(slots) - 1
        for r in vocab:
            try:
                h = Harmony(r, key, on, d)
            except Exception:
                continue
            fit = _fit_cost(h, notes, beat)
            local = fit
            # plain chords before coloured ones, unless the tune asks: a chord
            # with many notes fits any tune, which is no reason to choose it
            local += 0.3 * max(0, len(h.pcs) - 3)
            if "/" in r:
                local += 0.45
            elif "(" in r or r.startswith(("N", "Cad", "It", "Fr", "Ge")):
                local += 0.25
            # phrase shape: begin at home, pause on the dominant every fourth
            # bar, and close on the tonic after a dominant
            if j == 0:
                local += 0.0 if r == tonic else 2.5
            if (bar_index + 1) % 8 == 4 and in_bar >= bar / 2 - F(1, 1000) and \
                    bar_index < bars - 1:
                local += 0.0 if core(r) == "V" and "/" not in r else 0.8
            if last_slot:
                local += 0.0 if r == tonic else 4.0
            if not prev_layer:
                layer[r] = (local, None)
                continue
            best, arg = 1e18, None
            for pr, (pc, _b) in prev_layer.items():
                c = pc + local + _move_cost(pr, r, same_bar=in_bar != 0)
                if last_slot and function_of(pr) != "D" and r == tonic:
                    c += 1.5
                if c < best:
                    best, arg = c, pr
            layer[r] = (best, arg)
        # keep the most promising
        keep = sorted(layer.items(), key=lambda kv: kv[1][0])[:max(width, 8)]
        prev_layer = dict(keep)
        back.append({k: v[1] for k, v in keep})
    # trace back
    label = min(prev_layer, key=lambda k: prev_layer[k][0])
    labels = [label]
    for j in range(len(slots) - 1, 0, -1):
        label = back[j].get(label) or label
        labels.append(label)
    labels.reverse()
    hs = [Harmony(r, key, on, d) for r, (on, d) in zip(labels, slots)]
    if hs:
        hs[-1].cadence = "PAC"
    return _merge_repeats(hs)


def harmonize_score(existing: Score, style_name: str, *, quality: str = "best",
                    progress=None, seed: int = 0, title: str = "") -> tuple[Score, list[str]]:
    """A piano score with the tune of ``existing`` on top and an accompaniment
    under it (the tune itself is grafted back from the original afterwards)."""
    report(progress, Progress("planning", "Listening to your melody", "", 0.05))
    key = existing.key or Key("C", "major")
    time = tuple(existing.time)
    bars = max(1, existing.measure_count)
    prof = profile(style_name)
    style = harmony_style(prof.harmony)
    line = _top_line(existing)
    rng = random.Random(seed)
    width = {"sketch": 8, "balanced": 12, "best": 20, "maximum": 32}.get(quality, 20)
    report(progress, Progress("writing", "Choosing the harmony", "", 0.3))
    harmonies = choose_chords(line, key, time, bars, style, width=width)
    report(progress, Progress("writing", "Writing the accompaniment", "", 0.7))
    bar = bar_length(time)
    beat = beat_length(time)
    rh, rh2, lh = Voice("RH"), Voice("RH2", secondary=True), Voice("LH")
    for on, d, midi, _b in line:
        h = harmony_at(harmonies, on)
        rh.add(Note(on, d, [spell(midi, h)]))
    group_tuplets(rh.notes)
    ctx = TextureContext(time, bar, beat, key, bass_low=prof.bass_low, rng=rng,
                         grand=prof.harmony not in ("classical", "baroque"))
    lows, highs = {}, {}
    t = F(0)
    while t < bar * bars:
        ps = [n.pitches[0].midi for n in rh.notes if n.onset < t + bar / 2 and n.end > t]
        if ps:
            lows[(t, t + bar / 2)] = min(ps)
            highs[(t, t + bar / 2)] = max(ps)
        t += bar / 2
    ctx.melody_floor, ctx.melody_top = lows, highs
    options = prof.textures.get("theme") or ["block"]
    texture = rng.choice(options)
    if texture in ("bells", "sweep16"):
        texture = "nocturne"
    tex = realise(texture, harmonies, F(0), bar * bars, ctx)
    for n in tex:
        h = harmony_at(harmonies, n.onset)
        pitches = sorted((spell(m, h) for m in n.midis), key=lambda p: p.midi)
        (rh2 if n.staff == "RH" else lh).add(
            Note(n.onset, n.dur, pitches, marks=list(n.marks), tuplet=n.tuplet,
                 tuplet_start=n.tuplet_start, tuplet_stop=n.tuplet_stop))
    lh.marks.append(Mark(F(0), "dyn", "p"))
    if prof.pedal == "harmony":
        for h in harmonies:
            lh.marks.append(Mark(h.onset, "ped"))
    tempo, tempo_text = page_tempo(existing, time)
    sheet = Sheet(title=title or existing.title or "Untitled", key=key, time=time,
                  tempo=tempo, tempo_text=tempo_text, composer="Motif.AI", bars=bars,
                  parts=[("Pno", "piano", "")])
    sheet.voices = [rh, rh2, lh]
    msn = sheet.to_msn()
    score, _issues = to_score(parse_msn(msn))
    report(progress, Progress("finishing", "Engraving the score", "", 0.95))
    progression = " ".join(h.roman for h in harmonies[:12])
    notes = [f"Harmony chosen for your tune: {progression}{' …' if len(harmonies) > 12 else ''}",
             f"Accompaniment: {texture.replace('_', ' ')} in the manner of {prof.display}."]
    return score, notes


def page_tempo(existing: Score, time: tuple[int, int]) -> tuple[float, str]:
    """The piece's own opening tempo, counted in the beat of its metre (a
    dotted quarter in 6/8), and the word it is marked with ("Largo")."""
    first = next((t for t in existing.tempos if t.visible), None)
    quarters = first.quarter_bpm if first else float(existing.tempo or 90)
    beats, unit = time
    per_beat = 1.5 if (unit == 8 and beats % 3 == 0 and beats > 3) else 4.0 / unit
    return round(quarters / per_beat, 2), (first.text if first else "")


def arrange_score(existing: Score, ensemble: str, style_name: str, *, quality: str = "best",
                  progress=None, seed: int = 0, title: str = ""):
    """The tune of ``existing`` scored for ``ensemble``: its harmony worked
    out under it as when harmonising, then handed to the instruments by the
    composer's arranger — the tune to the lead, inner voices led beneath it,
    the bass its own line. Returns (score, notes, composer)."""
    from ..plan import CompositionPlan
    from .core import Composer, Written
    from .form import PhraseSpec
    from .melody import MelNote
    report(progress, Progress("planning", "Listening to your piece", "", 0.05))
    key = existing.key or Key("C", "major")
    time = tuple(existing.time)
    bars = max(1, existing.measure_count)
    prof = profile(style_name)
    style = harmony_style(prof.harmony)
    line = _top_line(existing)
    width = {"sketch": 8, "balanced": 12, "best": 20, "maximum": 32}.get(quality, 20)
    report(progress, Progress("writing", "Working out the harmony", "", 0.3))
    harmonies = choose_chords(line, key, time, bars, style, width=width)
    tempo, tempo_text = page_tempo(existing, time)
    plan = CompositionPlan(title=title or existing.title or "Untitled", key=str(key),
                           time=time, tempo=int(round(tempo)), tempo_given=True,
                           time_given=True, style=prof.name, ensemble=ensemble, seed=seed,
                           prompt="")
    composer = Composer(plan, quality=quality, progress=progress, seed=seed)
    composer.tempo_text = tempo_text
    bar = bar_length(time)
    texture = (prof.textures.get("theme") or ["block"])[0]
    written = []
    phrase_bars = 4
    for start_bar in range(0, bars, phrase_bars):
        n = min(phrase_bars, bars - start_bar)
        t0, t1 = bar * start_bar, bar * (start_bar + n)
        hs = [h for h in harmonies if t0 <= h.onset < t1]
        if not hs:
            continue
        mel = []
        for on, d, midi, _b in line:
            if t0 <= on < t1:
                h = harmony_at(harmonies, on)
                mel.append(MelNote(on, d, midi, spell(midi, h)))
        last = start_bar + n >= bars
        spec = PhraseSpec("A", "theme", "sentence", n, key, "PAC" if last else "HC",
                          0.5, texture, new_section=start_bar == 0)
        written.append(Written(spec, t0, hs, mel, []))
    report(progress, Progress("writing", "Scoring it for the instruments", "", 0.7))
    sheet = composer._ensemble_sheet(written, bar * bars) if ensemble != "solo_piano" else None
    if sheet is None:
        raise ValueError("arranging for solo piano is harmonising")
    msn = sheet.to_msn()
    score, _issues = to_score(parse_msn(msn))
    report(progress, Progress("finishing", "Engraving the score", "", 0.95))
    notes = [f"Harmony under your tune: {' '.join(h.roman for h in harmonies[:12])}"
             f"{' …' if len(harmonies) > 12 else ''}"]
    return score, notes, composer
