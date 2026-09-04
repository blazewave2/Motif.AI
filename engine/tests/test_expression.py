"""The performance layer: does the music breathe?

These assert the properties that separate a performance from a printout, and
would catch a regression that made playback metronomic again.
"""
import random

import pytest

from motif.agent.prompt_parser import parse_prompt
from motif.compose.composer import compose
from motif.compose.expression import (ExpressionPlanner, RUBATO, detect_phrases,
                                      shift_dynamic)
from motif.compose.styles import resolve_style
from motif.plan import SectionPlan
from motif.score import Note, QUARTER, WHOLE
from motif.theory.pitch import Pitch


def all_notes(score, voice=None):
    return [n for p in score.parts for m in p.measures
            for v, ns in m.voices.items() if voice is None or v == voice
            for n in ns if n.pitches]


SECTIONS = [SectionPlan("A", 8, "Eb minor", 0.4, role="theme"),
            SectionPlan("B", 8, "Gb major", 0.85, role="development"),
            SectionPlan("A'", 8, "Eb minor", 0.6, role="recap"),
            SectionPlan("coda", 4, "Eb minor", 0.3, role="coda")]


class TestTempo:
    @pytest.mark.parametrize("style_id", ["chopin", "rachmaninoff", "liszt", "brahms"])
    def test_freely_played_styles_breathe(self, style_id):
        ep = ExpressionPlanner(random.Random(3), resolve_style(style_id), 88.0)
        marks = ep.tempo_marks(SECTIONS, [0, 8, 16, 24], WHOLE)
        assert len(marks) >= 5, "a Romantic piece should not run at one tempo"
        assert any(m.text for m in marks), "tempo changes need words on the page"
        assert len({m.bpm for m in marks}) > 2

    def test_baroque_holds_its_pulse(self):
        ep = ExpressionPlanner(random.Random(3), resolve_style("bach"), 96.0)
        marks = ep.tempo_marks(SECTIONS, [0, 8, 16, 24], WHOLE)
        assert 1 <= len(marks) <= 3, "Bach should not be full of rubato"
        assert marks[0].measure == 1, "the opening tempo is always stated"

    def test_every_style_states_an_opening_tempo(self):
        from motif.compose.styles import STYLES
        for name in STYLES:
            ep = ExpressionPlanner(random.Random(1), resolve_style(name), 100.0)
            marks = ep.tempo_marks(SECTIONS, [0, 8, 16, 24], WHOLE)
            assert marks and marks[0].measure == 1, f"{name} has no opening tempo"

    def test_marks_are_ordered_and_unique_per_bar(self):
        ep = ExpressionPlanner(random.Random(7), resolve_style("chopin"), 80.0)
        marks = ep.tempo_marks(SECTIONS, [0, 8, 16, 24], WHOLE)
        bars = [m.measure for m in marks]
        assert bars == sorted(bars)
        assert len(bars) == len(set(bars))
        assert all(20 <= m.bpm <= 260 for m in marks)


class TestPhrases:
    def test_phrases_are_period_length_not_slur_length(self):
        # Eight bars of quarter notes, slurred every two beats.
        notes = []
        for i in range(32):
            n = Note([Pitch.parse("C5")], QUARTER)
            if i % 2 == 0:
                n.slur_start = 1
            else:
                n.slur_stop = 1
            notes.append(n)
        phrases = detect_phrases(notes, 0, WHOLE, 8, 0.5)
        assert phrases, "a line with slurs must still yield phrases"
        for ph in phrases:
            assert ph.length >= WHOLE * 2, "phrases should span bars, not beats"

    def test_unslurred_music_still_phrases(self):
        notes = [Note([Pitch.parse("C5")], QUARTER) for _ in range(32)]
        phrases = detect_phrases(notes, 0, WHOLE, 8, 0.5)
        assert len(phrases) >= 2
        assert phrases[-1].cadential


class TestDynamics:
    @pytest.mark.parametrize("prompt", [
        "a chopin nocturne in Eb minor",
        "a rachmaninoff prelude",
        "a mozart sonata in G",
        "a bach fugue in D minor",
    ])
    def test_velocities_are_continuous(self, prompt):
        score = compose(parse_prompt(prompt, seed=5))
        vels = [n.velocity for n in all_notes(score)]
        assert len(set(vels)) >= 25, "playback would sound stepped, not shaped"
        assert min(vels) >= 1 and max(vels) <= 127
        assert max(vels) - min(vels) >= 25, "no dynamic range"

    def test_melody_sits_above_the_accompaniment(self):
        score = compose(parse_prompt("a chopin nocturne in Eb minor", seed=5))
        melody = [n.velocity for n in all_notes(score, voice=1)]
        accomp = [n.velocity for n in all_notes(score, voice=5)]
        assert melody and accomp
        assert sum(melody) / len(melody) > sum(accomp) / len(accomp) + 4, \
            "the hands are not balanced"

    def test_shift_dynamic_clamps(self):
        assert shift_dynamic("fff", 3) == "fff"
        assert shift_dynamic("ppp", -3) == "ppp"
        assert shift_dynamic("mf", 1) == "f"
        assert shift_dynamic("nonsense", 0) == "mf"


class TestRhythmicLife:
    @pytest.mark.parametrize("prompt", [
        "a rachmaninoff prelude", "a chopin nocturne in Eb minor",
        "a liszt etude", "a tchaikovsky waltz",
    ])
    def test_no_single_bar_rhythm_dominates(self, prompt):
        import collections
        score = compose(parse_prompt(prompt, seed=5))
        part = score.parts[0]
        bars = [tuple(n.duration for n in m.voices[1] if not n.grace)
                for m in part.measures if 1 in m.voices]
        assert bars
        commonest = collections.Counter(bars).most_common(1)[0][1]
        assert commonest <= len(bars) * 0.55, \
            f"one bar rhythm covers {commonest}/{len(bars)} bars"
        assert len(set(bars)) >= max(3, len(bars) // 8)

    def test_tuplets_are_notated_not_approximated(self):
        score = compose(parse_prompt("a rachmaninoff prelude", seed=5))
        tuplets = [n for n in all_notes(score) if n.tuplet]
        assert tuplets, "no tuplets anywhere"
        for n in tuplets:
            assert n.tuplet.actual > n.tuplet.normal > 0
            # A tuplet member must never be shattered into unnotatable pieces.
            assert n.duration >= 40, f"tuplet note of {n.duration} ticks"
