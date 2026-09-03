"""The Motif agent: understand a request, act on it, return a score.

Intent routing is deterministic and local.  A configured LLM planner refines
the plan when available, but every path here works without one.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from ..compose.composer import compose
from ..compose.forms import build_sections
from ..compose.orchestration import build_instruments
from ..compose.styles import resolve_style
from ..engrave.midi import to_midi
from ..engrave.musicxml import to_musicxml
from ..engrave.musicxml_reader import read_musicxml
from ..engrave.preview import summarise
from ..plan import CompositionPlan, InstrumentPlan, SectionPlan
from ..score import Score
from ..theory.pitch import Key, Pitch
from .analysis import ScoreAnalysis, analyse
from .prompt_parser import parse_prompt, parse_key

INTENTS = ("create", "continue", "develop", "harmonize", "edit", "analyze")

_CONTINUE_WORDS = ("continue", "carry on", "keep going", "extend", "add more",
                   "what comes next", "next section", "go on", "more of this",
                   "finish this", "complete this", "another", "add a", "add an")
_DEVELOP_WORDS = ("develop", "vary", "variation", "elaborate", "expand on",
                  "build on", "take this", "rework", "reimagine")
_HARMONIZE_WORDS = ("harmonize", "harmonise", "add accompaniment", "accompany",
                    "add chords", "add a left hand", "add bass", "add harmony")
_EDIT_WORDS = ("transpose", "make it", "change the", "slower", "faster", "louder",
               "softer", "quieter", "more dramatic", "less", "simplify", "in the key of")
_ANALYZE_WORDS = ("analyze", "analyse", "what key", "what is this", "describe",
                  "tell me about", "what chords", "explain")


@dataclass
class Request:
    prompt: str = ""
    score_xml: str | None = None
    selection_start: int | None = None   # 1-based bar numbers
    selection_end: int | None = None
    seed: int | None = None
    style: str | None = None
    ensemble: str | None = None
    history: list[dict] = field(default_factory=list)
    use_model: bool = True


@dataclass
class Result:
    ok: bool = True
    intent: str = "create"
    message: str = ""
    musicxml: str = ""
    midi: bytes = b""
    plan: CompositionPlan | None = None
    analysis: str = ""
    preview: str = ""
    elapsed_ms: int = 0
    error: str = ""
    warnings: list[str] = field(default_factory=list)


class MotifAgent:
    def __init__(self, model=None, planner=None):
        self.model = model
        self.planner = planner       # optional LLM planner

    # ------------------------------------------------------------------
    def classify(self, prompt: str, has_score: bool) -> str:
        t = " " + prompt.lower().strip() + " "
        if any(w in t for w in _ANALYZE_WORDS):
            return "analyze" if has_score else "create"
        if not has_score:
            return "create"
        if any(w in t for w in _HARMONIZE_WORDS):
            return "harmonize"
        if any(w in t for w in _CONTINUE_WORDS):
            return "continue"
        if any(w in t for w in _DEVELOP_WORDS):
            return "develop"
        if any(w in t for w in _EDIT_WORDS):
            return "edit"
        # A bare descriptive request with a score present means a new piece.
        return "create"

    def run(self, req: Request) -> Result:
        started = time.time()
        try:
            existing: Score | None = None
            if req.score_xml and req.score_xml.strip():
                try:
                    existing = read_musicxml(req.score_xml)
                except Exception as exc:
                    existing = None
            info = analyse(existing) if existing is not None else None
            if info is not None and info.is_empty:
                existing, info = None, None

            intent = self.classify(req.prompt, existing is not None)
            handler = {
                "create": self._create, "continue": self._continue,
                "develop": self._develop, "harmonize": self._harmonize,
                "edit": self._edit, "analyze": self._analyze,
            }[intent]
            result = handler(req, existing, info)
            result.intent = intent
            result.elapsed_ms = int((time.time() - started) * 1000)
            return result
        except Exception as exc:              # never crash the plugin
            import traceback
            return Result(ok=False, error=f"{type(exc).__name__}: {exc}",
                          message="Motif could not complete that request.",
                          analysis=traceback.format_exc(limit=3),
                          elapsed_ms=int((time.time() - started) * 1000))

    # ------------------------------------------------------------------
    def _plan_for(self, req: Request, seed_hint: int | None = None) -> CompositionPlan:
        plan = parse_prompt(req.prompt, seed=req.seed if req.seed is not None else seed_hint)
        if req.style:
            plan.style = resolve_style(req.style).name
        if req.ensemble:
            plan.ensemble = req.ensemble
            plan.instruments = build_instruments(req.ensemble)
        if self.planner is not None:
            try:
                plan = self.planner.refine(req.prompt, plan)
            except Exception:
                pass                          # the local plan is always usable
        return plan

    def _finish(self, plan: CompositionPlan, message: str,
                warnings: list[str] | None = None) -> Result:
        score = compose(plan, self.model)
        return Result(ok=True, message=message, musicxml=to_musicxml(score),
                      midi=to_midi(score), plan=plan, preview=summarise(score),
                      analysis=analyse(score).describe(), warnings=warnings or [])

    # -- intents --------------------------------------------------------
    def _create(self, req: Request, existing, info) -> Result:
        plan = self._plan_for(req)
        style = resolve_style(plan.style)
        return self._finish(plan, _created_message(plan, style))

    def _continue(self, req: Request, existing: Score, info: ScoreAnalysis) -> Result:
        """Add new music that follows on from what is already written."""
        plan = self._plan_for(req)
        # The existing score wins on every musical parameter the user did not
        # explicitly override; continuing in a different key is not continuing.
        stated_tonic, stated_mode = parse_key(req.prompt.lower())
        if not stated_tonic:
            plan.key = str(info.key)
        plan.time = info.time
        if not re.search(r"\d{2,3}\s*bpm", req.prompt.lower()):
            plan.tempo = int(info.tempo)
        if not any(s in req.prompt.lower() for s in ("style of", "like ", "in the manner")):
            plan.style = info.detected_style
        style = resolve_style(plan.style)

        bars = plan.total_bars or 16
        key = Key.parse(plan.key)
        import random
        rng = random.Random(plan.seed)
        sections = build_sections("through_composed", key, style, rng, max(8, bars))
        for i, s in enumerate(sections):
            s.motif_op = "develop" if i else "recall"
            s.role = "development" if i else "theme"
        plan.sections = sections
        plan.title = existing.title or plan.title
        plan.subtitle = existing.subtitle or plan.subtitle

        result = self._finish(plan, "")
        merged = _append_scores(existing, read_musicxml(result.musicxml))
        result.musicxml = to_musicxml(merged)
        result.midi = to_midi(merged)
        result.preview = summarise(merged)
        result.message = (f"Continued **{existing.title}** with {bars} new bars in "
                          f"{plan.key}, following the existing {info.time[0]}/"
                          f"{info.time[1]} at ♩ = {int(plan.tempo)}. "
                          f"The new material develops the closing idea.")
        return result

    def _develop(self, req: Request, existing: Score, info: ScoreAnalysis) -> Result:
        plan = self._plan_for(req)
        stated_tonic, _ = parse_key(req.prompt.lower())
        if not stated_tonic:
            plan.key = str(info.key)
        plan.time = info.time
        for s in plan.sections:
            s.motif_op = "develop" if s.motif_op == "state" else s.motif_op
            s.energy = min(1.0, s.energy + 0.12)
        return self._finish(plan, f"Developed the material from **{existing.title}** "
                                  f"into a new {plan.form.replace('_', ' ')} of "
                                  f"{plan.total_bars} bars in {plan.key}.")

    def _harmonize(self, req: Request, existing: Score, info: ScoreAnalysis) -> Result:
        """Keep the user's melody, write an accompaniment underneath it."""
        plan = self._plan_for(req)
        plan.key = str(info.key)
        plan.time = info.time
        plan.tempo = int(info.tempo)
        style = resolve_style(plan.style if req.style else info.detected_style)
        plan.style = style.name

        import random
        rng = random.Random(plan.seed)
        bars = max(1, existing.measure_count)
        plan.sections = build_sections("through_composed", Key.parse(plan.key),
                                       style, rng, bars)
        _fit_section_bars(plan.sections, bars)

        generated = compose(plan, self.model)
        merged = _graft_melody(existing, generated)
        return Result(ok=True, message=(
            f"Harmonised {bars} bars of **{existing.title}** in {plan.key}. "
            f"Your melody is untouched on the upper staff; the accompaniment "
            f"is a {style.display}-style {plan.sections[0].texture_lh.replace('_', ' ')} "
            f"left hand."),
            musicxml=to_musicxml(merged), midi=to_midi(merged), plan=plan,
            preview=summarise(merged), analysis=analyse(merged).describe())

    def _edit(self, req: Request, existing: Score, info: ScoreAnalysis) -> Result:
        """Direct transformations of the score that is already there."""
        t = req.prompt.lower()
        score = existing
        applied: list[str] = []

        tonic, mode = parse_key(t)
        if tonic and ("transpose" in t or "in the key of" in t or "into" in t):
            target = Key(tonic, mode or ("minor" if info.key.is_minor else "major"))
            semis = (target.tonic_pc - info.key.tonic_pc) % 12
            if semis > 6:
                semis -= 12
            score = _transpose(score, semis, target)
            applied.append(f"transposed to {target}")

        factor = None
        if any(w in t for w in ("slower", "slow it", "less quickly", "calmer tempo")):
            factor = 0.82
        elif any(w in t for w in ("faster", "quicker", "speed", "speed it up")):
            factor = 1.22
        mbpm = re.search(r"(\d{2,3})\s*bpm", t)
        if mbpm:
            score.tempo = float(max(30, min(240, int(mbpm.group(1)))))
            for tm in score.tempos:
                tm.bpm = score.tempo
            applied.append(f"tempo set to {int(score.tempo)} bpm")
        elif factor:
            score.tempo = max(30.0, min(240.0, score.tempo * factor))
            for tm in score.tempos:
                tm.bpm = max(30.0, min(240.0, tm.bpm * factor))
            applied.append(f"tempo now ♩ = {int(score.tempo)}")

        step = 0
        if any(w in t for w in ("louder", "stronger", "more powerful", "more dramatic",
                                "bigger", "more intense")):
            step = 1
        elif any(w in t for w in ("softer", "quieter", "gentler", "calmer", "lighter")):
            step = -1
        if step:
            _shift_dynamics(score, step)
            applied.append("louder" if step > 0 else "softer")

        if not applied:
            # Nothing directly editable: reinterpret as a fresh piece in the
            # same key so the request still produces music.
            plan = self._plan_for(req)
            plan.key = str(info.key)
            plan.time = info.time
            return self._finish(plan, (
                f"I read that as a new piece rather than an edit, so here is a "
                f"{plan.total_bars}-bar {plan.form.replace('_', ' ')} in {plan.key}."))

        return Result(ok=True, message="Applied: " + ", ".join(applied) + ".",
                      musicxml=to_musicxml(score), midi=to_midi(score),
                      preview=summarise(score), analysis=analyse(score).describe())

    def _analyze(self, req: Request, existing: Score, info: ScoreAnalysis) -> Result:
        chords = " | ".join(info.chord_summary[:16]) or "—"
        msg = (f"**{existing.title}**\n\n{info.describe()}\n\n"
               f"Harmony by bar: {chords}\n\n"
               f"{info.note_count} notes, average density {info.density:.2f}.")
        return Result(ok=True, message=msg, musicxml="", preview=summarise(existing),
                      analysis=info.describe())


# ---------------------------------------------------------------------------
# score surgery
# ---------------------------------------------------------------------------
def _append_scores(base: Score, addition: Score) -> Score:
    """Concatenate ``addition`` after ``base``, matching part counts."""
    offset = base.measure_count
    for i, part in enumerate(base.parts):
        src = addition.parts[i] if i < len(addition.parts) else addition.parts[0]
        for m in src.measures:
            copy = _copy_measure(m)
            copy.number = offset + m.number
            if m.number == 1:
                copy.key = m.key
            part.measures.append(copy)
        if part.measures:
            part.measures[-1].barline = "light-heavy"
    for tm in addition.tempos:
        if tm.measure > 1:
            base.tempos.append(type(tm)(tm.measure + offset, tm.bpm, tm.beat_unit,
                                        tm.text, tm.dotted))
    return base


def _copy_measure(m):
    import copy
    return copy.deepcopy(m)


def _graft_melody(original: Score, generated: Score) -> Score:
    """Put the user's melody on top of a freshly generated accompaniment."""
    import copy
    out = copy.deepcopy(generated)
    src = original.parts[0]
    dst = out.parts[0]
    for i, m in enumerate(src.measures):
        if i >= len(dst.measures):
            break
        top_voice = min(m.voices) if m.voices else None
        if top_voice is None:
            continue
        melody = [n for n in m.voices[top_voice]]
        target = dst.measures[i]
        target.voices[1] = [_restaff(n, 1, 1) for n in melody]
    return out


def _restaff(note, voice: int, staff: int):
    n = note.copy()
    n.voice, n.staff = voice, staff
    return n


def _transpose(score: Score, semitones: int, target: Key) -> Score:
    score.key = target
    for part in score.parts:
        for m in part.measures:
            if m.key is not None:
                m.key = target
            for notes in m.voices.values():
                for n in notes:
                    n.pitches = [target.spell(max(0, min(127, p.midi + semitones)))
                                 for p in n.pitches]
    return score


_DYN = ["ppp", "pp", "p", "mp", "mf", "f", "ff", "fff"]


def _shift_dynamics(score: Score, step: int) -> None:
    for part in score.parts:
        for m in part.measures:
            for d in m.directions:
                if d.kind == "dynamics" and d.value in _DYN:
                    i = _DYN.index(d.value)
                    d.value = _DYN[max(0, min(len(_DYN) - 1, i + step))]
            for notes in m.voices.values():
                for n in notes:
                    n.velocity = max(1, min(127, n.velocity + step * 14))


def _fit_section_bars(sections: list[SectionPlan], total: int) -> None:
    if not sections:
        return
    have = sum(s.bars for s in sections)
    if have == total:
        return
    scale = total / max(1, have)
    for s in sections:
        s.bars = max(1, int(round(s.bars * scale)))
    drift = total - sum(s.bars for s in sections)
    sections[-1].bars = max(1, sections[-1].bars + drift)


def _created_message(plan: CompositionPlan, style) -> str:
    forces = {"solo_piano": "solo piano", "piano_concerto": "piano and orchestra",
              "string_quartet": "string quartet", "piano_trio": "piano trio",
              "string_orchestra": "string orchestra", "orchestra": "orchestra",
              "violin_piano": "violin and piano", "cello_piano": "cello and piano",
              "voice_piano": "voice and piano", "chamber": "chamber ensemble",
              }.get(plan.ensemble, plan.ensemble.replace("_", " "))
    bits = [f"**{plan.title}** — a {plan.total_bars}-bar "
            f"{plan.form.replace('_', ' ')} for {forces} in {plan.key}, "
            f"{plan.time[0]}/{plan.time[1]} at ♩ = {plan.tempo}"]
    if plan.tempo_text:
        bits.append(f" ({plan.tempo_text})")
    bits.append(f", written in a {style.display} idiom.")
    if plan.character:
        bits.append(f" Character: {plan.character}.")
    labels = " → ".join(s.label for s in plan.sections[:9])
    if labels:
        bits.append(f"\n\nStructure: {labels}.")
    if plan.notes:
        bits.append(f"\n\n_{plan.notes}_")
    return "".join(bits)
