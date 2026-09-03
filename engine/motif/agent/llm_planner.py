"""Optional plan refinement with Claude.

Motif's local parser already produces a complete, playable plan.  When an API
key is configured, Claude revises that plan — the structure, the key scheme,
the section-by-section character — which is where a language model genuinely
helps.  It never writes notes: every pitch still comes from the music engine.

Uses urllib so the engine keeps its zero-dependency install.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict

from ..compose.forms import FORMS
from ..compose.orchestration import ENSEMBLES, build_instruments
from ..compose.styles import STYLES
from ..compose.textures import TEXTURES
from ..plan import CompositionPlan, SectionPlan

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5"

SYSTEM = """You are the planning stage of Motif.ai, a composing engine for MuseScore.

You receive a musician's request and a draft plan produced by a deterministic
parser. Revise the draft so it best serves the request. You do not write notes:
a symbolic music engine renders every pitch from your plan.

Return ONLY a JSON object, no prose and no code fences, with these keys:
  title, style, key, time, tempo, tempo_text, form, character, ensemble, sections

Rules:
- "key" is like "Eb minor" or "D major". "time" is a two-element array, e.g. [3, 4].
- "tempo" is an integer BPM.
- Every value for style, form, ensemble and texture MUST come from the allowed
  lists you are given. Anything else is rejected and the draft is used instead.
- "sections" is an ordered list. Each section has: label, bars (integer),
  key, energy (0..1), dynamic (ppp..fff), texture_lh, texture_rh
  (melody|chordal|figuration|counterpoint), cadence, motif_op
  (state|develop|invert|sequence|fragment|augment|recall), harmonic_rhythm
  (slow|moderate|fast), register (-1..1), role
  (intro|theme|transition|development|recap|cadenza|coda), text, solo, tutti.
- Total bars should match what the request implies. Respect any key, metre,
  tempo or length the musician stated explicitly.
- Build a real dramatic arc: energy should rise to one clear climax and resolve.
- Keep the same motif working across sections; that is what makes it cohere."""


class LLMPlanner:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, timeout: float = 45.0):
        if not api_key:
            raise ValueError("an API key is required")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def refine(self, prompt: str, draft: CompositionPlan) -> CompositionPlan:
        """Return an improved plan, or the draft unchanged on any problem."""
        try:
            reply = self._call(prompt, draft)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return draft
        if not reply:
            return draft
        try:
            return self._merge(draft, reply)
        except (KeyError, TypeError, ValueError):
            return draft

    # ------------------------------------------------------------------
    def _call(self, prompt: str, draft: CompositionPlan) -> dict | None:
        payload = {
            "model": self.model,
            "max_tokens": 4000,
            "system": SYSTEM,
            "messages": [{"role": "user", "content": self._user_message(prompt, draft)}],
        }
        req = urllib.request.Request(
            API_URL, data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json",
                     "x-api-key": self.api_key,
                     "anthropic-version": API_VERSION},
            method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        for block in body.get("content", []):
            if block.get("type") == "text":
                return _extract_json(block.get("text", ""))
        return None

    def _user_message(self, prompt: str, draft: CompositionPlan) -> str:
        allowed = {
            "styles": sorted(STYLES),
            "forms": sorted(FORMS),
            "ensembles": sorted(ENSEMBLES),
            "textures_lh": sorted(TEXTURES),
            "textures_rh": ["melody", "chordal", "figuration", "counterpoint"],
        }
        draft_json = json.loads(draft.to_json())
        draft_json.pop("movements", None)
        draft_json.pop("instruments", None)
        return (f"Musician's request:\n{prompt}\n\n"
                f"Allowed values:\n{json.dumps(allowed)}\n\n"
                f"Draft plan:\n{json.dumps(draft_json)}\n\n"
                f"Return the revised plan as JSON.")

    # ------------------------------------------------------------------
    def _merge(self, draft: CompositionPlan, data: dict) -> CompositionPlan:
        """Apply only the fields that validate; the draft covers the rest."""
        plan = CompositionPlan(**{k: v for k, v in asdict(draft).items()
                                  if k not in ("sections", "instruments", "movements")})
        plan.sections = list(draft.sections)
        plan.instruments = list(draft.instruments)

        if isinstance(data.get("title"), str) and data["title"].strip():
            plan.title = data["title"].strip()[:120]
        if data.get("style") in STYLES:
            plan.style = data["style"]
        if data.get("form") in FORMS:
            plan.form = data["form"]
        if isinstance(data.get("key"), str):
            from ..theory.pitch import Key
            try:
                plan.key = str(Key.parse(data["key"]))
            except (ValueError, KeyError, IndexError):
                pass                       # keep the draft's key
        t = data.get("time")
        if (isinstance(t, (list, tuple)) and len(t) == 2
                and all(isinstance(x, int) for x in t)
                and 1 <= t[0] <= 32 and t[1] in (1, 2, 4, 8, 16)):
            plan.time = (int(t[0]), int(t[1]))
        if isinstance(data.get("tempo"), (int, float)) and 20 <= data["tempo"] <= 260:
            plan.tempo = int(data["tempo"])
        if isinstance(data.get("tempo_text"), str):
            plan.tempo_text = data["tempo_text"][:60]
        if isinstance(data.get("character"), str):
            plan.character = data["character"][:120]
        if data.get("ensemble") in ENSEMBLES and data["ensemble"] != plan.ensemble:
            plan.ensemble = data["ensemble"]
            plan.instruments = build_instruments(plan.ensemble)

        sections = self._sections(data.get("sections"))
        if sections:
            plan.sections = sections
        return plan

    def _sections(self, raw) -> list[SectionPlan]:
        if not isinstance(raw, list) or not raw:
            return []
        valid_rh = {"melody", "chordal", "figuration", "counterpoint"}
        valid_op = {"state", "develop", "invert", "sequence", "fragment",
                    "augment", "recall"}
        valid_hr = {"slow", "moderate", "fast", "very_fast"}
        out: list[SectionPlan] = []
        total = 0
        for item in raw[:64]:
            if not isinstance(item, dict):
                continue
            bars = item.get("bars")
            if not isinstance(bars, int) or not (1 <= bars <= 512):
                continue
            total += bars
            if total > 2000:            # refuse an unbounded score
                break
            s = SectionPlan(
                label=str(item.get("label", "A"))[:24],
                bars=bars,
                key=str(item.get("key", "C major"))[:32],
                energy=_clamp(item.get("energy", 0.5), 0.0, 1.0),
                dynamic=item["dynamic"] if item.get("dynamic") in
                        ("ppp", "pp", "p", "mp", "mf", "f", "ff", "fff") else "mf",
                texture_lh=item["texture_lh"] if item.get("texture_lh") in TEXTURES
                           else "block_chords",
                texture_rh=item["texture_rh"] if item.get("texture_rh") in valid_rh
                           else "melody",
                cadence=str(item.get("cadence", "authentic"))[:24],
                motif_op=item["motif_op"] if item.get("motif_op") in valid_op else "develop",
                harmonic_rhythm=item["harmonic_rhythm"]
                                if item.get("harmonic_rhythm") in valid_hr else "moderate",
                register=int(_clamp(item.get("register", 0), -1, 1)),
                role=str(item.get("role", "theme"))[:24],
                text=str(item.get("text", ""))[:60],
                solo=bool(item.get("solo", False)),
                tutti=bool(item.get("tutti", False)))
            # A key the engine cannot parse would break every note in the section.
            from ..theory.pitch import Key
            try:
                Key.parse(s.key)
            except (ValueError, KeyError):
                s.key = "C major"
            out.append(s)
        return out


def _clamp(v, lo, hi):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return (lo + hi) / 2


def _extract_json(text: str) -> dict | None:
    """Pull the JSON object out of a reply that may be fenced or chatty."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start, depth = text.find("{"), 0
    if start < 0:
        return None
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None
