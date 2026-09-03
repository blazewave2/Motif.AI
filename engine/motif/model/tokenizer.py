"""Symbolic-music tokenizer shared by training and inference.

A bar-relative (REMI-style) event vocabulary with explicit conditioning tokens
for style, key, metre and tempo, so the trained model can be steered by the
same plan the symbolic engine follows.  Pure stdlib: the engine imports this
without needing torch.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..score import DIVISIONS, Note, Part, Score, bar_duration
from ..theory.pitch import Key, Pitch

#: Positions are quantised to a twelfth of a quarter note, which represents
#: both duple subdivisions and triplets exactly.
GRID = DIVISIONS // 12          # 40 ticks
MAX_POS = 96                    # up to an 8-quarter bar
MAX_DUR = 96                    # up to 8 quarter notes; longer values are tied

STYLE_TAGS = [
    "bach", "handel", "scarlatti", "vivaldi", "mozart", "haydn", "clementi",
    "beethoven", "schubert", "chopin", "liszt", "brahms", "tchaikovsky",
    "mendelssohn", "grieg", "rachmaninoff", "scriabin", "debussy", "ravel",
    "satie", "einaudi", "film", "classical", "unknown",
]
TEMPO_BINS = [40, 52, 60, 69, 76, 84, 92, 100, 112, 126, 138, 152, 168, 184, 200]
VELOCITY_BINS = [24, 40, 52, 64, 76, 88, 104, 120]

SPECIAL = ["<pad>", "<bos>", "<eos>", "<unk>", "<sep>"]


def _dur_bin(ticks: int) -> int:
    """Snap a duration onto the twelfth-of-a-quarter grid."""
    return max(1, min(MAX_DUR, int(round(ticks / GRID))))


def _tempo_bin(bpm: float) -> int:
    for i, edge in enumerate(TEMPO_BINS):
        if bpm <= edge:
            return i
    return len(TEMPO_BINS)


def _velocity_bin(v: int) -> int:
    for i, edge in enumerate(VELOCITY_BINS):
        if v <= edge:
            return i
    return len(VELOCITY_BINS) - 1


class Vocabulary:
    def __init__(self) -> None:
        toks: list[str] = list(SPECIAL)
        toks += [f"STYLE_{s}" for s in STYLE_TAGS]
        toks += [f"KEY_{f}_{m}" for f in range(-7, 8) for m in ("maj", "min")]
        toks += [f"TS_{n}_{d}" for n, d in
                 [(2, 2), (2, 4), (3, 4), (4, 4), (5, 4), (6, 4), (3, 8), (6, 8),
                  (9, 8), (12, 8), (5, 8), (7, 8), (3, 2), (4, 2)]]
        toks += [f"TEMPO_{i}" for i in range(len(TEMPO_BINS) + 1)]
        toks += ["BAR"]
        toks += [f"POS_{i}" for i in range(MAX_POS + 1)]
        toks += [f"TRACK_{i}" for i in range(4)]
        toks += [f"PITCH_{i}" for i in range(128)]
        toks += [f"DUR_{i}" for i in range(1, MAX_DUR + 1)]
        toks += [f"VEL_{i}" for i in range(len(VELOCITY_BINS))]
        toks += ["CHORD"]
        self.tokens = toks
        self.stoi = {t: i for i, t in enumerate(toks)}
        self.itos = {i: t for i, t in enumerate(toks)}

    def __len__(self) -> int:
        return len(self.tokens)

    def encode(self, tokens: list[str]) -> list[int]:
        unk = self.stoi["<unk>"]
        return [self.stoi.get(t, unk) for t in tokens]

    def decode(self, ids: list[int]) -> list[str]:
        return [self.itos.get(i, "<unk>") for i in ids]

    @property
    def pad_id(self) -> int:
        return self.stoi["<pad>"]

    @property
    def bos_id(self) -> int:
        return self.stoi["<bos>"]

    @property
    def eos_id(self) -> int:
        return self.stoi["<eos>"]


VOCAB = Vocabulary()


@dataclass
class Conditioning:
    style: str = "unknown"
    key: Key = None
    time: tuple[int, int] = (4, 4)
    tempo: float = 100.0

    def tokens(self) -> list[str]:
        key = self.key or Key()
        style = self.style if self.style in STYLE_TAGS else "unknown"
        ts = f"TS_{self.time[0]}_{self.time[1]}"
        if ts not in VOCAB.stoi:
            ts = "TS_4_4"
        return ["<bos>",
                f"STYLE_{style}",
                f"KEY_{max(-7, min(7, key.fifths))}_{'min' if key.is_minor else 'maj'}",
                ts,
                f"TEMPO_{_tempo_bin(self.tempo)}"]


def encode_score(score: Score, style: str = "unknown",
                 max_bars: int | None = None) -> list[str]:
    """Flatten a score into the event vocabulary."""
    cond = Conditioning(style=style, key=score.key, time=tuple(score.time),
                        tempo=score.tempo)
    out = cond.tokens()
    bar_ticks = bar_duration(tuple(score.time))
    n_bars = score.measure_count if max_bars is None else min(score.measure_count, max_bars)

    for bar in range(1, n_bars + 1):
        out.append("BAR")
        events: list[tuple[int, int, int, int, int]] = []   # pos, track, pitch, dur, vel
        for pi, part in enumerate(score.parts):
            if bar - 1 >= len(part.measures):
                continue
            m = part.measures[bar - 1]
            for voice in sorted(m.voices):
                t = 0
                for n in m.voices[voice]:
                    if n.grace:
                        continue
                    if not n.is_rest and not n.tie_stop:
                        pos = max(0, min(MAX_POS, int(round(t / GRID))))
                        track = min(3, (n.staff - 1) + (pi * 2 if len(score.parts) > 1 else 0))
                        dur = _dur_bin(n.duration)
                        vel = _velocity_bin(n.velocity)
                        for p in n.pitches:
                            events.append((pos, track, p.midi, dur, vel))
                    t += n.duration
        events.sort(key=lambda e: (e[0], e[1], e[2]))
        last_pos, last_track = -1, -1
        for pos, track, pitch, dur, vel in events:
            if pos != last_pos:
                out.append(f"POS_{pos}")
                last_pos, last_track = pos, -1
            if track != last_track:
                out.append(f"TRACK_{track}")
                last_track = track
            out.append(f"PITCH_{pitch}")
            out.append(f"DUR_{dur}")
            out.append(f"VEL_{vel}")
    out.append("<eos>")
    return out


def decode_tokens(tokens: list[str], key: Key | None = None,
                  time: tuple[int, int] | None = None) -> Score:
    """Rebuild a Score from generated tokens.

    Anything malformed is skipped rather than raising: a sampled sequence is
    not guaranteed to be well-formed, and a partial bar is still music.
    """
    from ..score import Measure

    score = Score()
    style = "unknown"
    fifths, mode = 0, "maj"
    ts = time or (4, 4)
    tempo = 100.0

    i = 0
    while i < len(tokens) and tokens[i] != "BAR":
        t = tokens[i]
        if t.startswith("STYLE_"):
            style = t[6:]
        elif t.startswith("KEY_"):
            try:
                parts = t[4:].rsplit("_", 1)
                fifths, mode = int(parts[0]), parts[1]
            except (ValueError, IndexError):
                pass
        elif t.startswith("TS_"):
            try:
                n, d = t[3:].split("_")
                ts = (int(n), int(d))
            except ValueError:
                pass
        elif t.startswith("TEMPO_"):
            try:
                idx = int(t[6:])
                tempo = float(TEMPO_BINS[min(idx, len(TEMPO_BINS) - 1)])
            except ValueError:
                pass
        i += 1

    from ..engrave.musicxml_reader import _key_from_fifths
    score.key = key or _key_from_fifths(fifths, "minor" if mode == "min" else "major")
    score.time = ts
    score.tempo = tempo
    score.metadata["style"] = style

    part = Part(id="P1", name="Piano", abbreviation="Pno.", staves=2,
                clefs={1: "G", 2: "F"})
    score.add_part(part)

    bar_ticks = bar_duration(ts)
    bars: list[list[tuple[int, int, int, int, int]]] = []
    cur: list[tuple[int, int, int, int, int]] = []
    pos, track = 0, 0
    pending_pitch: int | None = None
    pending_dur: int | None = None

    for t in tokens[i:]:
        if t == "BAR":
            if cur or bars:
                bars.append(cur)
            cur = []
            pos, track, pending_pitch, pending_dur = 0, 0, None, None
        elif t.startswith("POS_"):
            try:
                pos = max(0, min(MAX_POS, int(t[4:])))
            except ValueError:
                pass
            pending_pitch = pending_dur = None
        elif t.startswith("TRACK_"):
            try:
                track = max(0, min(3, int(t[6:])))
            except ValueError:
                pass
        elif t.startswith("PITCH_"):
            try:
                pending_pitch = max(0, min(127, int(t[6:])))
            except ValueError:
                pending_pitch = None
            pending_dur = None
        elif t.startswith("DUR_"):
            try:
                pending_dur = max(1, min(MAX_DUR, int(t[4:])))
            except ValueError:
                pending_dur = None
        elif t.startswith("VEL_"):
            if pending_pitch is not None and pending_dur is not None:
                try:
                    vel = VELOCITY_BINS[max(0, min(len(VELOCITY_BINS) - 1, int(t[4:])))]
                except ValueError:
                    vel = 80
                cur.append((pos, track, pending_pitch, pending_dur, vel))
            pending_pitch = pending_dur = None
        elif t == "<eos>":
            break
    if cur:
        bars.append(cur)

    for bi, events in enumerate(bars):
        m = part.measure(bi + 1)
        if bi == 0:
            m.key, m.time = score.key, ts
        for staff, voice in ((1, 1), (2, 5)):
            staff_events = [e for e in events if (e[1] % 2) + 1 == staff]
            _fill_voice(m, staff_events, staff, voice, bar_ticks, score.key)
    return score


def _fill_voice(measure, events, staff: int, voice: int, bar_ticks: int, key: Key) -> None:
    """Turn (pos, track, pitch, dur, vel) tuples into a gap-free voice."""
    from ..score import Note

    by_pos: dict[int, list[tuple[int, int, int]]] = {}
    for pos, _track, pitch, dur, vel in events:
        by_pos.setdefault(pos, []).append((pitch, dur, vel))

    t = 0
    for pos in sorted(by_pos):
        start = min(bar_ticks, pos * GRID)
        if start > t:
            measure.add(Note([], start - t, voice=voice, staff=staff))
            t = start
        elif start < t:
            continue                       # overlapping event: keep the earlier one
        group = by_pos[pos]
        dur = min(max(d for _p, d, _v in group) * GRID, bar_ticks - t)
        if dur <= 0:
            continue
        pitches = sorted({p for p, _d, _v in group})
        vel = max(v for _p, _d, v in group)
        measure.add(Note([key.spell(p) for p in pitches], dur, voice=voice,
                         staff=staff, velocity=vel))
        t += dur
    if t < bar_ticks:
        measure.add(Note([], bar_ticks - t, voice=voice, staff=staff))
