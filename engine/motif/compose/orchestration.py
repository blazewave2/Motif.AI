"""Ensemble writing: hand the same musical material to different instruments.

Roles come from the instrument plan.  A concerto alternates solo and tutti, so
each section says which forces play; everything else rests, properly notated.
"""
from __future__ import annotations

from dataclasses import replace

from ..engrave.layout import place_voice
from ..plan import SectionPlan
from ..score import EIGHTH, HALF, Note, Part, QUARTER, Score
from ..theory.pitch import Key, Pitch
from .harmony_timeline import HarmonyTimeline
from .textures import TextureContext, render_texture
from .voicing import spell_in_chord

#: General MIDI programs and practical ranges for the instruments we score for.
INSTRUMENTS: dict[str, dict] = {
    "piano": dict(program=0, low=21, high=108, staves=2, clefs=["G", "F"],
                  abbrev="Pno.", role="solo"),
    "violin_i": dict(program=40, low=55, high=100, staves=1, clefs=["G"],
                     abbrev="Vln. I", role="melody", name="Violin I"),
    "violin_ii": dict(program=40, low=55, high=93, staves=1, clefs=["G"],
                      abbrev="Vln. II", role="harmony", name="Violin II"),
    "viola": dict(program=41, low=48, high=84, staves=1, clefs=["C"],
                  abbrev="Vla.", role="inner", name="Viola"),
    "cello": dict(program=42, low=36, high=76, staves=1, clefs=["F"],
                  abbrev="Vc.", role="bass", name="Violoncello"),
    "contrabass": dict(program=43, low=28, high=60, staves=1, clefs=["F"],
                       abbrev="Cb.", role="bass", name="Contrabass"),
    "flute": dict(program=73, low=60, high=96, staves=1, clefs=["G"],
                  abbrev="Fl.", role="melody", name="Flute"),
    "oboe": dict(program=68, low=58, high=91, staves=1, clefs=["G"],
                 abbrev="Ob.", role="melody", name="Oboe"),
    "clarinet": dict(program=71, low=50, high=91, staves=1, clefs=["G"],
                     abbrev="Cl.", role="harmony", name="Clarinet"),
    "bassoon": dict(program=70, low=34, high=72, staves=1, clefs=["F"],
                    abbrev="Bsn.", role="bass", name="Bassoon"),
    "horn": dict(program=60, low=41, high=77, staves=1, clefs=["G"],
                 abbrev="Hn.", role="harmony", name="Horn in F"),
    "trumpet": dict(program=56, low=55, high=82, staves=1, clefs=["G"],
                    abbrev="Tpt.", role="melody", name="Trumpet"),
    "trombone": dict(program=57, low=40, high=72, staves=1, clefs=["F"],
                     abbrev="Tbn.", role="bass", name="Trombone"),
    "timpani": dict(program=47, low=36, high=57, staves=1, clefs=["F"],
                    abbrev="Timp.", role="bass", name="Timpani"),
    "harp": dict(program=46, low=24, high=103, staves=2, clefs=["G", "F"],
                 abbrev="Hp.", role="harmony", name="Harp"),
    "strings": dict(program=48, low=36, high=96, staves=2, clefs=["G", "F"],
                    abbrev="Str.", role="harmony", name="Strings"),
    "voice": dict(program=52, low=55, high=81, staves=1, clefs=["G"],
                  abbrev="Vo.", role="melody", name="Voice"),
    "organ": dict(program=19, low=24, high=96, staves=2, clefs=["G", "F"],
                  abbrev="Org.", role="solo", name="Organ"),
    "harpsichord": dict(program=6, low=29, high=89, staves=2, clefs=["G", "F"],
                        abbrev="Hpschd.", role="solo", name="Harpsichord"),
    "guitar": dict(program=24, low=40, high=84, staves=1, clefs=["G8vb"],
                   abbrev="Gtr.", role="solo", name="Guitar"),
}

#: Named ensembles the planner can request.
ENSEMBLES: dict[str, list[str]] = {
    "solo_piano": ["piano"],
    "piano_concerto": ["piano", "flute", "oboe", "clarinet", "horn",
                       "violin_i", "violin_ii", "viola", "cello", "contrabass"],
    "string_quartet": ["violin_i", "violin_ii", "viola", "cello"],
    "string_orchestra": ["violin_i", "violin_ii", "viola", "cello", "contrabass"],
    "piano_trio": ["piano", "violin_i", "cello"],
    "orchestra": ["flute", "oboe", "clarinet", "bassoon", "horn", "trumpet",
                  "timpani", "violin_i", "violin_ii", "viola", "cello", "contrabass"],
    "chamber": ["flute", "clarinet", "violin_i", "cello", "piano"],
    "violin_piano": ["violin_i", "piano"],
    "cello_piano": ["cello", "piano"],
    "voice_piano": ["voice", "piano"],
    "organ": ["organ"],
    "harpsichord": ["harpsichord"],
    "guitar": ["guitar"],
}


def orchestrate(composer, score: Score, parts: list[Part], sec: SectionPlan,
                key: Key, timeline: HarmonyTimeline, melody: list[Note],
                start_tick: int, bar_ticks: int, beat_ticks: int) -> None:
    """Distribute a section's material across the ensemble."""
    plans = composer.plan.instruments
    solo_only = sec.solo and any(p.role == "solo" for p in plans)

    for part, ip in zip(parts, plans):
        spec = INSTRUMENTS.get(_lookup_key(ip.name), {})
        low = ip.range_low or spec.get("low", 36)
        high = ip.range_high or spec.get("high", 84)
        role = ip.role or spec.get("role", "harmony")

        if solo_only and role != "solo":
            _rest(part, start_tick, timeline.duration, composer.bar_ticks,
                  beat_ticks, part.staves)
            continue
        if sec.tutti is False and sec.solo is False:
            pass  # every section plays unless it is explicitly marked

        if role == "solo" and part.staves > 1:
            composer._write_piano(part, sec, key, timeline, melody, start_tick,
                                  bar_ticks, beat_ticks)
        elif role == "melody":
            line = _fit_range(melody, low, high, key)
            place_voice(part, line, start_tick=start_tick,
                        bar_ticks=composer.bar_ticks, beat_ticks=beat_ticks,
                        voice=1, staff=1)
        elif role == "bass":
            ctx = _ctx(composer, timeline, key, sec, bar_ticks, beat_ticks,
                       low, min(high, low + 30), staff=1, voice=1)
            name = "octave_bass" if sec.energy > 0.6 else "walking_bass" \
                if composer.style.era == "baroque" else "sustained"
            place_voice(part, render_texture(name, ctx), start_tick=start_tick,
                        bar_ticks=composer.bar_ticks, beat_ticks=beat_ticks,
                        voice=1, staff=1)
        elif role == "inner":
            ctx = _ctx(composer, timeline, key, sec, bar_ticks, beat_ticks,
                       low, high, staff=1, voice=1)
            name = "repeated_chords" if sec.energy > 0.65 else "sustained"
            place_voice(part, render_texture(name, ctx), start_tick=start_tick,
                        bar_ticks=composer.bar_ticks, beat_ticks=beat_ticks,
                        voice=1, staff=1)
        elif role == "doubling":
            line = _fit_range(melody, low, high, key, octave_bias=-1)
            place_voice(part, line, start_tick=start_tick,
                        bar_ticks=composer.bar_ticks, beat_ticks=beat_ticks,
                        voice=1, staff=1)
        else:  # harmony
            ctx = _ctx(composer, timeline, key, sec, bar_ticks, beat_ticks,
                       low, high, staff=1, voice=1)
            name = "tremolo" if sec.energy > 0.82 else "sustained"
            place_voice(part, render_texture(name, ctx), start_tick=start_tick,
                        bar_ticks=composer.bar_ticks, beat_ticks=beat_ticks,
                        voice=1, staff=1)


def _ctx(composer, timeline, key, sec, bar_ticks, beat_ticks, low, high,
         staff, voice) -> TextureContext:
    from .composer import _dyn_level
    return TextureContext(timeline, key, composer.rng, bar_ticks=bar_ticks,
                          beat_ticks=beat_ticks, low=low, high=high, staff=staff,
                          voice=voice, density=0.35 + sec.energy * 0.4,
                          style=composer.style.name,
                          dynamic=_dyn_level(sec.dynamic), hand_span=24)


def _rest(part: Part, start_tick: int, duration: int, bar_ticks: int,
          beat_ticks: int, staves: int) -> None:
    place_voice(part, [Note([], duration)], start_tick=start_tick,
                bar_ticks=bar_ticks, beat_ticks=beat_ticks, voice=1, staff=1)
    if staves > 1:
        place_voice(part, [Note([], duration)], start_tick=start_tick,
                    bar_ticks=bar_ticks, beat_ticks=beat_ticks, voice=5, staff=2)


def _fit_range(melody: list[Note], low: int, high: int, key: Key,
               octave_bias: int = 0) -> list[Note]:
    """Transpose a line by octaves until it sits inside an instrument's range."""
    pitched = [n for n in melody if n.pitches and not n.grace]
    if not pitched:
        return [n.copy() for n in melody]
    lo = min(p.midi for n in pitched for p in n.pitches)
    hi = max(p.midi for n in pitched for p in n.pitches)
    shift = octave_bias * 12
    while lo + shift < low:
        shift += 12
    while hi + shift > high:
        shift -= 12
    if lo + shift < low:            # range too narrow for the line: clamp instead
        shift = low - lo
    out: list[Note] = []
    for n in melody:
        nn = n.copy()
        nn.pitches = [key.spell(max(low, min(high, p.midi + shift))) for p in n.pitches]
        out.append(nn)
    return out


def _lookup_key(name: str) -> str:
    n = name.lower().replace(" ", "_").replace(".", "")
    aliases = {"violin": "violin_i", "violin_1": "violin_i", "violin_2": "violin_ii",
               "violoncello": "cello", "double_bass": "contrabass",
               "string_bass": "contrabass", "horn_in_f": "horn", "french_horn": "horn"}
    return aliases.get(n, n)


def build_instruments(ensemble: str) -> list:
    """Instrument plans for a named ensemble."""
    from ..plan import InstrumentPlan
    names = ENSEMBLES.get(ensemble, ENSEMBLES["solo_piano"])
    out = []
    for n in names:
        spec = INSTRUMENTS.get(n, INSTRUMENTS["piano"])
        out.append(InstrumentPlan(
            name=spec.get("name", n.replace("_", " ").title()),
            abbreviation=spec.get("abbrev", n[:4].title()),
            midi_program=spec["program"], staves=spec["staves"],
            clefs=list(spec["clefs"]), role=spec["role"],
            range_low=spec["low"], range_high=spec["high"]))
    return out
