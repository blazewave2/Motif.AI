"""Turn an ordered verbal arc into an executable section map.

The style profile supplies idioms; the brief supplies the musician's dramatic
decisions.  This stage stays deterministic and runs without a language model.
It only interprets directions we can actually render, leaving the remaining
words in the original prompt for a future planner.
"""
from __future__ import annotations

import re

from ..plan import SectionPlan
from ..theory.pitch import Key

_BOUNDARY = re.compile(r"\b(?:and\s+)?then\b|\bfinally\b|\bat the end\b", re.I)
_DYNAMICS = re.compile(r"(?<!\w)(ppp|pp|mp|mf|fff|ff|p|f)(?!\w)", re.I)
_MARKINGS = ("cantabile", "dolce", "espressivo", "agitato", "maestoso",
             "sotto voce", "morendo", "con fuoco", "lamentoso")
_TEXTURES = {
    "arpeggio": ("arpeggio", "arpeggios", "arpeggiated"),
    "tremolo": ("tremolo", "tremolos"),
    "octave_bass": ("octave bass", "bass octaves"),
    "nocturne": ("nocturne accompaniment", "flowing left hand"),
    "block_chords": ("block chords", "chordal accompaniment"),
    "sustained": ("sustained chords", "held chords"),
}


def _weight_bars(sections: list[SectionPlan], target: int) -> None:
    """Apportion bars exactly, keeping each surviving section at least one bar."""
    if not sections:
        return
    if len(sections) > target:
        del sections[target:]
    weights = [max(1, s.bars) for s in sections]
    free = target - len(sections)
    total = sum(weights)
    quotas = [free * w / total for w in weights]
    lengths = [1 + int(q) for q in quotas]
    remainder = target - sum(lengths)
    order = sorted(range(len(sections)), key=lambda i: (quotas[i] % 1, -i), reverse=True)
    for i in order[:remainder]:
        lengths[i] += 1
    for section, length in zip(sections, lengths):
        section.bars = length


def apply_narrated_arc(prompt: str, template: list[SectionPlan], key: Key,
                       style, target: int, parse_key, moods: dict, shift_dynamic) -> list[SectionPlan]:
    """Compile ordered clauses to sections and fulfil the specified length.

    Deliberately require an ordering word. Ordinary prose, including words
    like 'middle' or 'return', keeps its composer's existing formal template.
    """
    clauses = [s.strip(" ,.;:") for s in _BOUNDARY.split(prompt) if s.strip(" ,.;:")]
    if len(clauses) < 2 or len(clauses) > 5:
        _weight_bars(template, target)
        return template

    sections: list[SectionPlan] = []
    for i, clause in enumerate(clauses):
        t = clause.lower()
        is_return = i > 0 and any(w in t for w in
                                  ("return", "recap", "reprise", "original theme", "opening theme"))
        is_end = i == len(clauses) - 1 and any(w in t for w in
                                                ("end", "close", "fade", "die away", "coda", "quietly"))
        role = "theme" if i == 0 else "coda" if is_end else "recap" if is_return else "development"
        operation = "state" if i == 0 else "recall" if is_return else "fragment" if is_end else "develop"
        energy = 0.44 if i == 0 else 0.67
        dyn = "mp" if i == 0 else "mf"
        for name, spec in moods.items():
            if any(re.search(r"\b" + re.escape(word) + r"\b", t) for word in spec["words"]):
                energy += spec["energy"] * 0.7
                dyn = shift_dynamic(dyn, int(round(spec["dyn"])))
        if any(w in t for w in ("climax", "thunder", "explosive", "massive")):
            energy, dyn = 0.96, "ff"
        if any(w in t for w in ("fade", "die away", "whisper")):
            energy, dyn = 0.18, "pp"
        if match := _DYNAMICS.search(clause):
            dyn = match.group(1).lower()
        energy = max(0.08, min(0.98, energy))

        tonic, mode = parse_key(t, clause)
        section_key = key
        if tonic:
            section_key = Key(tonic, mode or ("minor" if key.is_minor else "major"))
        elif "relative major" in t or "relative minor" in t:
            section_key = key.relative
        elif "parallel major" in t or "parallel minor" in t:
            section_key = key.parallel
        elif is_return or "home key" in t or "original key" in t:
            section_key = key

        texture = next((name for name, words in _TEXTURES.items()
                        if any(w in t for w in words)), None)
        if texture is None:
            texture = ("rachmaninoff_wide" if style.name == "rachmaninoff" and
                       energy > 0.82 else "sustained" if energy < 0.27 else
                       style.lh_textures[0] if style.lh_textures else "block_chords")
        marking = next((word for word in _MARKINGS if word in t), "")
        sections.append(SectionPlan(
            label="A" if i == 0 else "A'" if is_return else "Coda" if is_end else chr(65 + i),
            bars=2 if is_end else 4, key=str(section_key), energy=energy, dynamic=dyn,
            texture_lh=texture, texture_rh="melody",
            cadence="perfect_authentic" if is_end or is_return else "half",
            motif_op=operation, harmonic_rhythm="fast" if energy > 0.82 else "moderate",
            role=role, text=marking,
        ))
    _weight_bars(sections, target)
    return sections
