"""Turn the downloaded corpus into a packed token stream for training.

Transposition augmentation happens at the token level, which is both exact and
cheap: shifting every PITCH token and the KEY token gives twelve musically
valid variants of each piece and multiplies a modest public-domain corpus into
something a 90M-parameter model can actually learn from.
"""
from __future__ import annotations

import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from motif.model.tokenizer import VOCAB, encode_score          # noqa: E402
from convert import guess_style, iter_files, load_score        # noqa: E402

MIN_TOKENS = 128          # anything shorter is an incipit, not a piece
MAX_TOKENS = 32768


def _shift_fifths(fifths: int, semitones: int) -> int:
    """Where a key signature lands after transposing by ``semitones``."""
    f = fifths + semitones * 7
    while f > 7:
        f -= 12
    while f < -7:
        f += 12
    return f


def transpose_tokens(tokens: list[str], semitones: int) -> list[str] | None:
    """Transpose a token sequence, or None if it would leave the keyboard."""
    if semitones == 0:
        return tokens
    out: list[str] = []
    for t in tokens:
        if t.startswith("PITCH_"):
            p = int(t[6:]) + semitones
            if p < 21 or p > 108:
                return None
            out.append(f"PITCH_{p}")
        elif t.startswith("KEY_"):
            head, mode = t[4:].rsplit("_", 1)
            out.append(f"KEY_{_shift_fifths(int(head), semitones)}_{mode}")
        else:
            out.append(t)
    return out


def build(raw_dir: Path, out_dir: Path, *, transpositions: int = 12,
          val_fraction: float = 0.01, limit: int | None = None,
          extra_dirs: list[Path] | None = None, seed: int = 0) -> dict:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    roots: list[tuple[Path, str]] = []
    for child in sorted(raw_dir.iterdir()) if raw_dir.exists() else []:
        if child.is_dir():
            roots.append((child, "unknown"))
    for extra in extra_dirs or []:
        roots.append((extra, "unknown"))
    if not roots:
        raise SystemExit(f"no corpus directories under {raw_dir}; run corpus.py first")

    files: list[Path] = []
    for root, _ in roots:
        files.extend(iter_files(root))
    rng.shuffle(files)
    if limit:
        files = files[:limit]
    print(f"  {len(files)} candidate files", flush=True)

    train_ids: list[np.ndarray] = []
    val_ids: list[np.ndarray] = []
    stats = Counter()
    style_counts = Counter()
    started = time.time()

    shifts = _shift_plan(transpositions)
    for i, path in enumerate(files):
        if i % 250 == 0 and i:
            done = len(train_ids)
            print(f"  {i}/{len(files)} files, {done} sequences, "
                  f"{time.time() - started:.0f}s", flush=True)
        score = load_score(path)
        if score is None:
            stats["unreadable"] += 1
            continue
        style = guess_style(path)
        try:
            base = encode_score(score, style)
        except Exception:
            stats["encode_failed"] += 1
            continue
        if not (MIN_TOKENS <= len(base) <= MAX_TOKENS):
            stats["out_of_range"] += 1
            continue
        stats["ok"] += 1
        style_counts[style] += 1

        is_val = rng.random() < val_fraction
        for shift in ([0] if is_val else shifts):
            variant = transpose_tokens(base, shift)
            if variant is None:
                continue
            arr = np.array(VOCAB.encode(variant), dtype=np.uint16)
            (val_ids if is_val else train_ids).append(arr)

    if not train_ids:
        raise SystemExit("no usable training data was produced")

    rng.shuffle(train_ids)
    train = np.concatenate(train_ids)
    val = np.concatenate(val_ids) if val_ids else train[: max(1024, len(train) // 100)]

    train.tofile(out_dir / "train.bin")
    val.tofile(out_dir / "val.bin")
    meta = {
        "vocab_size": len(VOCAB),
        "train_tokens": int(train.size),
        "val_tokens": int(val.size),
        "sequences": len(train_ids),
        "files_seen": len(files),
        "files_used": stats["ok"],
        "transpositions": len(shifts),
        "styles": dict(style_counts.most_common()),
        "rejected": dict(stats),
        "tokens": VOCAB.tokens,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_s": round(time.time() - started, 1),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"\n  train {train.size:,} tokens   val {val.size:,} tokens")
    print(f"  from {stats['ok']} scores across {len(style_counts)} styles")
    print(f"  top styles: {', '.join(f'{k}:{v}' for k, v in style_counts.most_common(8))}")
    return meta


def _shift_plan(n: int) -> list[int]:
    """Transposition amounts, nearest-to-original first."""
    if n <= 1:
        return [0]
    order = [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6]
    return order[:min(n, len(order))]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="prepare the Motif training set")
    ap.add_argument("--raw", default="training/data/raw")
    ap.add_argument("--out", default="training/data/processed")
    ap.add_argument("--transpositions", type=int, default=12)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--extra-dir", action="append", default=[])
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    build(Path(args.raw), Path(args.out), transpositions=args.transpositions,
          limit=args.limit, extra_dirs=[Path(p) for p in args.extra_dir],
          seed=args.seed)
