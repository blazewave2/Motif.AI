"""Learn Motif's melodic style model from public-domain scores.

    python training/learn_style.py <folder of MusicXML> [--out engine/motif/composer/data]

Reads every MusicXML file in the folder, takes its tune (the first part with
one staff: the voice of a song, the first violin of a quartet), finds its key,
and counts how real melodies move: which interval follows which, which scale
degree follows which (in major and in minor), how long notes are and what
follows them. The counts are smoothed into log-probabilities and written as a
small JSON file the composer loads at start-up — a few kilobytes, no
dependencies.

Only scores whose licence allows commercial use may be learned from for the
shipped model: the OpenScore Lieder and String Quartet corpora are CC0. The
script records which collections went in.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from motif.engrave.musicxml_reader import read_musicxml   # noqa: E402
from motif.score import QUARTER                            # noqa: E402

# Krumhansl–Kessler key profiles
_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

#: Note values the model distinguishes, in quarters.
DURS = [Fraction(1, 4), Fraction(1, 3), Fraction(1, 2), Fraction(2, 3), Fraction(3, 4),
        Fraction(1), Fraction(3, 2), Fraction(2), Fraction(3), Fraction(4)]
MAX_IV = 12


def _corr(a: list[float], b: list[float]) -> float:
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else 0.0


def find_key(hist: list[float], fifths: int | None) -> tuple[int, str]:
    """(tonic pitch class, mode) that best fits a pitch-class histogram,
    among the two keys of the signature when there is one."""
    cands = []
    if fifths is not None:
        major = (fifths * 7) % 12
        cands = [(major, "major"), ((major + 9) % 12, "minor")]
    else:
        cands = [(t, m) for t in range(12) for m in ("major", "minor")]
    best, best_r = cands[0], -2.0
    for tonic, mode in cands:
        prof = _MAJOR if mode == "major" else _MINOR
        rot = [prof[(pc - tonic) % 12] for pc in range(12)]
        r = _corr(hist, rot)
        if r > best_r:
            best, best_r = (tonic, mode), r
    return best


def _dur_class(d: Fraction) -> int:
    return min(range(len(DURS)), key=lambda i: abs(DURS[i] - d))


def melodies(score) -> list[list[tuple[int, Fraction, Fraction, bool]]]:
    """The tune as phrases: runs of (midi, duration, position in bar, on a
    beat), split at rests."""
    part = next((p for p in score.parts if p.staves == 1), None)
    if part is None:
        return []
    num, den = score.time
    bar = Fraction(num * 4, den)
    beat = Fraction(3, 2) if (den == 8 and num % 3 == 0) else Fraction(4, den)
    phrases, cur = [], []
    for m in part.measures:
        if m.time:
            num, den = m.time
            bar = Fraction(num * 4, den)
            beat = Fraction(3, 2) if (den == 8 and num % 3 == 0) else Fraction(4, den)
        pos = Fraction(0)
        notes = [n for n in m.voices.get(1, []) if not n.grace]
        for n in notes:
            d = Fraction(n.duration, QUARTER)
            if n.is_rest:
                if cur:
                    phrases.append(cur)
                cur = []
            elif not n.tie_stop or not cur:
                cur.append((n.pitches[-1].midi, d, pos, pos % beat == 0))
            else:
                midi, dd, p0, s0 = cur[-1]
                cur[-1] = (midi, dd + d, p0, s0)
            pos += d
            if pos > bar:
                break
    if cur:
        phrases.append(cur)
    return [p for p in phrases if len(p) >= 3]


def learn(files: list[Path]) -> dict:
    iv = defaultdict(Counter)            # previous interval -> interval
    deg = {"major": defaultdict(Counter), "minor": defaultdict(Counter)}
    deg_strong = {"major": Counter(), "minor": Counter()}
    dur = defaultdict(Counter)
    start_iv = Counter()
    songs = notes = 0
    collections = Counter()
    for f in files:
        try:
            score = read_musicxml(f.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        phrases = melodies(score)
        if not phrases:
            continue
        hist = [0.0] * 12
        for ph in phrases:
            for midi, d, _, _ in ph:
                hist[midi % 12] += float(d)
        tonic, mode = find_key(hist, score.key.fifths if score.key else None)
        songs += 1
        collection = f.name.split("__")[0]
        collections[collection] += 1
        if collection == "lieder":
            # a singer repeats a note for each syllable of the words; an
            # instrument sustains it, so the tune is learned without them
            phrases = [_merge_repeats(ph) for ph in phrases]
        for ph in phrases:
            prev_iv = None
            prev_deg = None
            prev_dur = None
            for k, (midi, d, pos, strong) in enumerate(ph):
                dg = (midi - tonic) % 12
                if k:
                    step = max(-MAX_IV, min(MAX_IV, midi - ph[k - 1][0]))
                    if prev_iv is None:
                        start_iv[step] += 1
                    else:
                        iv[prev_iv][step] += 1
                    prev_iv = step
                    deg[mode][prev_deg][dg] += 1
                if strong:
                    deg_strong[mode][dg] += 1
                dc = _dur_class(d)
                if prev_dur is not None:
                    dur[prev_dur][dc] += 1
                prev_deg, prev_dur = dg, dc
                notes += 1
    return _pack(iv, start_iv, deg, deg_strong, dur, songs, notes, collections)


def _merge_repeats(ph):
    out = []
    for note in ph:
        if out and out[-1][0] == note[0]:
            midi, d, pos, strong = out[-1]
            out[-1] = (midi, d + note[1], pos, strong)
        else:
            out.append(note)
    return out


def _logp(counter: Counter, keys, alpha: float = 0.5) -> list[float]:
    total = sum(counter.values()) + alpha * len(keys)
    return [round(math.log((counter.get(k, 0) + alpha) / total), 3) for k in keys]


def _pack(iv, start_iv, deg, deg_strong, dur, songs, notes, collections) -> dict:
    ivs = list(range(-MAX_IV, MAX_IV + 1))
    return {
        "about": "Melodic statistics learned by training/learn_style.py.",
        "sources": dict(collections),
        "licence": "Learned from CC0 scores (OpenScore Lieder, OpenScore String Quartets).",
        "songs": songs, "notes": notes,
        "intervals": ivs,
        "interval_start": _logp(start_iv, ivs),
        "interval_after": {str(p): _logp(iv[p], ivs) for p in ivs},
        "degree_after": {mode: {str(p): _logp(deg[mode][p], range(12)) for p in range(12)}
                         for mode in ("major", "minor")},
        "degree_strong": {mode: _logp(deg_strong[mode], range(12)) for mode in ("major", "minor")},
        "durations": [str(d) for d in DURS],
        "duration_after": {str(p): _logp(dur[p], range(len(DURS))) for p in range(len(DURS))},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("folder", type=Path)
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parents[1] / "engine/motif/composer/data")
    ap.add_argument("--only", default="lieder,quartets",
                    help="collections (file-name prefixes) to learn from")
    args = ap.parse_args(argv)
    allowed = tuple(p.strip() + "__" for p in args.only.split(",") if p.strip())
    files = sorted(f for f in args.folder.glob("*.musicxml") if f.name.startswith(allowed))
    model = learn(files)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "melody.json"
    path.write_text(json.dumps(model, separators=(",", ":")))
    print(f"learned from {model['songs']} scores, {model['notes']} notes -> {path} "
          f"({path.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
