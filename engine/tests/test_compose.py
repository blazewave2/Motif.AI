"""End-to-end composition: every style and form must produce a valid score.

These are the tests that would catch a regression a musician would actually
notice — a bar that does not add up, a note off the keyboard, a piece that
comes out in the wrong key.
"""
import random
import xml.dom.minidom as minidom
from xml.etree import ElementTree as ET

import pytest

from motif.agent.prompt_parser import parse_prompt
from motif.compose.composer import compose
from motif.compose.forms import FORMS, build_sections
from motif.compose.harmony_timeline import HarmonyTimeline
from motif.compose.orchestration import ENSEMBLES, build_instruments
from motif.compose.styles import STYLES, resolve_style
from motif.compose.textures import TEXTURES, TextureContext, render_texture
from motif.engrave.musicxml import to_musicxml
from motif.plan import CompositionPlan, InstrumentPlan
from motif.score import QUARTER, WHOLE, bar_duration, beat_duration
from motif.theory.harmony import progression
from motif.theory.pitch import Key


def bars_are_complete(score) -> list[str]:
    """Every voice in every bar must fill exactly one bar."""
    problems = []
    time = tuple(score.time)
    for part in score.parts:
        expected = bar_duration(time)
        for m in part.measures:
            if m.time:
                expected = bar_duration(tuple(m.time))
            for voice, notes in m.voices.items():
                total = sum(n.duration for n in notes if not n.grace)
                if total != expected:
                    problems.append(
                        f"{part.id} bar {m.number} voice {voice}: "
                        f"{total} != {expected}")
    return problems


def pitch_range(score):
    lo, hi = 128, 0
    for part in score.parts:
        for m in part.measures:
            for notes in m.voices.values():
                for n in notes:
                    for p in n.pitches:
                        lo, hi = min(lo, p.midi), max(hi, p.midi)
    return lo, hi


STYLE_IDS = sorted(STYLES)
FORM_IDS = sorted(set(FORMS))


@pytest.mark.parametrize("style_id", STYLE_IDS)
def test_every_style_composes(style_id):
    style = resolve_style(style_id)
    key = Key("Eb", "minor")
    rng = random.Random(5)
    sections = build_sections(style.forms[0], key, style, rng, 24)
    plan = CompositionPlan(title="T", style=style_id, key=str(key),
                           time=style.meters[0], tempo=88, form=style.forms[0],
                           sections=sections,
                           instruments=[InstrumentPlan(staves=2, clefs=["G", "F"],
                                                       range_low=21, range_high=108)],
                           seed=5)
    score = compose(plan)
    assert score.measure_count > 0
    assert not bars_are_complete(score)
    lo, hi = pitch_range(score)
    assert 21 <= lo <= hi <= 108, f"{style_id} wrote outside the keyboard"
    minidom.parseString(to_musicxml(score))


@pytest.mark.parametrize("form_id", FORM_IDS)
def test_every_form_composes(form_id):
    style = resolve_style("chopin")
    key = Key("D", "minor")
    sections = build_sections(form_id, key, style, random.Random(3), 24)
    assert sections, f"{form_id} produced no sections"
    plan = CompositionPlan(style="chopin", key=str(key), time=(4, 4), tempo=90,
                           form=form_id, sections=sections,
                           instruments=[InstrumentPlan(staves=2, clefs=["G", "F"])],
                           seed=3)
    score = compose(plan)
    assert not bars_are_complete(score)


@pytest.mark.parametrize("ensemble", sorted(ENSEMBLES))
def test_every_ensemble_composes(ensemble):
    style = resolve_style("rachmaninoff")
    key = Key("C", "minor")
    sections = build_sections("ternary", key, style, random.Random(4), 16)
    plan = CompositionPlan(style="rachmaninoff", key=str(key), time=(4, 4),
                           tempo=84, form="ternary", sections=sections,
                           instruments=build_instruments(ensemble), seed=4,
                           ensemble=ensemble)
    score = compose(plan)
    assert len(score.parts) == len(ENSEMBLES[ensemble])
    assert not bars_are_complete(score)
    # Every part must span the same number of bars or the score will not engrave.
    assert len({len(p.measures) for p in score.parts}) == 1
    for part, ip in zip(score.parts, plan.instruments):
        for m in part.measures:
            for notes in m.voices.values():
                for n in notes:
                    for p in n.pitches:
                        assert ip.range_low <= p.midi <= ip.range_high, \
                            f"{ip.name} cannot play {p}"
        # A bass-register instrument (cello, contrabass, bassoon, trombone)
        # cannot sound three or more notes at once; at most a root-and-octave
        # doubling is idiomatic.
        if ip.role == "bass":
            for m in part.measures:
                for notes in m.voices.values():
                    for n in notes:
                        assert len(n.pitches) <= 2, \
                            f"{ip.name} was written a {len(n.pitches)}-note chord"


@pytest.mark.parametrize("style_id", ["chopin", "rachmaninoff", "mozart", "bach",
                                      "debussy", "liszt", "beethoven"])
def test_keyboard_writing_stays_inside_one_hand(style_id):
    """No chord wider than the hand that has to play it.

    Voicings are built to fill a register, which is right for an orchestra
    and wrong for a keyboard, where one hand takes the whole chord. Left
    unchecked this writes four-note chords spanning two octaves — notes on a
    page that no pianist can play.
    """
    style = resolve_style(style_id)
    key = Key("C", "minor")
    sections = build_sections("ternary", key, style, random.Random(9), 24)
    plan = CompositionPlan(style=style_id, key=str(key), time=(4, 4), tempo=96,
                           form="ternary", sections=sections, seed=9,
                           instruments=build_instruments("solo_piano"),
                           ensemble="solo_piano")
    score = compose(plan)
    reach = max(9, min(14, style.hand_span))
    for part in score.parts:
        for m in part.measures:
            for notes in m.voices.values():
                for n in notes:
                    if len(n.pitches) < 2:
                        continue
                    span = max(p.midi for p in n.pitches) - min(p.midi for p in n.pitches)
                    assert span <= reach, (
                        f"{style_id} bar {m.number}: {len(n.pitches)}-note chord "
                        f"spanning {span} semitones, hand reaches {reach}")
                    assert len(n.pitches) <= 4, (
                        f"{style_id} bar {m.number}: {len(n.pitches)} notes in one hand")


@pytest.mark.parametrize("texture", sorted(TEXTURES))
def test_textures_fill_their_timeline_and_stay_playable(texture):
    key = Key("Eb", "minor")
    tl = HarmonyTimeline(progression(["i", "iv", "V7", "i"], key,
                                     durations=[4, 4, 4, 4]))
    ctx = TextureContext(tl, key, random.Random(5), bar_ticks=WHOLE,
                         beat_ticks=QUARTER, low=28, high=64, hand_span=15)
    notes = render_texture(texture, ctx)
    assert sum(n.duration for n in notes) == tl.duration

    # A hand can only stretch so far at once. A rolled figure may cover three
    # octaves within a bar, so the reach that matters is per attack, not per bar.
    for n in notes:
        if len(n.pitches) > 1:
            reach = max(p.midi for p in n.pitches) - min(p.midi for p in n.pitches)
            assert reach <= 24, f"{texture} asks for a {reach}-semitone stretch at once"
    t, bars = 0, {}
    for n in notes:
        if n.pitches:
            bars.setdefault(t // WHOLE, []).extend(p.midi for p in n.pitches)
        t += n.duration
    for b, pitches in bars.items():
        assert max(pitches) - min(pitches) <= 40, f"{texture} bar {b} roams too far"


PROMPTS = [
    "Create a simple melody for me to play.",
    "Make a full Rachmanninoff style piano concerto using a dark Eb minor melody.",
    "Compose a romantic piano piece in the style of Chopin",
    "Create a joyful and uplifting melody in 6/8 time",
    "Write a short film score for a mysterious forest scene",
    "Add a contrasting middle section in a minor key",
    "a bach fugue in D minor at 92 bpm",
    "a stormy virtuosic liszt etude",
    "a calm minimal piece for piano",
    "a mozart sonata in G major",
]


@pytest.mark.parametrize("prompt", PROMPTS)
def test_shipped_prompts_produce_valid_scores(prompt):
    plan = parse_prompt(prompt, seed=11)
    score = compose(plan)
    assert score.measure_count > 0
    assert not bars_are_complete(score)
    xml = to_musicxml(score)
    root = ET.fromstring(xml)
    assert root.tag == "score-partwise"
    assert len(root.findall("part")) == len(score.parts)


def test_requested_key_is_honoured():
    for text, expected in [("a nocturne in Eb minor", "Eb minor"),
                           ("something in F# major", "F# major"),
                           ("a piece in Bb minor", "Bb minor")]:
        plan = parse_prompt(text, seed=2)
        assert plan.key == expected
        assert compose(plan).key.tonic == expected.split()[0]


def test_seeds_are_reproducible_and_distinct():
    a = to_musicxml(compose(parse_prompt("a chopin nocturne", seed=1)))
    b = to_musicxml(compose(parse_prompt("a chopin nocturne", seed=1)))
    c = to_musicxml(compose(parse_prompt("a chopin nocturne", seed=2)))
    assert a == b, "the same seed must reproduce the same score"
    assert a != c, "different seeds should give different music"
