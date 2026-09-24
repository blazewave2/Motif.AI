"""The Motif agent: understand a request, act on it, return a score.

Everything here runs on this computer: understanding the request, composing,
and engraving. Nothing is sent anywhere.
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field

from ..compose.composer import compose
from ..composer import arrange as _arrange
from ..composer.core import Composer
from ..control import Cancelled
from ..compose.forms import build_sections
from ..compose.orchestration import INSTRUMENTS, build_instruments
from ..compose.styles import resolve_style
from ..engrave.beaming import apply_beams
from ..engrave.midi import to_midi
from ..engrave.musicxml import to_musicxml
from ..engrave.musicxml_reader import read_musicxml
from ..engrave.preview import summarise
from ..plan import CompositionPlan, InstrumentPlan, SectionPlan
from ..score import Part, Score
from ..theory.pitch import Key
from .analysis import ScoreAnalysis, analyse
from .prompt_parser import ENSEMBLE_WORDS, parse_prompt, parse_key
from .prompt_parser import _detect as _detect_ensemble
from . import voice as _voice

INTENTS = ("create", "continue", "develop", "harmonize", "edit", "analyze")

_CONTINUE_WORDS = ("continue", "carry on", "keep going", "keep writing",
                   "keep composing", "extend", "add more", "what comes next",
                   "next section", "go on", "more of this", "finish this",
                   "complete this", "another", "add a", "add an",
                   "same style", "same voice", "match this style",
                   "match my style", "matching style", "in the same vein",
                   "in this same style", "picks up where", "pick up where",
                   "consistent with this", "keep it in the same")
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
    score_path: str | None = None        # the open score's own file, if it has one
    selection_start: int | None = None   # 1-based bar numbers
    selection_end: int | None = None
    seed: int | None = None
    style: str | None = None
    ensemble: str | None = None
    history: list[dict] = field(default_factory=list)
    use_model: bool = True
    session_id: str | None = None        # the conversation this request belongs to
    cancel: threading.Event | None = None


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
    #: The musician had a score open but it was still blank. A new piece
    #: belongs in that empty page rather than in a second tab beside it.
    open_score_empty: bool = False
    engine: str = "motif"
    title: str = ""
    notes: list[str] = field(default_factory=list)   # what the composer decided
    based_on: str = ""                   # open_score | last_piece
    changed: tuple[int, int] | None = None
    session_id: str = ""


class MotifAgent:
    def __init__(self, model=None, voice_model=None, sessions=None,
                 options: dict | None = None):
        self.model = model
        self.voice_model = voice_model   # optional: rewrites the chat replies
        self.sessions = sessions
        #: Composer settings chosen in the panel, such as how much care to take.
        self.options = options or {}
        self._progress = None        # set for the duration of a single run()
        self._cancel: threading.Event | None = None

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

    def report(self, update) -> None:
        """Pass progress to the panel, and stop here if the musician asked to."""
        if self._cancel is not None and self._cancel.is_set():
            raise Cancelled()
        if self._progress is not None:
            try:
                self._progress(update)
            except Exception:
                pass          # a broken status display must never break composing

    def run(self, req: Request, progress=None) -> Result:
        # The caller already serialises requests through a single lock, so an
        # instance attribute for "the callback for whichever run is
        # currently happening" is safe rather than needing its own lock.
        self._progress = progress
        self._cancel = req.cancel
        started = time.time()
        session = self.sessions.get(req.session_id) if self.sessions is not None else None
        try:
            existing: Score | None = None
            if req.score_xml and req.score_xml.strip():
                try:
                    existing = read_musicxml(req.score_xml)
                except Exception:
                    # An unreadable score is not fatal: fall back to treating
                    # the request as a fresh piece rather than refusing it.
                    existing = None
            info = analyse(existing) if existing is not None else None
            open_score_empty = False
            if info is not None and info.is_empty:
                existing, info = None, None
                open_score_empty = True

            intent = self.classify(req.prompt, existing is not None)
            handler = {
                "create": self._create, "continue": self._continue,
                "develop": self._develop, "harmonize": self._harmonize,
                "edit": self._edit, "analyze": self._analyze,
            }[intent]
            result = handler(req, existing, info)
            result.intent = intent
            result.open_score_empty = open_score_empty
            if existing is not None and intent != "create":
                result.based_on = "open_score"
            if not result.title and result.plan is not None:
                result.title = result.plan.title
        except Cancelled:
            return Result(ok=False, intent="cancelled", error="cancelled",
                          message="Stopped. Nothing was changed.",
                          session_id=session.id if session else "",
                          elapsed_ms=int((time.time() - started) * 1000))
        except Exception as exc:              # never crash the plugin
            import traceback
            return Result(ok=False, error=f"{type(exc).__name__}: {exc}",
                          message="Motif could not complete that request.",
                          analysis=traceback.format_exc(limit=3),
                          session_id=session.id if session else "",
                          elapsed_ms=int((time.time() - started) * 1000))
        result.elapsed_ms = int((time.time() - started) * 1000)
        if session is not None:
            result.session_id = session.id
            session.add("musician", req.prompt)
            session.add("motif", result.message, action=result.intent)
            if result.title:
                session.title = result.title
            if result.plan is not None:
                session.plan = json.loads(result.plan.to_json())
            self.sessions.save(session)
        return result

    # ------------------------------------------------------------------
    def _plan_for(self, req: Request, seed_hint: int | None = None) -> CompositionPlan:
        plan = parse_prompt(req.prompt, seed=req.seed if req.seed is not None else seed_hint)
        if req.style:
            plan.style = resolve_style(req.style).name
        if req.ensemble:
            plan.ensemble = req.ensemble
            plan.instruments = build_instruments(req.ensemble)
        return plan

    def _compose(self, plan: CompositionPlan) -> tuple[Score, list[str], dict]:
        """Motif's composer writes the piece; concertos, which it does not
        yet score, still go to the earlier engine."""
        ensemble = plan.ensemble or "solo_piano"
        if not plan.movements and (ensemble == "solo_piano" or _arrange.supported(ensemble)):
            composer = Composer(plan, quality=self.options.get("quality", "best"),
                                progress=self.report)
            score = composer.compose()
            plan.tempo = int(composer.tempo)
            plan.tempo_text = composer.tempo_text
            plan.time = tuple(composer.time)
            return score, list(composer.notes), dict(composer.summary)
        return compose(plan, self.model, progress=self.report), [], {}

    def _finish(self, plan: CompositionPlan, message,
                warnings: list[str] | None = None) -> Result:
        """Compose ``plan``. ``message`` is the reply, or a function of the
        plan and what the composer decided that writes it."""
        score, notes, summary = self._compose(plan)
        if callable(message):
            message = message(plan, summary)
        return Result(ok=True, message=message, musicxml=to_musicxml(score),
                      midi=to_midi(score), plan=plan, preview=summarise(score),
                      analysis=analyse(score).describe(), warnings=warnings or [],
                      notes=notes)

    # -- intents --------------------------------------------------------
    def _create(self, req: Request, existing, info) -> Result:
        plan = self._plan_for(req)
        style = resolve_style(plan.style)

        def message(p: CompositionPlan, summary: dict) -> str:
            if summary:
                return _voice.composed_message(p, summary, self.voice_model)
            return _voice.created_message(p, style, self.voice_model)
        return self._finish(plan, message)

    def _continue(self, req: Request, existing: Score, info: ScoreAnalysis) -> Result:
        """Add new music that follows on from what is already written."""
        plan = self._plan_for(req)
        # The existing score wins on every musical parameter the user did not
        # explicitly override; continuing in a different key is not continuing,
        # and continuing a concerto is not continuing it as a solo piano line.
        stated_tonic, stated_mode = parse_key(req.prompt.lower(), req.prompt)
        if not stated_tonic:
            plan.key = str(info.key)
        plan.time = info.time
        if not re.search(r"\d{2,3}\s*bpm", req.prompt.lower()):
            plan.tempo = int(info.tempo)
        if not any(s in req.prompt.lower() for s in ("style of", "like ", "in the manner")):
            plan.style = info.detected_style
        style = resolve_style(plan.style)
        if not req.ensemble and not _ensemble_named_in(req.prompt):
            plan.instruments = _instruments_from_score(existing)
            if info.ensemble:
                plan.ensemble = info.ensemble

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
        result.message = _voice.continued_message(
            plan, existing.title, bars, info, self.voice_model)
        return result

    def _develop(self, req: Request, existing: Score, info: ScoreAnalysis) -> Result:
        plan = self._plan_for(req)
        stated_tonic, _ = parse_key(req.prompt.lower(), req.prompt)
        if not stated_tonic:
            plan.key = str(info.key)
        plan.time = info.time
        # Same guard as continuing: a style or ensemble named in the request
        # wins, otherwise the piece already open decides both.
        if not any(s in req.prompt.lower() for s in ("style of", "like ", "in the manner")):
            plan.style = info.detected_style
        if not req.ensemble and not _ensemble_named_in(req.prompt):
            plan.instruments = _instruments_from_score(existing)
            if info.ensemble:
                plan.ensemble = info.ensemble
        for s in plan.sections:
            s.motif_op = "develop" if s.motif_op == "state" else s.motif_op
            s.energy = min(1.0, s.energy + 0.12)
        return self._finish(plan, _voice.developed_message(
            plan, existing.title, self.voice_model))

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

        generated = compose(plan, self.model, progress=self.report)
        merged = _graft_melody(existing, generated)
        message = _voice.harmonized_message(
            plan, existing.title, bars, style, plan.sections[0].texture_lh, self.voice_model)
        return Result(ok=True, message=message,
            musicxml=to_musicxml(merged), midi=to_midi(merged), plan=plan,
            preview=summarise(merged), analysis=analyse(merged).describe())

    def _edit(self, req: Request, existing: Score, info: ScoreAnalysis) -> Result:
        """Direct transformations of the score that is already there."""
        t = req.prompt.lower()
        score = existing
        applied: list[str] = []

        tonic, mode = parse_key(t, req.prompt)
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
# matching the instrumentation already on the page
# ---------------------------------------------------------------------------
def _ensemble_named_in(prompt: str) -> str | None:
    """Whether the request itself names an ensemble or instrumentation.

    Distinguishes "continue this for string quartet instead" from a plain
    "continue this piece" — only the former should change what is playing.
    """
    return _detect_ensemble(prompt.lower(), ENSEMBLE_WORDS)


def _instruments_from_score(score: Score) -> list[InstrumentPlan]:
    """Rebuild an instrument list that matches what is already on the page.

    "The same style" has to mean the same forces too: continuing a concerto
    is not continuing it as a solo piano line. Each part is matched back to
    the General MIDI instrument it was written for, which recovers a proper
    playable range and role even though that information is not itself
    stored in MusicXML; a part that cannot be matched falls back to its own
    observed range instead of a guess that could sit outside it.
    """
    plans: list[InstrumentPlan] = []
    solo = len(score.parts) == 1
    for part in score.parts:
        spec = _instrument_spec_for(part)
        clefs = [part.clefs.get(i + 1, "G") for i in range(max(1, part.staves))]
        if spec:
            plans.append(InstrumentPlan(
                name=part.name, abbreviation=part.abbreviation or part.name[:4],
                midi_program=part.midi_program, staves=max(1, part.staves),
                clefs=clefs, role=spec["role"],
                range_low=spec["low"], range_high=spec["high"]))
        else:
            lo, hi = _observed_range(part)
            plans.append(InstrumentPlan(
                name=part.name, abbreviation=part.abbreviation or part.name[:4],
                midi_program=part.midi_program, staves=max(1, part.staves),
                clefs=clefs, role="solo" if solo else "harmony",
                range_low=max(21, lo - 3), range_high=min(108, hi + 3)))
    return plans


def _instrument_spec_for(part: Part) -> dict | None:
    """Look an existing part up in the General MIDI instrument table."""
    key = part.name.strip().lower().replace(" ", "_").replace(".", "")
    aliases = {"violin_1": "violin_i", "violin_2": "violin_ii",
               "violoncello": "cello", "double_bass": "contrabass",
               "string_bass": "contrabass", "horn_in_f": "horn",
               "french_horn": "horn"}
    key = aliases.get(key, key)
    if key in INSTRUMENTS:
        return INSTRUMENTS[key]
    for spec in INSTRUMENTS.values():
        if spec["program"] == part.midi_program:
            return spec
    return None


def _observed_range(part: Part) -> tuple[int, int]:
    lo = hi = None
    for m in part.measures:
        for notes in m.voices.values():
            for n in notes:
                for p in n.pitches:
                    lo = p.midi if lo is None else min(lo, p.midi)
                    hi = p.midi if hi is None else max(hi, p.midi)
    return (lo, hi) if lo is not None else (48, 84)


# ---------------------------------------------------------------------------
# score surgery
# ---------------------------------------------------------------------------
def _append_scores(base: Score, addition: Score) -> Score:
    """Concatenate ``addition`` after ``base``.

    Parts are matched by instrument identity (name and General MIDI program),
    not by position — a positional match is only correct when the
    instrumentation has not changed, and pastes one instrument's line under
    another's name the moment it has. In the ordinary case (continuing with
    the same forces) every part finds its match and this is a plain append.

    When a continuation is explicitly asked for with different or larger
    forces, an unmatched base part falls silent from here on (it is not part
    of what continues), and an unmatched addition part is added as a new
    part, silent for everything already written, carrying the new material
    from where it enters — a real, legible instrumentation change, not a
    smear of mismatched material into the wrong staff.
    """
    offset = base.measure_count
    new_bars = addition.measure_count
    used: set[int] = set()

    for part in base.parts:
        match = _find_matching_part(part, addition.parts, used)
        if match is not None:
            used.add(match)
            _copy_measures_into(part, addition.parts[match].measures, offset)
        else:
            _pad_with_silence(part, base.time, len(part.measures), new_bars)
        if part.measures:
            part.measures[-1].barline = "light-heavy"

    for i, extra in enumerate(addition.parts):
        if i in used:
            continue
        new_part = _new_part_like(extra, len(base.parts))
        _pad_with_silence(new_part, base.time, 0, offset)
        _copy_measures_into(new_part, extra.measures, offset)
        if new_part.measures:
            new_part.measures[-1].barline = "light-heavy"
        base.parts.append(new_part)

    for tm in addition.tempos:
        if tm.measure > 1:
            base.tempos.append(type(tm)(tm.measure + offset, tm.bpm, tm.beat_unit,
                                        tm.text, tm.dotted))

    # The reader that parsed ``base`` back in from disk never restores beam
    # info (MusicXML leaves grouping entirely to each note), so the bars that
    # already existed would otherwise print unbeamed even though the newly
    # composed bars are. Recomputing over the whole score is cheap and keeps
    # both halves looking like one piece.
    for part in base.parts:
        apply_beams(part, base.time)
    return base


def _find_matching_part(part: Part, candidates: list[Part], used: set[int]) -> int | None:
    for i, cand in enumerate(candidates):
        if i not in used and cand.name == part.name and cand.midi_program == part.midi_program:
            return i
    return None


def _copy_measures_into(part: Part, measures, offset: int) -> None:
    for m in measures:
        copy = _copy_measure(m)
        copy.number = offset + m.number
        if m.number == 1:
            copy.key = m.key
        part.measures.append(copy)


def _pad_with_silence(part: Part, time: tuple[int, int], start: int, count: int) -> None:
    """Fill ``count`` bars from ``start`` with a full-bar rest in every voice."""
    from ..engrave.layout import fill_empty_measures
    from ..score import bar_duration
    bar_ticks = bar_duration(tuple(time))
    for n in range(1, count + 1):
        part.measure(start + n)
    vs = [(1, 1)] if part.staves == 1 else [(1, 1), (5, 2)]
    fill_empty_measures(part, bar_ticks, vs)


def _new_part_like(src: Part, index: int) -> Part:
    """A fresh, empty part carrying ``src``'s instrument identity."""
    import copy as _copy
    part = _copy.deepcopy(src)
    part.measures = []
    part.id = f"P{index + 1}"
    part.midi_channel = min(16, index + 1)
    return part


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


