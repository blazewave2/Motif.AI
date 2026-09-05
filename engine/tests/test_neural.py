"""Composing with the trained model in charge of the notes.

These run without torch: a stand-in model returns material of the same shape
the real one does, which is what the composition path actually depends on.
What is being checked is that whatever the model hands back becomes a real
score — every bar full, every chord inside one hand, the right number of
bars — and that a model which fails in any way never stops Motif working.
"""
import random

import pytest

from motif.compose.composer import compose
from motif.compose.forms import build_sections
from motif.compose.orchestration import build_instruments
from motif.compose.styles import resolve_style
from motif.plan import CompositionPlan
from motif.score import Note, Part, Score, bar_duration
from motif.theory.pitch import Key, Pitch


def a_plan(bars: int = 16) -> CompositionPlan:
    style = resolve_style("chopin")
    key = Key.parse("C major")
    sections = build_sections("binary", key, style, random.Random(2), bars)
    return CompositionPlan(title="T", style="chopin", key="C major", time=(4, 4),
                           tempo=96, form="binary", ensemble="solo_piano", seed=2,
                           sections=sections,
                           instruments=build_instruments("solo_piano"))


class FakeModel:
    """Stands in for NeuralComposer, returning the same shape of Score."""

    available = True

    def __init__(self, bars: int = 20, chord_span: int = 30, fail: bool = False):
        self.bars, self.chord_span, self.fail = bars, chord_span, fail

    def generate_long(self, *, style, key, time, tempo, bars, seed=None,
                      progress=None, **kw):
        if self.fail:
            raise RuntimeError("model exploded")
        score = Score(key=key, time=time, tempo=tempo)
        part = Part(staves=2, clefs={1: "G", 2: "F"})
        score.add_part(part)
        bar_ticks = bar_duration(time)
        for i in range(self.bars):
            m = part.measure(i + 1)
            # An unreasonably wide chord, which the engine must make playable.
            low = Pitch.parse("C2")
            top = key.spell(low.midi + self.chord_span)
            m.add(Note([low, key.spell(low.midi + 7), top], bar_ticks,
                       voice=5, staff=2))
            # Eighths, so there is something for the engraver to beam.
            for step in range(8):
                pitch = "E5" if step % 2 else "G5"
                m.add(Note([Pitch.parse(pitch)], bar_ticks // 8, voice=1, staff=1))
        return score


class TestNeuralComposition:
    def test_the_model_writes_the_music_when_one_is_loaded(self):
        score = compose(a_plan(), model=FakeModel())
        assert score.metadata.get("generator") == "neural"

    def test_the_score_is_exactly_as_long_as_asked(self):
        plan = a_plan(16)
        score = compose(plan, model=FakeModel(bars=20))
        assert score.measure_count == plan.total_bars

    def test_every_bar_is_complete(self):
        score = compose(a_plan(), model=FakeModel())
        bar_ticks = bar_duration((4, 4))
        for part in score.parts:
            for m in part.measures:
                for voice, notes in m.voices.items():
                    total = sum(n.duration for n in notes if not n.grace)
                    assert total in (0, bar_ticks), \
                        f"bar {m.number} voice {voice} holds {total} of {bar_ticks}"

    def test_model_output_is_made_playable(self):
        """A model has no hands; it will write chords nobody can reach."""
        score = compose(a_plan(), model=FakeModel(chord_span=30))
        reach = max(9, min(14, resolve_style("chopin").hand_span))
        for part in score.parts:
            for m in part.measures:
                for notes in m.voices.values():
                    for n in notes:
                        if len(n.pitches) > 1:
                            span = (max(p.midi for p in n.pitches)
                                    - min(p.midi for p in n.pitches))
                            assert span <= reach, f"{span} semitones in one hand"

    def test_the_page_is_beamed(self):
        score = compose(a_plan(), model=FakeModel())
        assert any(n.beam for part in score.parts for m in part.measures
                   for notes in m.voices.values() for n in notes)


class TestFallback:
    @pytest.mark.parametrize("model", [
        FakeModel(fail=True),                 # raises
        FakeModel(bars=1),                    # returns too little to use
    ])
    def test_a_failing_model_never_stops_motif(self, model):
        score = compose(a_plan(), model=model)
        assert score.measure_count > 0
        assert score.metadata.get("generator") != "neural"

    def test_no_model_at_all_uses_the_symbolic_engine(self):
        score = compose(a_plan(), model=None)
        assert score.measure_count > 0
        assert score.metadata.get("generator") != "neural"
