"""The words of a musical request must affect the engraved result."""
from motif.agent.agent import MotifAgent, Request
from motif.agent.prompt_parser import parse_prompt
from motif.engrave.musicxml_reader import read_musicxml


def test_narrated_arc_controls_sections_and_engraved_score():
    prompt = ("Write a 24 bar Rachmaninoff prelude in C minor at 92 bpm: "
              "begin with a quiet cantabile melody and flowing left hand, "
              "then grow into a thunderous climax with bass octaves, "
              "finally return to the opening theme and fade away")
    plan = parse_prompt(prompt, seed=10)
    assert plan.style == "rachmaninoff"
    assert plan.tempo == 92 and plan.total_bars == 24
    assert [s.motif_op for s in plan.sections] == ["state", "develop", "recall"]
    assert [s.texture_lh for s in plan.sections] == ["nocturne", "octave_bass", "sustained"]
    assert plan.sections[1].energy > plan.sections[0].energy > plan.sections[2].energy

    result = MotifAgent().run(Request(prompt=prompt, seed=10))
    assert result.ok, result.error
    score = read_musicxml(result.musicxml)
    assert score.measure_count == 24
    assert str(score.key) == "C minor"


def test_sections_can_change_key_and_remain_reproducible():
    prompt = ("16 bars of Chopin in A minor: begin gently, then move to "
              "the relative major with arpeggios, finally return to A minor")
    first = parse_prompt(prompt, seed=9)
    second = parse_prompt(prompt, seed=9)
    assert first.to_json() == second.to_json()
    assert first.total_bars == 16
    assert [s.key for s in first.sections] == ["A minor", "C major", "A minor"]
    assert first.sections[1].texture_lh == "arpeggio"


def test_explicit_bpm_overrides_mood_and_form_has_exact_length():
    plan = parse_prompt("a dark 17 bar Chopin nocturne at 104 bpm", seed=8)
    assert plan.tempo == 104
    assert plan.total_bars == 17


def test_optional_planner_cannot_overrule_explicit_brief():
    class OvereagerPlanner:
        def refine(self, prompt, draft):
            from copy import deepcopy
            p = deepcopy(draft)
            p.key, p.tempo, p.time, p.style, p.form = (
                "G major", 200, (3, 4), "bach", "fugue")
            p.sections = p.sections[:1]
            p.sections[0].bars = 4
            return p

    prompt = ("Chopin nocturne in C minor, 12 bars at 88 bpm in 4/4: "
              "begin quietly, then build to a climax, finally return")
    plan = MotifAgent(planner=OvereagerPlanner())._plan_for(Request(prompt=prompt, seed=3))
    assert (plan.key, plan.tempo, plan.time, plan.style, plan.form) == (
        "C minor", 88, (4, 4), "chopin", "nocturne")
    assert len(plan.sections) == 3 and plan.total_bars == 12
