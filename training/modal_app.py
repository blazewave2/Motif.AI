"""Train Motif's neural composer on Modal, inside a fixed dollar budget.

Run it with:

    modal run training/modal_app.py --step all --budget 26      # the whole thing
    modal run training/modal_app.py --step download            # fetch the result

or one stage at a time:

    modal run training/modal_app.py --step corpus     # download the scores  (CPU)
    modal run training/modal_app.py --step prepare    # tokenize + augment   (CPU)
    modal run training/modal_app.py --step train --budget 26
    modal run training/modal_app.py --step sample

The budget is enforced in the training loop itself, not just documented: the
run checkpoints and stops before the estimated spend crosses the cap, so an
overnight job cannot quietly run past it.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import modal

APP_NAME = "motif-ai"
VOLUME_NAME = "motif-data"
DATA = Path("/data")

# Approximate on-demand US rates in USD per GPU-hour. These are used only to
# enforce the budget, and Modal's published pricing is authoritative — check
# https://modal.com/pricing and override with --gpu-hourly if it has moved.
GPU_HOURLY = {
    "T4": 0.59, "L4": 0.80, "A10G": 1.10, "L40S": 1.95,
    "A100-40GB": 2.10, "A100-80GB": 2.50, "H100": 3.95,
}
DEFAULT_GPU = "A10G"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install(
        "torch==2.4.1",
        "numpy>=1.26,<2.2",
        "music21==9.1.0",
        "tqdm>=4.66",
    )
    .add_local_dir(
        Path(__file__).resolve().parents[1] / "engine",
        remote_path="/root/engine",
    )
    .add_local_dir(
        Path(__file__).resolve().parent,
        remote_path="/root/training",
    )
)

app = modal.App(APP_NAME, image=image)
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _sys_path() -> None:
    import sys
    for p in ("/root/engine", "/root/training"):
        if p not in sys.path:
            sys.path.insert(0, p)


# ---------------------------------------------------------------------------
# 1. corpus
# ---------------------------------------------------------------------------
@app.function(volumes={str(DATA): volume}, timeout=60 * 60, cpu=4.0)
def fetch_corpus(include_extended: bool = True, include_nc: bool = False) -> dict:
    _sys_path()
    from corpus import fetch_all, NOTES_ON_LARGER_SETS
    print("Downloading public-domain scores…", flush=True)
    report = fetch_all(DATA / "raw", include_extended=include_extended,
                       include_nc=include_nc)
    volume.commit()
    print(NOTES_ON_LARGER_SETS)
    return {"ok": report["ok"], "failed": report["failed"]}


# ---------------------------------------------------------------------------
# 2. prepare
# ---------------------------------------------------------------------------
@app.function(volumes={str(DATA): volume}, timeout=6 * 60 * 60, cpu=8.0,
              memory=16384)
def prepare_data(transpositions: int = 12, limit: int | None = None) -> dict:
    _sys_path()
    from prepare import build
    meta = build(DATA / "raw", DATA / "processed",
                 transpositions=transpositions, limit=limit)
    volume.commit()
    return meta


# ---------------------------------------------------------------------------
# 3. train
# ---------------------------------------------------------------------------
PRESETS = {
    # Sized to the data actually available. The public-domain Humdrum corpus
    # yields roughly 150M augmented tokens, which suits ~25M parameters; step
    # up to "base" only once you have folded in a larger set such as PDMX.
    "small": dict(n_layer=8, n_head=8, n_embd=512, block_size=1024),
    "base": dict(n_layer=12, n_head=12, n_embd=768, block_size=1024),
    "large": dict(n_layer=16, n_head=16, n_embd=1024, block_size=1024),
}


@app.function(volumes={str(DATA): volume}, gpu=DEFAULT_GPU,
              timeout=24 * 60 * 60, memory=32768)
def train(budget_usd: float = 26.0, preset: str = "small", gpu: str = DEFAULT_GPU,
          gpu_hourly: float | None = None, max_steps: int = 60000,
          batch_size: int = 16, grad_accum: int = 4, lr: float = 6e-4,
          warmup: int = 400, eval_every: int = 500, resume: bool = True,
          dropout: float = 0.1) -> dict:
    _sys_path()
    import numpy as np
    import torch
    from model import MotifConfig, MotifModel

    rate = gpu_hourly if gpu_hourly else GPU_HOURLY.get(gpu, GPU_HOURLY[DEFAULT_GPU])
    per_second = rate / 3600.0
    started = time.time()

    proc = DATA / "processed"
    meta = json.loads((proc / "meta.json").read_text())
    train_ids = np.memmap(proc / "train.bin", dtype=np.uint16, mode="r")
    val_ids = np.memmap(proc / "val.bin", dtype=np.uint16, mode="r")
    print(f"data: {len(train_ids):,} train / {len(val_ids):,} val tokens", flush=True)

    cfg_kwargs = dict(PRESETS.get(preset, PRESETS["small"]))
    cfg = MotifConfig(vocab_size=meta["vocab_size"], dropout=dropout, **cfg_kwargs)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(1337)
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    model = MotifModel(cfg).to(device)
    print(f"model: {model.num_parameters()/1e6:.1f}M parameters, preset={preset}",
          flush=True)

    ckpt_dir = DATA / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = ckpt_dir / f"motif-{preset}.pt"

    optimizer = model.configure_optimizers(0.1, lr, (0.9, 0.95), device)
    scaler = torch.amp.GradScaler(enabled=(device == "cuda"))
    step0, best_val = 0, float("inf")
    spent_before = 0.0

    if resume and ckpt_path.exists():
        state = torch.load(ckpt_path, map_location=device, weights_only=False)
        if state.get("config", {}).get("n_embd") == cfg.n_embd:
            model.load_state_dict(state["model"])
            optimizer.load_state_dict(state["optimizer"])
            step0 = state.get("step", 0)
            best_val = state.get("best_val", float("inf"))
            spent_before = state.get("spent_usd", 0.0)
            print(f"resumed at step {step0}, ${spent_before:.2f} already spent",
                  flush=True)

    budget_left = max(0.0, budget_usd - spent_before)
    if budget_left <= 0.05:
        return {"status": "budget_exhausted", "spent_usd": spent_before, "step": step0}
    seconds_allowed = budget_left / per_second
    print(f"budget: ${budget_usd:.2f} total, ${budget_left:.2f} left "
          f"= {seconds_allowed/3600:.2f} h on {gpu} at ${rate:.2f}/h", flush=True)

    block = cfg.block_size

    def get_batch(split: str):
        source = train_ids if split == "train" else val_ids
        hi = len(source) - block - 1
        if hi <= 0:
            raise SystemExit("dataset is shorter than one context window")
        ix = torch.randint(hi, (batch_size,))
        x = torch.stack([torch.from_numpy(source[i:i + block].astype(np.int64))
                         for i in ix])
        y = torch.stack([torch.from_numpy(source[i + 1:i + 1 + block].astype(np.int64))
                         for i in ix])
        if device == "cuda":
            return x.pin_memory().to(device, non_blocking=True), \
                   y.pin_memory().to(device, non_blocking=True)
        return x.to(device), y.to(device)

    @torch.no_grad()
    def estimate_loss(iters: int = 40) -> dict:
        model.eval()
        out = {}
        for split in ("train", "val"):
            losses = torch.zeros(iters)
            for k in range(iters):
                X, Y = get_batch(split)
                with torch.autocast(device_type=device, dtype=torch.bfloat16,
                                    enabled=(device == "cuda")):
                    _, loss = model(X, Y)
                losses[k] = loss.item()
            out[split] = losses.mean().item()
        model.train()
        return out

    def lr_at(step: int) -> float:
        if step < warmup:
            return lr * (step + 1) / warmup
        progress = (step - warmup) / max(1, max_steps - warmup)
        return lr * 0.1 + 0.5 * (lr - lr * 0.1) * (1 + math.cos(math.pi * min(1.0, progress)))

    print("training…", flush=True)
    model.train()
    step = step0
    stop_reason = "max_steps"
    tokens_seen = 0

    while step < max_steps:
        elapsed = time.time() - started
        spent = spent_before + elapsed * per_second
        # Stop with enough margin to write the checkpoint and shut down cleanly.
        if spent >= budget_usd - 0.10:
            stop_reason = "budget"
            break

        for group in optimizer.param_groups:
            group["lr"] = lr_at(step)

        optimizer.zero_grad(set_to_none=True)
        for micro in range(grad_accum):
            X, Y = get_batch("train")
            with torch.autocast(device_type=device, dtype=torch.bfloat16,
                                enabled=(device == "cuda")):
                _, loss = model(X, Y)
                loss = loss / grad_accum
            scaler.scale(loss).backward()
            tokens_seen += X.numel()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(optimizer)
        scaler.update()
        step += 1

        if step % 50 == 0:
            print(f"  step {step:6d}  loss {loss.item()*grad_accum:.4f}  "
                  f"lr {lr_at(step):.2e}  ${spent:.2f}  "
                  f"{tokens_seen/1e6:.1f}M tok", flush=True)

        if step % eval_every == 0 or step == max_steps:
            metrics = estimate_loss()
            print(f"  eval  step {step}: train {metrics['train']:.4f}  "
                  f"val {metrics['val']:.4f}", flush=True)
            if metrics["val"] < best_val:
                best_val = metrics["val"]
                _save(ckpt_path, model, optimizer, cfg, step, best_val, spent, meta)
                volume.commit()
                print(f"  checkpoint saved (val {best_val:.4f})", flush=True)

    spent = spent_before + (time.time() - started) * per_second
    _save(ckpt_path, model, optimizer, cfg, step, best_val, spent, meta)
    volume.commit()
    result = {"status": "stopped", "reason": stop_reason, "step": step,
              "best_val": best_val, "spent_usd": round(spent, 2),
              "params_m": round(model.num_parameters() / 1e6, 1),
              "tokens_seen_m": round(tokens_seen / 1e6, 1),
              "checkpoint": str(ckpt_path)}
    print(json.dumps(result, indent=2), flush=True)
    return result


def _save(path, model, optimizer, cfg, step, best_val, spent, meta) -> None:
    import torch
    from dataclasses import asdict
    torch.save({
        "model": model.state_dict(),
        "optimizer": optimizer.state_dict(),
        "config": asdict(cfg),
        "step": step,
        "best_val": best_val,
        "spent_usd": spent,
        "vocab_size": cfg.vocab_size,
        "tokens": meta.get("tokens"),
        "data_meta": {k: meta.get(k) for k in
                      ("train_tokens", "styles", "transpositions", "files_used")},
    }, path)


# ---------------------------------------------------------------------------
# 4. sample
# ---------------------------------------------------------------------------
@app.function(volumes={str(DATA): volume}, gpu="T4", timeout=20 * 60)
def sample(preset: str = "small", style: str = "chopin", key: str = "Eb minor",
           bars: int = 16, temperature: float = 0.95, top_k: int = 40) -> str:
    _sys_path()
    from motif.model.runtime import NeuralComposer
    from motif.engrave.musicxml import to_musicxml
    from motif.theory.pitch import Key

    ckpt = DATA / "checkpoints" / f"motif-{preset}.pt"
    if not ckpt.exists():
        return f"no checkpoint at {ckpt}"
    composer = NeuralComposer(str(ckpt))
    score = composer.generate(style=style, key=Key.parse(key), bars=bars,
                              temperature=temperature, top_k=top_k)
    xml = to_musicxml(score)
    out = DATA / "samples"
    out.mkdir(exist_ok=True)
    name = out / f"sample-{style}-{int(time.time())}.musicxml"
    name.write_text(xml)
    volume.commit()
    return f"wrote {name} ({score.measure_count} bars, {len(xml)} chars)"


@app.function(volumes={str(DATA): volume}, timeout=30 * 60)
def read_checkpoint(preset: str = "small") -> bytes:
    ckpt = DATA / "checkpoints" / f"motif-{preset}.pt"
    if not ckpt.exists():
        raise FileNotFoundError(str(ckpt))
    return ckpt.read_bytes()


@app.function(volumes={str(DATA): volume})
def status() -> dict:
    out: dict = {"raw": [], "processed": None, "checkpoints": []}
    raw = DATA / "raw"
    if raw.exists():
        out["raw"] = sorted(p.name for p in raw.iterdir() if p.is_dir())
    meta = DATA / "processed" / "meta.json"
    if meta.exists():
        m = json.loads(meta.read_text())
        out["processed"] = {k: m.get(k) for k in
                            ("train_tokens", "val_tokens", "files_used", "styles")}
    ck = DATA / "checkpoints"
    if ck.exists():
        for p in sorted(ck.glob("*.pt")):
            out["checkpoints"].append({"name": p.name,
                                       "mb": round(p.stat().st_size / 1e6, 1)})
    return out


# ---------------------------------------------------------------------------
@app.local_entrypoint()
def main(step: str = "status", budget: float = 26.0, preset: str = "small",
         gpu: str = DEFAULT_GPU, gpu_hourly: float = 0.0, max_steps: int = 60000,
         transpositions: int = 12, limit: int = 0, style: str = "chopin",
         key: str = "Eb minor", bars: int = 16, out: str = "checkpoints",
         include_nc: bool = False, core_only: bool = False):
    if step == "all":
        # The whole pipeline in order, which is what a first run wants.
        # Each stage is idempotent, so re-running after an interruption
        # resumes rather than starting again.
        print("1/4  downloading public-domain scores…", flush=True)
        print(fetch_corpus.remote(include_extended=not core_only,
                                  include_nc=include_nc))
        print("\n2/4  tokenising and augmenting…", flush=True)
        meta = prepare_data.remote(transpositions=transpositions,
                                   limit=limit or None)
        print(json.dumps({k: v for k, v in meta.items() if k != "tokens"}, indent=2))
        print(f"\n3/4  training on {gpu} within ${budget:.2f}…", flush=True)
        print(train.remote(budget_usd=budget, preset=preset, gpu=gpu,
                           gpu_hourly=gpu_hourly or None, max_steps=max_steps))
        print("\n4/4  sampling from the trained model…", flush=True)
        print(sample.remote(preset=preset, style=style, key=key, bars=bars))
        print("\nNow bring the checkpoint down:")
        print(f"  modal run training/modal_app.py --step download --preset {preset}")
    elif step == "corpus":
        print(fetch_corpus.remote(include_extended=not core_only,
                                  include_nc=include_nc))
    elif step == "prepare":
        meta = prepare_data.remote(transpositions=transpositions,
                                   limit=limit or None)
        print(json.dumps({k: v for k, v in meta.items() if k != "tokens"}, indent=2))
    elif step == "train":
        print(train.remote(budget_usd=budget, preset=preset, gpu=gpu,
                           gpu_hourly=gpu_hourly or None, max_steps=max_steps))
    elif step == "sample":
        print(sample.remote(preset=preset, style=style, key=key, bars=bars))
    elif step == "download":
        data = read_checkpoint.remote(preset=preset)
        dest = Path(out)
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"motif-{preset}.pt"
        path.write_bytes(data)
        print(f"wrote {path} ({len(data)/1e6:.1f} MB)")
        print("point the engine at it:  MOTIF_MODEL=%s python -m motif serve" % path)
    else:
        print(json.dumps(status.remote(), indent=2))
