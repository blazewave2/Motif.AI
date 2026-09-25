"""Analyse an existing score so the agent can respond to what is on the page."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..compose.styles import STYLES
from ..score import DIVISIONS, Score
from ..theory.harmony import CHORD_SPEC, Chord
from ..theory.pitch import Key, Pitch


@dataclass
class ScoreAnalysis:
    key: Key = field(default_factory=Key)
    time: tuple[int, int] = (4, 4)
    tempo: float = 100.0
    bars: int = 0
    parts: int = 1
    range_low: int = 60
    range_high: int = 72
    density: float = 0.5
    chromaticism: float = 0.0
    polyphony: float = 1.0
    ornament_rate: float = 0.0
    tempo_span: float = 0.0
    last_melody_pitch: Pitch | None = None
    #: Where the piece has got to by its last bar — the key, metre and tempo
    #: a continuation picks up from (the tempo in beats of that metre).
    end_key: Key | None = None
    end_time: tuple[int, int] | None = None
    end_tempo: float | None = None
    final_chord_pcs: tuple[int, ...] = ()
    detected_style: str = "classical"
    style_is_exact: bool = False        # read from the file, not guessed
    ensemble: str = ""                  # read from the file, when known
    chord_summary: list[str] = field(default_factory=list)
    note_count: int = 0
    is_empty: bool = True

    def describe(self) -> str:
        if self.is_empty:
            return "The score is empty."
        style_line = (f"Style: {STYLES[self.detected_style].display}." if self.style_is_exact
                     else f"Closest style match: {STYLES[self.detected_style].display}.")
        return (f"{self.bars} bars in {self.key}, {self.time[0]}/{self.time[1]}, "
                f"♩ = {int(self.tempo)}, {self.parts} part(s), "
                f"range {self.key.spell(self.range_low)}\u2013{self.key.spell(self.range_high)}. "
                f"{style_line}")


def analyse(score: Score) -> ScoreAnalysis:
    a = ScoreAnalysis(key=score.key, time=tuple(score.time), tempo=score.tempo,
                      bars=score.measure_count, parts=len(score.parts))
    pitches: list[int] = []
    durations: list[int] = []
    ornamented = 0
    last: Pitch | None = None
    for part in score.parts:
        for m in part.measures:
            for voice in sorted(m.voices):
                for n in m.voices[voice]:
                    if n.is_rest or n.grace:
                        continue
                    durations.append(n.duration)
                    if n.ornaments:
                        ornamented += 1
                    for p in n.pitches:
                        pitches.append(p.midi)
    if not pitches:
        return a
    a.is_empty = False
    a.note_count = len(durations)
    a.range_low, a.range_high = min(pitches), max(pitches)
    avg = sum(durations) / len(durations)
    a.density = max(0.0, min(1.0, 1.0 - (avg / (DIVISIONS * 2))))
    a.polyphony = len(pitches) / len(durations)
    a.ornament_rate = ornamented / len(durations)
    if score.tempos:
        a.tempo_span = max(t.bpm for t in score.tempos) - min(t.bpm for t in score.tempos)

    top = score.parts[0]
    for m in reversed(top.measures):
        v = min(m.voices) if m.voices else None
        if v is None:
            continue
        for n in reversed(m.voices[v]):
            if n.pitches and not n.grace:
                last = max(n.pitches, key=lambda p: p.midi)
                break
        if last:
            break
    a.last_melody_pitch = last

    a.key = detect_key(pitches, score.key)
    _read_the_ending(a, score)
    a.chromaticism = sum(1 for p in pitches if p % 12 not in set(a.key.scale_pcs)) / len(pitches)

    # A score Motif itself wrote carries its exact composer and forces as
    # miscellaneous fields; read those back rather than re-guessing from the
    # notes, which is only ever an approximation. Anything else — a score
    # written by hand, or edited enough that the guess is worth trusting —
    # falls back to the heuristic below.
    recorded_style = score.metadata.get("style")
    if recorded_style in STYLES:
        a.detected_style = recorded_style
        a.style_is_exact = True
    else:
        a.detected_style = detect_style(a)
    a.ensemble = score.metadata.get("ensemble", "")

    a.chord_summary = summarise_harmony(score, a.key)
    if a.chord_summary:
        a.final_chord_pcs = tuple(sorted({p % 12 for p in pitches[-6:]}))
    return a


def _read_the_ending(a: ScoreAnalysis, score: Score) -> None:
    """The key, metre and tempo in force at the end of the piece. A piece that
    has changed its key signature is heard in its new key from its last bars;
    one that has not keeps the key found for the whole piece."""
    top = score.parts[0]
    sig, time = score.key, tuple(score.time)
    for m in top.measures:
        if m.key is not None:
            sig = m.key
        if m.time:
            time = tuple(m.time)
    a.end_time = time
    if sig.fifths == score.key.fifths:
        a.end_key = a.key
    else:
        tail = [p.midi for part in score.parts for m in part.measures[-8:]
                for notes in m.voices.values() for n in notes if not n.grace
                for p in n.pitches]
        a.end_key = detect_key(tail, sig) if len(tail) >= 8 else sig
        if a.end_key.fifths != sig.fifths:
            a.end_key = sig             # the signature's own major or minor, never another
    visible = [t for t in score.tempos if t.visible] or list(score.tempos)
    if visible:
        last = max(visible, key=lambda t: (t.measure, t.offset))
        beats, unit = time
        per_beat = 1.5 if (unit == 8 and beats % 3 == 0 and beats > 3) else 4.0 / unit
        a.end_tempo = round(last.quarter_bpm / per_beat, 2)


#: Krumhansl-Schmuckler style weights, normalised for tonal music.
_MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def detect_key(pitches: list[int], fallback: Key) -> Key:
    """Correlate the pitch-class histogram against key profiles."""
    if len(pitches) < 8:
        return fallback
    hist = [0.0] * 12
    for p in pitches:
        hist[p % 12] += 1.0
    total = sum(hist) or 1.0
    hist = [h / total for h in hist]
    best, best_score = fallback, -1e9
    for tonic in range(12):
        for profile, mode in ((_MAJOR_PROFILE, "major"), (_MINOR_PROFILE, "minor")):
            score = sum(hist[(tonic + i) % 12] * profile[i] for i in range(12))
            if score > best_score:
                spelled = _spell_tonic(tonic, mode, fallback)
                best, best_score = Key(spelled, mode), score
    # Keep the notated key when it explains the notes nearly as well; respelling
    # a piece the user wrote in Db as C# is never an improvement.
    fb = sum(hist[(fallback.tonic_pc + i) % 12] *
             (_MINOR_PROFILE if fallback.is_minor else _MAJOR_PROFILE)[i]
             for i in range(12))
    return fallback if fb >= best_score * 0.97 else best


def _spell_tonic(pc: int, mode: str, hint: Key) -> str:
    flat_side = hint.fifths <= 0
    sharp = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    flat = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
    return (flat if flat_side else sharp)[pc % 12]


def detect_style(a: ScoreAnalysis) -> str:
    """Guess which profile the existing music is closest to.

    Used only when the score carries no exact record of its own composer (see
    ``analyse``) — a hand-written score, or one edited enough that guessing
    again is worth it. Tempo and register alone barely separate the styles
    (Mozart and Debussy sit almost on top of each other on those two axes);
    chromaticism, how many notes sound at once, and how freely the tempo
    moves are what actually tell two composers apart.
    """
    best, best_score = "classical", -1e9
    span = a.range_high - a.range_low
    for name, p in STYLES.items():
        s = 0.0
        lo, hi = p.tempo_range
        s -= abs(a.tempo - (lo + hi) / 2) / 30.0
        s -= abs(a.density - p.rhythm_density) * 4.0
        prange = p.rh_range[1] - p.lh_range[0]
        s -= abs(span - prange) / 14.0
        s -= abs(a.chromaticism - p.chromaticism) * 6.0
        expected_poly = 1.0 + (0.35 if p.doubling != "none" else 0.0) \
            + (0.5 if p.rh_style == "chordal" else 0.0)
        s -= abs(a.polyphony - expected_poly) * 2.5
        s -= abs(a.ornament_rate - p.ornament_rate) * 5.0
        if s > best_score:
            best, best_score = name, s
    return best


def summarise_harmony(score: Score, key: Key, max_bars: int = 16) -> list[str]:
    """A rough chord-per-bar reading, used to continue an existing harmony."""
    out: list[str] = []
    n_bars = min(score.measure_count, max_bars)
    for bar in range(1, n_bars + 1):
        pcs: Counter[int] = Counter()
        for part in score.parts:
            if bar - 1 >= len(part.measures):
                continue
            m = part.measures[bar - 1]
            for voice, notes in m.voices.items():
                for n in notes:
                    if n.is_rest:
                        continue
                    w = max(1, n.duration // (DIVISIONS // 4))
                    for p in n.pitches:
                        pcs[p.pc] += w
        if not pcs:
            out.append("-")
            continue
        out.append(_best_chord_name(pcs, key))
    return out


def _best_chord_name(pcs: Counter, key: Key) -> str:
    best, best_score = "?", -1e9
    for root in range(12):
        for quality in ("maj", "min", "dom7", "min7", "dim", "half_dim7", "dim7",
                        "maj7", "aug", "sus4"):
            tones = {(root + s) % 12 for _, s in CHORD_SPEC[quality]}
            hit = sum(pcs[t] for t in tones)
            miss = sum(c for pc, c in pcs.items() if pc not in tones)
            score = hit - miss * 1.4 - len(tones) * 0.5
            if score > best_score:
                best_score = score
                best = Chord(key.spell(root + 60), quality).symbol()
    return best
