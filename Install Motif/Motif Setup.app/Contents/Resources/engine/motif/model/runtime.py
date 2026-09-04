"""Inference for the trained Motif model.

The neural model does not replace the symbolic engine — it supplies melodic
material with a learned voice, which the theory engine then harmonises,
voices and engraves.  That split is what lets a small model trained on a
modest public-domain corpus still produce coherent long-form music.

torch is imported lazily so the engine runs with no ML dependencies at all.
"""
from __future__ import annotations

import sys
from pathlib import Path

from ..score import Note, Score
from ..theory.pitch import Key
from .tokenizer import MAX_DUR, MAX_POS, VOCAB, Conditioning, decode_tokens


class ModelUnavailable(RuntimeError):
    pass


class NeuralComposer:
    """Loads a checkpoint and samples grammar-constrained token sequences."""

    def __init__(self, checkpoint: str, device: str | None = None):
        try:
            import torch
        except ImportError as exc:
            raise ModelUnavailable(
                "PyTorch is not installed; Motif will use the symbolic engine"
            ) from exc
        self.torch = torch
        path = Path(checkpoint)
        if not path.exists():
            raise ModelUnavailable(f"checkpoint not found: {checkpoint}")

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        state = torch.load(str(path), map_location=self.device, weights_only=False)

        model_cls, config_cls = _import_model()
        cfg = config_cls(**{k: v for k, v in state["config"].items()
                            if k in config_cls.__dataclass_fields__})
        model = model_cls(cfg)
        model.load_state_dict(state["model"])
        model.eval().to(self.device)

        self.model = model
        self.config = cfg
        self.meta = state.get("data_meta", {})
        self.step = state.get("step", 0)
        self.val_loss = state.get("best_val")
        # A checkpoint trained against a different vocabulary cannot be decoded.
        if state.get("vocab_size") not in (None, len(VOCAB)):
            raise ModelUnavailable(
                f"checkpoint vocabulary ({state['vocab_size']}) does not match "
                f"this build ({len(VOCAB)}); retrain or update Motif")

    @property
    def available(self) -> bool:
        return True

    def describe(self) -> str:
        params = self.model.num_parameters() / 1e6
        loss = f"{self.val_loss:.3f}" if self.val_loss else "?"
        return (f"Motif neural model — {params:.1f}M params, step {self.step}, "
                f"val loss {loss}, device {self.device}")

    # ------------------------------------------------------------------
    def generate(self, *, style: str = "chopin", key: Key | None = None,
                 time: tuple[int, int] = (4, 4), tempo: float = 96.0,
                 bars: int = 16, temperature: float = 0.95,
                 top_k: int = 40, top_p: float | None = 0.95,
                 max_tokens: int | None = None, seed: int | None = None) -> Score:
        """Sample a complete passage and decode it into a Score."""
        torch = self.torch
        if seed is not None:
            torch.manual_seed(seed)
        key = key or Key("C", "major")
        cond = Conditioning(style=style, key=key, time=time, tempo=tempo)
        prompt = VOCAB.encode(cond.tokens())
        idx = torch.tensor([prompt], dtype=torch.long, device=self.device)

        budget = max_tokens or min(self.config.block_size - len(prompt) - 1,
                                   bars * 220)
        grammar = _Grammar(target_bars=bars)
        out = self.model.generate(
            idx, max_new_tokens=budget, temperature=temperature,
            top_k=top_k, top_p=top_p,
            allowed_fn=lambda ids: grammar.mask(ids, torch),
            eos_id=VOCAB.eos_id)
        tokens = VOCAB.decode(out[0].tolist())
        score = decode_tokens(tokens, key=key, time=time)
        score.tempo = tempo
        score.metadata["generator"] = "neural"
        return score

    def melody(self, *, style: str, key: Key, time: tuple[int, int], bars: int,
               tempo: float = 96.0, temperature: float = 0.9,
               top_k: int = 32, seed: int | None = None) -> list[Note]:
        """Sample material and return just the upper line, for the composer.

        The symbolic engine treats this as a proposal: it re-fits the notes to
        its own harmony and phrase structure, so a rough sample still helps.
        """
        score = self.generate(style=style, key=key, time=time, tempo=tempo,
                              bars=bars, temperature=temperature, top_k=top_k,
                              seed=seed)
        out: list[Note] = []
        for part in score.parts:
            for m in part.measures:
                voice = min(m.voices) if m.voices else None
                if voice is None:
                    continue
                for n in m.voices[voice]:
                    if n.grace:
                        continue
                    top = n.top
                    out.append(Note([top] if top else [], n.duration,
                                    velocity=n.velocity))
            break
        return out


def _import_model():
    """Find the model definition, which lives in the training package."""
    candidates = [
        Path(__file__).resolve().parents[3] / "training",
        Path("/root/training"),
        Path.cwd() / "training",
    ]
    for c in candidates:
        if (c / "model.py").exists() and str(c) not in sys.path:
            sys.path.insert(0, str(c))
    try:
        from model import MotifConfig, MotifModel     # type: ignore
    except ImportError as exc:
        raise ModelUnavailable(
            "the model definition (training/model.py) is not importable"
        ) from exc
    return MotifModel, MotifConfig


class _Grammar:
    """Constrain sampling to well-formed sequences.

    A small model will otherwise emit a DUR where a PITCH belongs.  Masking
    impossible continuations costs nothing at inference and removes a whole
    class of decode failures.
    """

    PITCH_IDS = [VOCAB.stoi[f"PITCH_{i}"] for i in range(21, 109)]
    DUR_IDS = [VOCAB.stoi[f"DUR_{i}"] for i in range(1, MAX_DUR + 1)]
    VEL_IDS = [VOCAB.stoi[t] for t in VOCAB.tokens if t.startswith("VEL_")]
    POS_IDS = [VOCAB.stoi[f"POS_{i}"] for i in range(MAX_POS + 1)]
    TRACK_IDS = [VOCAB.stoi[f"TRACK_{i}"] for i in range(4)]
    BAR_ID = VOCAB.stoi["BAR"]
    EOS_ID = VOCAB.eos_id

    def __init__(self, target_bars: int = 16):
        self.target_bars = target_bars

    def mask(self, ids: list[int], torch):
        last = ids[-1] if ids else VOCAB.bos_id
        token = VOCAB.itos.get(last, "")
        bars = sum(1 for i in ids if i == self.BAR_ID)

        if token.startswith("PITCH_"):
            allowed = self.DUR_IDS
        elif token.startswith("DUR_"):
            allowed = self.VEL_IDS
        elif token.startswith("VEL_"):
            allowed = self.PITCH_IDS + self.POS_IDS + self.TRACK_IDS + [self.BAR_ID]
            if bars >= self.target_bars:
                allowed = allowed + [self.EOS_ID]
        elif token.startswith("POS_"):
            allowed = self.TRACK_IDS + self.PITCH_IDS
        elif token.startswith("TRACK_"):
            allowed = self.PITCH_IDS
        elif token == "BAR":
            allowed = self.POS_IDS + self.TRACK_IDS + self.PITCH_IDS
        elif token.startswith("TEMPO_"):
            allowed = [self.BAR_ID]
        else:
            return None                      # conditioning prefix: leave it free

        m = torch.zeros(1, len(VOCAB), dtype=torch.bool)
        m[0, allowed] = True
        return m


def load_if_configured(path: str | None) -> NeuralComposer | None:
    """Best-effort load; the engine must keep working when this fails."""
    if not path:
        return None
    try:
        return NeuralComposer(path)
    except (ModelUnavailable, Exception):
        return None
