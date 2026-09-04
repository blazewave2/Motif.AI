"""How Motif describes what it wrote: real variety, never a fixed form."""
from motif.agent import voice
from motif.compose.styles import resolve_style
from motif.plan import CompositionPlan, SectionPlan


def _plan(seed: int) -> CompositionPlan:
    return CompositionPlan(
        title="Test Piece", style="chopin", key="Eb major", time=(4, 4),
        tempo=90, form="nocturne", ensemble="solo_piano", seed=seed,
        sections=[SectionPlan(label="A", bars=16), SectionPlan(label="B", bars=16)])


class TestCreatedMessage:
    def test_is_deterministic_for_the_same_seed(self):
        style = resolve_style("chopin")
        a = voice.created_message(_plan(1), style)
        b = voice.created_message(_plan(1), style)
        assert a == b

    def test_varies_across_seeds(self):
        style = resolve_style("chopin")
        messages = {voice.created_message(_plan(s), style) for s in range(12)}
        # Not every seed needs a unique message, but a single fixed template
        # would collapse this to one entry regardless of seed.
        assert len(messages) > 1

    def test_always_names_the_piece_and_key(self):
        style = resolve_style("chopin")
        msg = voice.created_message(_plan(3), style)
        assert "Test Piece" in msg
        assert "Eb major" in msg


class TestVoiceModelHook:
    def test_a_rewrite_is_used_when_it_returns_text(self):
        class FakeVoice:
            def rewrite(self, plain, context):
                return "Rewritten by the voice model."
        style = resolve_style("chopin")
        msg = voice.created_message(_plan(1), style, FakeVoice())
        assert msg == "Rewritten by the voice model."

    def test_falls_back_to_the_plain_message_on_any_failure(self):
        class BrokenVoice:
            def rewrite(self, plain, context):
                raise RuntimeError("no model loaded")
        style = resolve_style("chopin")
        plain = voice.created_message(_plan(1), style)
        msg = voice.created_message(_plan(1), style, BrokenVoice())
        assert msg == plain

    def test_falls_back_when_the_rewrite_is_empty(self):
        class EmptyVoice:
            def rewrite(self, plain, context):
                return "   "
        style = resolve_style("chopin")
        plain = voice.created_message(_plan(1), style)
        msg = voice.created_message(_plan(1), style, EmptyVoice())
        assert msg == plain


class TestOtherMessages:
    def test_continued_message_names_the_existing_title(self):
        from motif.agent.analysis import ScoreAnalysis
        info = ScoreAnalysis(time=(4, 4), tempo=90, detected_style="chopin",
                             style_is_exact=True, is_empty=False)
        msg = voice.continued_message(_plan(2), "My Nocturne", 16, info)
        assert "My Nocturne" in msg

    def test_developed_message_names_the_existing_title(self):
        msg = voice.developed_message(_plan(4), "My Nocturne")
        assert "My Nocturne" in msg

    def test_harmonized_message_names_the_existing_title(self):
        style = resolve_style("chopin")
        msg = voice.harmonized_message(_plan(5), "My Nocturne", 16, style, "block_chords")
        assert "My Nocturne" in msg
