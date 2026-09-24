"""Motif's own composer: complete, valid, reproducible pieces in every style."""
from __future__ import annotations

import random
from fractions import Fraction as F

import pytest

from motif.agent.prompt_parser import parse_prompt
from motif.composer.core import CARE, Composer
from motif.composer.form import detect_genre, genre_family
from motif.composer.harmony import PhraseHarmonySpec, harmony_style, plan_phrase
from motif.composer.melody import (_degree_of, _move_to_key, _scale_steps, _transpose_steps,
                                   invent_motif, melody_style, motif_score, roles_for)
from motif.control import Cancelled
from motif.notation import parse
from motif.notation.validate import validate
from motif.theory.pitch import Key


def _compose(prompt: str, seed: int = 1, quality: str = "sketch"):
    plan = parse_prompt(prompt, seed=seed)
    c = Composer(plan, quality=quality)
    score = c.compose()
    return c, score


def _errors(msn: str) -> list[str]:
    piece = parse(msn)
    assert not piece.issues, piece.issues[:3]
    return [str(i) for i in validate(piece) if i.severity == "error"]


@pytest.mark.parametrize("prompt", [
    "A Rachmaninoff prelude in C sharp minor",
    "A tender Chopin nocturne in E flat major",
    "A Chopin waltz in A minor",
    "A Mozart sonata in C major",
    "A Bach invention in D minor",
    "A Debussy prelude, dreamy",
    "A Liszt etude in F minor, stormy",
    "A Satie gymnopedie",
])
def test_every_style_writes_a_valid_complete_piece(prompt):
    c, score = _compose(prompt)
    assert _errors(c.msn) == []
    assert score.measure_count >= 16
    assert c.summary["bars"] == score.measure_count
    # it ends: a final bar line and a held last chord
    assert "barline=final" in c.msn
    assert "+fermata" in c.msn


def test_the_same_request_and_seed_give_the_same_piece():
    a, _ = _compose("A Rachmaninoff prelude in C sharp minor", seed=7)
    b, _ = _compose("A Rachmaninoff prelude in C sharp minor", seed=7)
    c, _ = _compose("A Rachmaninoff prelude in C sharp minor", seed=8)
    assert a.msn == b.msn
    assert a.msn != c.msn


@pytest.mark.parametrize("prompt", [
    "A romantic song for voice and piano in F major",
    "A string quartet in D minor",
    "An orchestral elegy in C minor",
    "A violin and piano romance in G minor",
    "A cello and piano piece",
    "A piano trio in A minor",
    "A chorale prelude for organ",
    "A harpsichord sonata in the style of Scarlatti",
    "A guitar piece in E minor",
    "An adagio for string orchestra",
])
def test_ensembles_are_scored_for_their_instruments(prompt):
    c, score = _compose(prompt, seed=3)
    assert _errors(c.msn) == []
    assert c.ensemble == parse_prompt(prompt, seed=3).ensemble
    assert len(score.parts) >= 1


def test_the_lead_instrument_stays_in_its_range():
    c, _ = _compose("A romantic song for voice and piano in F major", seed=2)
    piece = parse(c.msn)
    voice = [p for p in piece.parts if p.id == "V"][0]
    lo, hi = voice.instrument.low, voice.instrument.high
    for m in piece.measures:
        for line in m.voices:
            if line.part != "V":
                continue
            for ev in line.events:
                for p in getattr(ev, "pitches", []) or []:
                    assert lo <= p.midi <= hi


def test_care_levels_exist_and_grow():
    order = ["sketch", "balanced", "best", "maximum"]
    for a, b in zip(order, order[1:]):
        assert CARE[a].beam <= CARE[b].beam
        assert CARE[a].melody_takes <= CARE[b].melody_takes


def test_stop_request_interrupts_composing():
    calls = []

    def progress(update):
        calls.append(update)
        if len(calls) > 3:
            raise Cancelled()

    plan = parse_prompt("A Chopin nocturne", seed=1)
    with pytest.raises(Cancelled):
        Composer(plan, quality="sketch", progress=progress).compose()


def test_progress_is_reported_in_order():
    seen = []
    plan = parse_prompt("A Chopin nocturne", seed=1)
    Composer(plan, quality="sketch", progress=seen.append).compose()
    fractions = [u.fraction for u in seen]
    assert fractions == sorted(fractions)
    assert seen[0].stage == "planning"
    assert seen[-1].stage == "finishing"


def test_genre_is_read_from_the_request():
    assert detect_genre("a Liszt consolation") == "consolation"
    assert genre_family("consolation") == "nocturne"
    assert genre_family("waltz") == "waltz"
    assert genre_family("a prelude marked allegro") == "prelude"
    c, _ = _compose("A Tchaikovsky romance in F minor", seed=1)
    assert c.family == "nocturne"


def test_a_named_tempo_and_metre_are_kept():
    plan = parse_prompt("A Chopin nocturne in 12/8 at 60 bpm", seed=1)
    c = Composer(plan, quality="sketch")
    assert c.time == (12, 8)
    assert c.tempo == 60


def test_unnamed_tempo_suits_the_piece():
    plan = parse_prompt("A sad Rachmaninoff prelude", seed=1)
    c = Composer(plan, quality="sketch")
    assert c.tempo <= 80
    assert c.tempo_text


# -- the pieces of the composer ---------------------------------------------------
def test_scale_steps_and_transposition_agree():
    k = Key.parse("A minor")
    assert _scale_steps(64, 69, k) == 3            # E up to A: three steps
    assert _transpose_steps(69, 1, k) == 71        # A -> B
    assert _transpose_steps(72, -2, k) == 69       # C -> A
    # the leading tone is the seventh degree raised
    assert _degree_of(68, k) == (_degree_of(67, k)[0], 1)
    c = Key.parse("C major")
    assert [_transpose_steps(m, 1, c) for m in (60, 64, 71)] == [62, 65, 72]


def test_a_remembered_tune_moves_into_a_new_key_by_degree():
    # E in C major is the third degree: in G major that is B, the nearest one
    moved = _move_to_key(64, Key.parse("C major"), Key.parse("G major"))
    assert moved % 12 == 11 and abs(moved - 64) <= 6
    # C major's E is the third degree; in A minor that is C
    assert _move_to_key(64, Key.parse("C major"), Key.parse("A minor")) % 12 == 0


def test_invented_motifs_have_a_shape():
    rng = random.Random(4)
    for name in ("russian", "romantic", "classical", "baroque"):
        m = invent_motif(melody_style(name), (4, 4), rng, 16)
        assert len(m.steps) == len(m.rhythm) + len(m.second) - 1
        assert max(m.contour) - min(m.contour) >= 2
        assert motif_score(m, melody_style(name)) > 0


def test_sentences_state_repeat_and_break_down_their_idea():
    roles = roles_for("sentence", 8)
    assert roles[:4] == ["idea", "idea2", "repeat", "repeat2"]
    assert roles[-1] == "cadence"
    assert roles_for("consequent", 8)[:2] == ["recall:0", "recall:1"]


def test_a_sentence_answers_its_idea_and_a_consequent_borrows_the_opening():
    key = Key.parse("C minor")
    style = harmony_style("russian")
    rng = random.Random(1)
    spec = PhraseHarmonySpec(key=key, start=F(0), bars=8, bar_len=F(4), cadence="HC",
                             presentation=True)
    ante = plan_phrase(spec, style, rng, tries=8)
    assert ante[0].roman.startswith("i")
    assert ante[-1].roman.startswith("V")
    first4 = [h for h in ante if h.onset < 16]
    cons_spec = PhraseHarmonySpec(key=key, start=F(32), bars=8, bar_len=F(4), cadence="PAC",
                                  prefix=[type(h)(h.roman, h.key, h.onset + 32, h.dur)
                                          for h in first4], prefix_bars=4)
    cons = plan_phrase(cons_spec, style, rng, tries=8)
    assert [h.roman for h in cons[:len(first4)]][:2] == [h.roman for h in first4][:2]
    assert cons[-1].roman.startswith("i")
    assert sum(h.dur for h in cons) == 32


def test_the_learned_melody_model_ships_and_is_used():
    from motif.composer.style_model import melody_model
    model = melody_model()
    assert model is not None and model.songs > 1000
    # after a rising leap a melody usually falls back by step
    assert model.interval_cost(7, -2) < model.interval_cost(7, 5)
    # the leading tone rises to the tonic
    assert model.degree_cost(False, 11, 0) < model.degree_cost(False, 11, 6)


def test_returns_can_be_ornamented_with_runs_that_are_written_as_tuplets():
    c, _ = _compose("A tender Chopin nocturne in E flat major", seed=2, quality="balanced")
    assert _errors(c.msn) == []
    assert "{6 " in c.msn or "{3 " in c.msn or "{a" in c.msn or "turn" in c.msn


def test_every_chord_in_every_style_is_spelled_sensibly():
    from motif.composer.harmony import HARMONY_STYLES, chord_for
    for style in HARMONY_STYLES.values():
        for mode, key in (("major", Key.parse("C major")), ("minor", Key.parse("C minor")),
                          ("minor", Key.parse("A minor"))):
            pools = [style.tonic[mode], style.predominant[mode], style.dominant[mode],
                     style.response.get(mode, [])]
            pools += [c[mode] for c in style.cadence.values()]
            for pool in pools:
                for _w, pattern in pool:
                    for label in pattern:
                        chord = chord_for(label, key)
                        for p in chord.pitches(4, key):
                            assert abs(p.alter) <= 1, (style.name, mode, label, str(p))


def test_a_piano_concerto_passes_the_music_between_soloist_and_orchestra():
    c, score = _compose("Make a full Rachmaninoff style piano concerto using a dark E flat "
                        "minor melody", seed=1)
    assert _errors(c.msn) == []
    assert c.ensemble == "piano_concerto"
    forces = {s["forces"] for s in c.summary["sections"]}
    assert {"solo", "orch_lead", "tutti", "cadenza"} <= forces
    piece = parse(c.msn)
    ids = [p.id for p in piece.parts]
    assert "Pno" in ids and "Vn1" in ids and "Timp" in ids


def test_a_musicians_melody_is_harmonised_and_kept_exactly():
    from motif.agent.agent import MotifAgent, Request
    from motif.engrave.musicxml import to_musicxml
    from motif.engrave.musicxml_reader import read_musicxml
    from motif.notation.to_score import to_score
    msn = ("title: My Tune\nkey: D major\ntime: 4/4\ntempo: 96\npart: Pno piano\n\n"
           + "".join(f"m{i + 1}\n  RH: {bar}\n  LH: R\n" for i, bar in enumerate([
               "F#4:q F#4:q G4:q A4:q", "A4:q G4:q F#4:q E4:q", "D4:q D4:q E4:q F#4:q",
               "F#4:q. E4:e E4:h", "F#4:q F#4:q G4:q A4:q", "A4:q G4:q F#4:q E4:q",
               "D4:q D4:q E4:q F#4:q", "E4:q. D4:e D4:h"])))
    score, _ = to_score(parse(msn))
    result = MotifAgent(options={"quality": "sketch"}).run(
        Request(prompt="Add a left hand accompaniment", score_xml=to_musicxml(score), seed=3))
    assert result.ok and result.intent == "harmonize", result.error
    out = read_musicxml(result.musicxml)
    tune_in = [(n.pitches[0].midi, n.duration) for m in score.parts[0].measures
               for n in m.voices.get(1, []) if n.pitches]
    tune_out = [(n.pitches[0].midi, n.duration) for m in out.parts[0].measures
                for n in m.voices.get(1, []) if n.pitches and n.staff == 1]
    assert tune_out == tune_in
    lh = [n for m in out.parts[0].measures for v in m.voices.values() for n in v
          if n.pitches and n.staff == 2]
    assert len(lh) >= 16


def test_an_open_piece_can_be_arranged_for_other_forces():
    from motif.agent.agent import MotifAgent, Request
    from motif.engrave.musicxml_reader import read_musicxml
    agent = MotifAgent(options={"quality": "sketch"})
    src = agent.run(Request(prompt="A Chopin nocturne in E flat major, 16 bars", seed=4))
    out = agent.run(Request(prompt="Arrange the piece I have open for string quartet, keeping "
                                   "the melody in the first violin", score_xml=src.musicxml,
                            seed=5))
    assert out.ok and out.intent == "arrange", out.error
    score = read_musicxml(out.musicxml)
    assert [p.name for p in score.parts] == ["Violin I", "Violin II", "Viola", "Violoncello"]
    original = read_musicxml(src.musicxml)
    assert score.measure_count == original.measure_count
