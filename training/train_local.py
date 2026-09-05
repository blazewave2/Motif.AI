"""Train a checkpoint on this machine.

Modal is where the real run happens — a useful model needs a GPU and hours of
it. This exists so the whole chain (corpus → tokens → training → checkpoint →
generation) can be exercised end to end on a laptop in a few minutes with a
deliberately tiny model, before any money is spent on the real one. The
checkpoint it writes has exactly the same shape as Modal's, so everything
downstream is genuinely tested rather than assumed.

    python training/train_local.py --data training/data/processed \\
        --out training/data/checkpoints/local.pt --preset tiny --steps 300
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from model import MotifConfig, MotifModel     # noqa: E402

#: Deliberately small shapes for a laptop; the real sizes live in modal_app.
PRESETS = {
    "tiny":  dict(n_layer=4,  n_head=4,  n_embd=128, block_size=256),
    "small": dict(n_layer=8,  n_head=8,  n_embd=512, block_size=512),
    "base":  dict(n_layer=12, n_head=12, n_embd=768, block_size=1024),
}


def load_split(data_dir: Path, name: str) -> np.ndarray:
    return np.fromfile(data_dir / f"{name}.bin", dtype=np.uint16)


def get_batch(data: np.ndarray, block: int, batch: int, device: str):
    if len(data) <= block + 1:
        raise SystemExit(
            f"only {len(data)} tokens available but the block size is {block}; "
            "prepare more data or use a smaller preset")
    ix = torch.randint(len(data) - block - 1, (batch,))
    x = torch.stack([torch.from_numpy(data[i:i + block].astype(np.int64)) for i in ix])
    y = torch.stack([torch.from_numpy(data[i + 1:i + 1 + block].astype(np.int64))
                     for i in ix])
    return x.to(device), y.to(device)


@torch.no_grad()
def estimate_loss(model, data: np.ndarray, block: int, batch: int,
                  device: str, iters: int = 20) -> float:
    model.eval()
    losses = []
    for _ in range(iters):
        try:
            x, y = get_batch(data, block, batch, device)
        except SystemExit:
            break
        _, loss = model(x, y)
        losses.append(loss.item())
    model.train()
    return sum(losses) / max(1, len(losses)) if losses else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser(description="train a Motif checkpoint locally")
    ap.add_argument("--data", default="training/data/processed")
    ap.add_argument("--out", default="training/data/checkpoints/local.pt")
    ap.add_argument("--preset", default="tiny", choices=sorted(PRESETS))
    ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--eval-every", type=int, default=50)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()

    data_dir = Path(args.data)
    meta = json.loads((data_dir / "meta.json").read_text())
    train_data = load_split(data_dir, "train")
    val_data = load_split(data_dir, "val")

    shape = dict(PRESETS[args.preset])
    cfg = MotifConfig(vocab_size=meta["vocab_size"], dropout=0.1, **shape)
    model = MotifModel(cfg).to(args.device)
    params = model.num_parameters() / 1e6
    print(f"  {args.preset}: {params:.1f}M parameters, block {cfg.block_size}, "
          f"{len(train_data):,} training tokens, device {args.device}")

    opt = model.configure_optimizers(0.1, args.lr, (0.9, 0.95), args.device)
    best = float("inf")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()

    for step in range(1, args.steps + 1):
        # Cosine decay with a short warmup, same shape as the Modal run.
        warmup = max(1, args.steps // 20)
        if step < warmup:
            lr = args.lr * step / warmup
        else:
            p = (step - warmup) / max(1, args.steps - warmup)
            lr = args.lr * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * p)))
        for g in opt.param_groups:
            g["lr"] = lr

        x, y = get_batch(train_data, cfg.block_size, args.batch, args.device)
        _, loss = model(x, y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

        if step % args.eval_every == 0 or step == args.steps:
            val = estimate_loss(model, val_data, cfg.block_size, args.batch, args.device)
            mins = (time.time() - started) / 60
            print(f"  step {step:5d}  train {loss.item():.3f}  val {val:.3f}  "
                  f"({mins:.1f} min)", flush=True)
            if val < best:
                best = val
                torch.save({"model": model.state_dict(),
                            "config": cfg.__dict__,
                            "step": step,
                            "val_loss": val,
                            "vocab": meta["tokens"]}, out)

    print(f"\n  saved {out}  (best val {best:.3f})")


if __name__ == "__main__":
    main()
