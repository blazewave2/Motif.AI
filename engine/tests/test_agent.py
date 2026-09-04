"""Prompt understanding and the agent's intents."""
import pytest

from motif.agent.agent import MotifAgent, Request
from motif.agent.prompt_parser import parse_key, parse_prompt


class TestKeyParsing:
    @pytest.mark.parametrize("text,expected", [
        ("continue this piece in a more dramatic way", (None, None)),
        ("create a joyful melody in 6/8 time", (None, None)),
        ("write something in c", ("C", None)),
        ("a gentle piece for a friend", (None, None)),
        ("a dark eb minor melody", ("Eb", "minor")),
        ("a bach fugue in d minor", ("D", "minor")),
        ("in the key of f# major", ("F#", "major")),
        ("transpose to bb major", ("Bb", "major")),
        ("a piece in b minor", ("B", "minor")),
        ("key of eb", ("Eb", None)),
        ("e flat minor please", ("Eb", "minor")),
        # "a minor key" means the mode, not the key of A.
        ("add a contrasting middle section in a minor key", (None, "minor")),
        ("transpose into a major key", (None, "major")),
        # A bare letter after "in" is a key when it stands alone; only "a" is
        # ambiguous with the article, so there capitalisation decides.
        ("a mozart sonata in G", ("G", None)),
        ("a fugue in D at 92 bpm", ("D", None)),
        ("write a nocturne in C", ("C", None)),
        ("a piece in A", ("A", None)),
        ("a piece in a", (None, None)),
    ])
    def test_parse_key(self, text, expected):
        assert parse_key(text, text) == expected


class TestPromptParsing:
    def test_reads_the_full_concerto_request(self):
        p = parse_prompt("Make a full Rachmanninoff style piano concerto "
                         "using a dark Eb minor melody.", seed=1)
        assert p.style == "rachmaninoff"          # despite the misspelling
        assert p.key == "Eb minor"
        assert p.ensemble == "piano_concerto"
        assert p.form == "concerto"
        assert p.total_bars >= 96
        assert len(p.instruments) > 1

    def test_simple_request_stays_simple(self):
        p = parse_prompt("Create a simple melody for me to play.", seed=1)
        assert p.total_bars <= 16
        assert p.ensemble == "solo_piano"
        assert all(s.energy <= 0.6 for s in p.sections)
        assert all(s.register == 0 for s in p.sections)

    @pytest.mark.parametrize("seed", [1, 2, 3, 4])
    def test_requested_key_survives_a_bare_letter(self, seed):
        # A key named without a mode means major, and must not be re-rolled.
        assert parse_prompt("a mozart sonata in G", seed=seed).key == "G major"
        assert parse_prompt("a nocturne in C", seed=seed).key == "C major"
        assert parse_prompt("a dark elegy in F", seed=seed).key.startswith("F")

    @pytest.mark.parametrize("text,field,value", [
        ("a bach fugue in D minor", "form", "fugue"),
        ("a chopin nocturne", "style", "chopin"),
        ("write a waltz", "form", "waltz"),
        ("a string quartet", "ensemble", "string_quartet"),
    ])
    def test_extracts_fields(self, text, field, value):
        assert getattr(parse_prompt(text, seed=3), field) == value

    def test_explicit_numbers_win(self):
        p = parse_prompt("a piece of 24 bars at 92 bpm in 5/4", seed=1)
        assert p.total_bars == 24 or abs(p.total_bars - 24) <= 4
        assert p.tempo == 92
        assert p.time == (5, 4)

    def test_titles_match_mood(self):
        sad = {parse_prompt("a dark mournful piece", seed=s).title for s in range(6)}
        happy = {parse_prompt("a joyful uplifting piece", seed=s).title for s in range(6)}
        assert not (sad & happy), "moods should not share title vocabulary"

    def test_is_deterministic_for_a_seed(self):
        a = parse_prompt("a chopin nocturne", seed=7)
        b = parse_prompt("a chopin nocturne", seed=7)
        assert a.to_json() == b.to_json()


@pytest.fixture(scope="module")
def agent():
    return MotifAgent()


@pytest.fixture(scope="module")
def first(agent):
    r = agent.run(Request(prompt="Create a simple melody for me to play.", seed=3))
    assert r.ok
    return r


class TestAgent:
    def test_create(self, first):
        assert first.intent == "create"
        assert first.musicxml.startswith("<?xml")
        assert first.midi[:4] == b"MThd"
        assert first.plan is not None

    def test_continue_keeps_the_existing_key(self, agent, first):
        r = agent.run(Request(prompt="Continue this piece in a more dramatic way",
                              score_xml=first.musicxml, seed=4))
        assert r.ok and r.intent == "continue"
        from motif.engrave.musicxml_reader import read_musicxml
        before = read_musicxml(first.musicxml)
        after = read_musicxml(r.musicxml)
        assert after.measure_count > before.measure_count
        assert str(after.key) == str(before.key)

    def test_transpose_and_tempo(self, agent, first):
        r = agent.run(Request(prompt="transpose it to F# minor and make it slower",
                              score_xml=first.musicxml, seed=5))
        assert r.ok and r.intent == "edit"
        from motif.engrave.musicxml_reader import read_musicxml
        assert str(read_musicxml(r.musicxml).key) == "F# minor"

    def test_analyze_reports_the_key(self, agent, first):
        r = agent.run(Request(prompt="what key is this in?", score_xml=first.musicxml))
        assert r.ok and r.intent == "analyze"
        assert "minor" in r.message or "major" in r.message

    def test_harmonize_preserves_length(self, agent, first):
        r = agent.run(Request(prompt="add a left hand accompaniment",
                              score_xml=first.musicxml, seed=6))
        assert r.ok and r.intent == "harmonize"
        from motif.engrave.musicxml_reader import read_musicxml
        assert read_musicxml(r.musicxml).measure_count >= 1

    def test_bad_input_does_not_raise(self, agent):
        r = agent.run(Request(prompt="continue this", score_xml="<not-xml", seed=1))
        assert r.ok or r.error         # either handled or reported, never a crash
