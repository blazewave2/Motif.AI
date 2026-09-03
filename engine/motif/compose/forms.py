"""Formal templates.

A form supplies the section map: how many bars, in what key, at what intensity,
and what happens to the motif.  This is where long-range shape comes from — a
piece without it wanders no matter how good the bar-to-bar writing is.
"""
from __future__ import annotations

import random

from ..plan import SectionPlan
from ..theory.pitch import Key
from .styles import StyleProfile


def _k(key: Key, shift: int = 0, mode: str | None = None) -> str:
    if shift == 0 and mode is None:
        return str(key)
    k = key.transposed(shift) if shift else key
    if mode:
        k = Key(k.tonic, mode)
    return str(k)


def _dyn(level: float) -> str:
    scale = ["pp", "p", "mp", "mf", "f", "ff", "fff"]
    return scale[max(0, min(len(scale) - 1, int(round(level * (len(scale) - 1)))))]


def _pick_texture(style: StyleProfile, rng: random.Random, energy: float) -> str:
    pool = list(style.lh_textures)
    if not pool:
        return "block_chords"
    heavy = {"octave_bass", "tremolo", "rachmaninoff_wide", "broken_octaves", "scale_run"}
    light = {"sustained", "pedal_point", "waltz", "alberti", "arpeggio", "nocturne"}
    weights = []
    for t in pool:
        w = 1.0
        if t in heavy:
            w *= 0.4 + energy * 2.0
        if t in light:
            w *= 1.6 - energy * 0.9
        weights.append(max(0.05, w))
    return rng.choices(pool, weights=weights, k=1)[0]


# ---------------------------------------------------------------------------
def build_sections(form: str, key: Key, style: StyleProfile, rng: random.Random,
                   target_bars: int = 32) -> list[SectionPlan]:
    fn = FORMS.get(form) or FORMS.get(style.forms[0] if style.forms else "ternary") \
        or FORMS["ternary"]
    secs = fn(key, style, rng, target_bars)
    for s in secs:
        if not s.texture_lh or s.texture_lh == "auto":
            s.texture_lh = _pick_texture(style, rng, s.energy)
        if not s.dynamic:
            s.dynamic = _dyn(s.energy)
        if not s.text and style.rubato_terms and rng.random() < 0.45:
            s.text = rng.choice(style.rubato_terms)
    return secs


def _scale_bars(sections: list[SectionPlan], target: int) -> list[SectionPlan]:
    """Stretch or shrink a template to roughly the requested length."""
    total = sum(s.bars for s in sections) or 1
    factor = target / total
    if 0.85 <= factor <= 1.15:
        return sections
    for s in sections:
        s.bars = max(2, int(round(s.bars * factor / 2)) * 2)
    return sections


def period(key: Key, style: StyleProfile, rng: random.Random, bars: int) -> list[SectionPlan]:
    half = max(4, bars // 2)
    return [
        SectionPlan("a", half, str(key), 0.4, "", "auto", "melody", "half",
                    "state", style.harmonic_rhythm, role="theme"),
        SectionPlan("a'", bars - half, str(key), 0.55, "", "auto", "melody",
                    "perfect_authentic", "develop", style.harmonic_rhythm, role="theme"),
    ]


def binary(key: Key, style: StyleProfile, rng: random.Random, bars: int) -> list[SectionPlan]:
    half = max(4, bars // 2)
    dest = "dominant" if not key.is_minor else "relative"
    other = key.dominant_key() if dest == "dominant" else key.relative
    return _scale_bars([
        SectionPlan("A", half, str(key), 0.45, "", "auto", "melody", "half",
                    "state", role="theme", repeat=True),
        SectionPlan("B", bars - half, str(other), 0.6, "", "auto", "melody",
                    "perfect_authentic", "develop", role="theme", repeat=True),
    ], bars)


def rounded_binary(key: Key, style: StyleProfile, rng: random.Random, bars: int):
    a = max(4, bars // 3)
    b = max(4, bars // 3)
    return _scale_bars([
        SectionPlan("A", a, str(key), 0.45, "", "auto", "melody", "half", "state",
                    role="theme", repeat=True),
        SectionPlan("B", b, _k(key, 0, "major" if key.is_minor else "minor"), 0.65,
                    "", "auto", "melody", "half", "develop", role="development"),
        SectionPlan("A'", bars - a - b, str(key), 0.5, "", "auto", "melody",
                    "perfect_authentic", "recall", role="recap"),
    ], bars)


def ternary(key: Key, style: StyleProfile, rng: random.Random, bars: int):
    a = max(4, round(bars * 0.35 / 2) * 2)
    b = max(4, round(bars * 0.3 / 2) * 2)
    c = max(4, bars - a - b - 2)
    contrast = key.relative if rng.random() < 0.55 else key.subdominant_key()
    return [
        SectionPlan("A", a, str(key), 0.42, "", "auto", "melody", "half",
                    "state", role="theme"),
        SectionPlan("B", b, str(contrast), 0.68, "", "auto", "melody", "half",
                    "develop", role="development", register=1),
        SectionPlan("A'", c, str(key), 0.55, "", "auto", "melody",
                    "perfect_authentic", "recall", role="recap"),
        SectionPlan("coda", 2, str(key), 0.3, "", "sustained", "melody", "plagal",
                    "fragment", role="coda"),
    ]


def nocturne(key: Key, style: StyleProfile, rng: random.Random, bars: int):
    a = max(6, round(bars * 0.3 / 2) * 2)
    b = max(6, round(bars * 0.28 / 2) * 2)
    return [
        SectionPlan("intro", 2, str(key), 0.22, "p", "auto", "chordal", "half",
                    "state", "slow", role="intro"),
        SectionPlan("A", a, str(key), 0.4, "", "nocturne", "melody", "half",
                    "state", role="theme", text="cantabile"),
        SectionPlan("A'", a, str(key), 0.52, "", "nocturne", "melody",
                    "perfect_authentic", "develop", role="theme"),
        SectionPlan("B", b, str(key.relative), 0.78, "", "auto", "melody", "half",
                    "sequence", role="development", register=1),
        SectionPlan("A''", max(6, bars - 2 * a - b - 4), str(key), 0.6, "",
                    "nocturne", "melody", "romantic", "recall", role="recap"),
        SectionPlan("coda", 4, str(key), 0.25, "pp", "arpeggio", "chordal", "plagal",
                    "fragment", role="coda", text="morendo"),
    ]


def sonata(key: Key, style: StyleProfile, rng: random.Random, bars: int):
    second_key = key.relative if key.is_minor else key.dominant_key()
    unit = max(4, bars // 12)
    return [
        SectionPlan("P", unit * 2, str(key), 0.55, "", "auto", "melody", "half",
                    "state", role="theme"),
        SectionPlan("TR", unit, str(key), 0.68, "", "auto", "melody", "half",
                    "sequence", role="transition"),
        SectionPlan("S", unit * 2, str(second_key), 0.45, "", "auto", "melody",
                    "half", "develop", role="theme"),
        SectionPlan("K", unit, str(second_key), 0.7, "", "auto", "melody",
                    "perfect_authentic", "fragment", role="theme"),
        SectionPlan("Dev", unit * 3, str(key.relative if not key.is_minor
                                          else key.subdominant_key()), 0.85, "",
                    "auto", "melody", "half", "sequence", role="development", register=1),
        SectionPlan("P'", unit * 2, str(key), 0.6, "", "auto", "melody", "half",
                    "recall", role="recap"),
        SectionPlan("S'", unit * 2, str(key), 0.55, "", "auto", "melody",
                    "perfect_authentic", "develop", role="recap"),
        SectionPlan("Coda", unit, str(key), 0.75, "", "auto", "chordal",
                    "perfect_authentic", "fragment", role="coda"),
    ]


def rondo(key: Key, style: StyleProfile, rng: random.Random, bars: int):
    unit = max(4, bars // 7)
    return [
        SectionPlan("A", unit, str(key), 0.5, "", "auto", "melody",
                    "perfect_authentic", "state", role="theme"),
        SectionPlan("B", unit, str(key.dominant_key()), 0.6, "", "auto", "melody",
                    "half", "develop", role="theme"),
        SectionPlan("A'", unit, str(key), 0.52, "", "auto", "melody",
                    "perfect_authentic", "recall", role="recap"),
        SectionPlan("C", unit + unit // 2, str(key.subdominant_key() if not key.is_minor
                                               else key.relative), 0.75, "", "auto",
                    "melody", "half", "sequence", role="development", register=1),
        SectionPlan("A''", unit, str(key), 0.6, "", "auto", "melody",
                    "perfect_authentic", "recall", role="recap"),
        SectionPlan("Coda", max(2, bars - unit * 5 - unit // 2), str(key), 0.8, "",
                    "auto", "chordal", "perfect_authentic", "fragment", role="coda"),
    ]


def theme_and_variations(key: Key, style: StyleProfile, rng: random.Random, bars: int):
    theme_len = 8
    n = max(2, min(6, (bars - theme_len) // theme_len))
    secs = [SectionPlan("Theme", theme_len, str(key), 0.35, "p", "auto", "melody",
                        "perfect_authentic", "state", role="theme")]
    ops = ["develop", "sequence", "invert", "fragment", "augment", "develop"]
    for i in range(n):
        energy = 0.4 + (i + 1) / (n + 1) * 0.5
        var_key = str(key.parallel) if i == n - 2 and n > 2 else str(key)
        secs.append(SectionPlan(f"Var {i+1}", theme_len, var_key, energy, "", "auto",
                                "melody", "perfect_authentic", ops[i % len(ops)],
                                role="theme",
                                harmonic_rhythm="fast" if i % 2 else "moderate",
                                register=1 if i % 3 == 2 else 0))
    secs.append(SectionPlan("Coda", max(2, bars - theme_len * (n + 1)), str(key), 0.85,
                            "", "auto", "chordal", "perfect_authentic", "fragment",
                            role="coda"))
    return secs


def prelude(key: Key, style: StyleProfile, rng: random.Random, bars: int):
    a = max(4, round(bars * 0.4 / 2) * 2)
    return [
        SectionPlan("A", a, str(key), 0.4, "", "auto", "figuration", "half",
                    "state", role="theme"),
        SectionPlan("B", max(4, round(bars * 0.35 / 2) * 2),
                    str(key.relative if key.is_minor else key.subdominant_key()),
                    0.72, "", "auto", "figuration", "half", "sequence",
                    role="development"),
        SectionPlan("A'", max(4, bars - a - round(bars * 0.35 / 2) * 2 - 2), str(key),
                    0.62, "", "auto", "figuration", "perfect_authentic", "recall",
                    role="recap"),
        SectionPlan("coda", 2, str(key), 0.35, "", "sustained", "chordal", "plagal",
                    "fragment", role="coda"),
    ]


def invention(key: Key, style: StyleProfile, rng: random.Random, bars: int):
    unit = max(3, bars // 5)
    return [
        SectionPlan("Exposition", unit, str(key), 0.45, "mf", "two_part_invention",
                    "counterpoint", "half", "state", "fast", role="theme"),
        SectionPlan("Episode 1", unit, str(key.dominant_key()), 0.6,
                    "mf", "two_part_invention", "counterpoint", "half", "sequence",
                    "fast", role="development"),
        SectionPlan("Middle", unit, str(key.relative), 0.68, "mf",
                    "two_part_invention", "counterpoint", "half", "invert", "fast",
                    role="development"),
        SectionPlan("Episode 2", unit, str(key.subdominant_key()), 0.6, "mf",
                    "two_part_invention", "counterpoint", "half", "sequence", "fast",
                    role="development"),
        SectionPlan("Return", max(3, bars - unit * 4), str(key), 0.55, "mf",
                    "two_part_invention", "counterpoint", "perfect_authentic",
                    "recall", "fast", role="recap"),
    ]


def fugue(key: Key, style: StyleProfile, rng: random.Random, bars: int):
    unit = max(3, bars // 6)
    return [
        SectionPlan("Subject", unit, str(key), 0.35, "mp", "two_part_invention",
                    "counterpoint", "half", "state", "fast", role="theme"),
        SectionPlan("Answer", unit, str(key.dominant_key()), 0.45, "mf",
                    "two_part_invention", "counterpoint", "half", "state", "fast",
                    role="theme"),
        SectionPlan("Episode", unit, str(key.relative), 0.55, "mf",
                    "two_part_invention", "counterpoint", "half", "sequence", "fast",
                    role="development"),
        SectionPlan("Entry III", unit, str(key.subdominant_key()), 0.65, "mf",
                    "two_part_invention", "counterpoint", "half", "invert", "fast",
                    role="development"),
        SectionPlan("Stretto", unit, str(key), 0.8, "f", "two_part_invention",
                    "counterpoint", "half", "fragment", "fast", role="development"),
        SectionPlan("Coda", max(2, bars - unit * 5), str(key), 0.7, "f", "chorale",
                    "chordal", "perfect_authentic", "recall", role="coda"),
    ]


def waltz(key: Key, style: StyleProfile, rng: random.Random, bars: int):
    unit = max(8, round(bars / 4 / 2) * 2)
    return [
        SectionPlan("intro", 4, str(key), 0.3, "p", "waltz", "chordal", "half",
                    "state", role="intro"),
        SectionPlan("A", unit, str(key), 0.5, "", "waltz", "melody", "half",
                    "state", role="theme"),
        SectionPlan("B", unit, str(key.dominant_key()), 0.65, "", "waltz", "melody",
                    "perfect_authentic", "develop", role="theme"),
        SectionPlan("C", unit, str(key.subdominant_key()), 0.72, "", "waltz",
                    "melody", "half", "sequence", role="development", register=1),
        SectionPlan("A'", max(4, bars - unit * 3 - 8), str(key), 0.6, "", "waltz",
                    "melody", "perfect_authentic", "recall", role="recap"),
        SectionPlan("coda", 4, str(key), 0.85, "f", "waltz", "chordal",
                    "perfect_authentic", "fragment", role="coda"),
    ]


def through_composed(key: Key, style: StyleProfile, rng: random.Random, bars: int):
    n = max(3, min(7, bars // 8))
    secs = []
    keys = [key, key.relative, key.subdominant_key(), key.dominant_key(),
            key.transposed(3), key.parallel]
    for i in range(n):
        e = 0.3 + 0.6 * (i / max(1, n - 1)) if i < n - 1 else 0.4
        secs.append(SectionPlan(chr(65 + i), max(4, bars // n), str(keys[i % len(keys)]),
                                e, "", "auto", "melody", "half" if i < n - 1 else "plagal",
                                "state" if i == 0 else "develop",
                                role="theme" if i == 0 else "development"))
    return secs


def ostinato_form(key: Key, style: StyleProfile, rng: random.Random, bars: int):
    unit = max(4, bars // 5)
    return [
        SectionPlan("intro", unit, str(key), 0.2, "pp", "ostinato", "chordal",
                    "plagal", "state", "slow", role="intro"),
        SectionPlan("A", unit, str(key), 0.4, "p", "ostinato", "melody", "plagal",
                    "state", "slow", role="theme"),
        SectionPlan("B", unit, str(key), 0.65, "mf", "arpeggio", "melody", "plagal",
                    "develop", "slow", role="development", register=1),
        SectionPlan("C", unit, str(key.relative), 0.85, "f", "octave_bass", "chordal",
                    "authentic", "sequence", "moderate", role="development"),
        SectionPlan("A'", max(2, bars - unit * 4), str(key), 0.35, "p", "ostinato",
                    "melody", "plagal", "recall", "slow", role="recap"),
    ]


def concerto_movement(key: Key, style: StyleProfile, rng: random.Random, bars: int):
    """Ritornello-flavoured concerto first movement with real solo/tutti trading."""
    unit = max(4, bars // 14)
    second = key.relative if key.is_minor else key.dominant_key()
    return [
        SectionPlan("Tutti I", unit * 2, str(key), 0.7, "f", "octave_bass", "chordal",
                    "half", "state", role="theme", tutti=True),
        SectionPlan("Solo I", unit * 2, str(key), 0.55, "mf", "rachmaninoff_wide",
                    "melody", "half", "state", role="theme", solo=True),
        SectionPlan("Transition", unit, str(key), 0.72, "f", "broken_octaves",
                    "figuration", "half", "sequence", role="transition", solo=True),
        SectionPlan("Solo II", unit * 2, str(second), 0.5, "mp", "arpeggio", "melody",
                    "half", "develop", role="theme", solo=True),
        SectionPlan("Tutti II", unit, str(second), 0.8, "ff", "octave_bass", "chordal",
                    "perfect_authentic", "fragment", role="transition", tutti=True),
        SectionPlan("Development", unit * 2, str(key.subdominant_key()), 0.88, "f",
                    "tremolo", "figuration", "half", "sequence", role="development",
                    register=1, solo=True),
        SectionPlan("Cadenza", unit, str(key), 0.92, "ff", "scale_run", "figuration",
                    "half", "fragment", role="cadenza", solo=True),
        SectionPlan("Recap", unit * 2, str(key), 0.75, "f", "rachmaninoff_wide",
                    "melody", "romantic", "recall", role="recap", tutti=True),
        SectionPlan("Coda", max(2, bars - unit * 13), str(key), 0.95, "fff",
                    "octave_bass", "chordal", "perfect_authentic", "fragment",
                    role="coda", tutti=True),
    ]


FORMS = {
    "period": period, "binary": binary, "sonata_binary": binary,
    "rounded_binary": rounded_binary, "ternary": ternary, "nocturne": nocturne,
    "sonata": sonata, "rondo": rondo, "theme_and_variations": theme_and_variations,
    "prelude": prelude, "invention": invention, "fugue": fugue, "waltz": waltz,
    "through_composed": through_composed, "ostinato_form": ostinato_form,
    "concerto": concerto_movement, "concerto_movement": concerto_movement,
    "etude": prelude, "etude_tableau": prelude, "mazurka": ternary,
    "ballade": through_composed, "rhapsody": through_composed,
    "intermezzo": ternary, "impromptu": ternary, "arabesque": ternary,
    "reverie": ostinato_form, "gymnopedie": ternary, "lyric_piece": ternary,
    "song_without_words": ternary, "poem": through_composed, "fantasy": through_composed,
    "scherzo": rounded_binary, "minuet": rounded_binary, "chorale": period,
    "ritornello": rondo, "lied": ternary, "pavane": ternary, "elegie": ternary,
    "sonata_form": sonata,
}
