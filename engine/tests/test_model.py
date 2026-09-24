"""Tokenizer round-trips and graceful degradation without torch."""
import pytest

from motif.agent.prompt_parser import parse_prompt
from motif.compose.composer import compose
from motif.engrave.musicxml import to_musicxml
from motif.model.runtime import ModelUnavailable, NeuralComposer, load_if_configured
from motif.model.tokenizer import VOCAB, decode_tokens, encode_score
from motif.theory.pitch import Key


def test_vocabulary_is_stable():
    assert len(VOCAB) == len(set(VOCAB.tokens)), "duplicate tokens"
    for special in ("<pad>", "<bos>", "<eos>", "<unk>"):
        assert special in VOCAB.stoi
    assert VOCAB.pad_id == 0


@pytest.mark.parametrize("prompt,style", [
    ("a chopin nocturne in Eb minor", "chopin"),
    ("a bach fugue in D minor", "bach"),
    ("a mozart sonata in G major", "mozart"),
])
def test_encode_decode_round_trip(prompt, style):
    score = compose(parse_prompt(prompt, seed=4))
    tokens = encode_score(score, style)
    ids = VOCAB.encode(tokens)
    assert VOCAB.stoi["<unk>"] not in ids, "the vocabulary must cover real scores"
    assert VOCAB.decode(ids) == tokens

    back = decode_tokens(tokens)
    assert str(back.key) == str(score.key)
    assert back.time == tuple(score.time)
    assert back.measure_count == score.measure_count
    assert back.metadata["style"] == style
    to_musicxml(back)          # a decoded score must still engrave


def test_decoder_survives_malformed_sequences():
    junk = ["<bos>", "STYLE_chopin", "KEY_-6_min", "TS_4_4", "TEMPO_5", "BAR",
            "DUR_12", "VEL_3", "PITCH_60", "POS_999", "PITCH_notanumber",
            "TRACK_9", "PITCH_64", "DUR_8", "VEL_4", "<eos>"]
    score = decode_tokens(junk)
    assert score.measure_count >= 1
    to_musicxml(score)


def test_transposition_augmentation_shifts_key_and_pitch():
    import sys, pathlib
    pytest.importorskip("numpy")      # the training tools need it; the engine does not
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "training"))
    from prepare import transpose_tokens, _shift_fifths

    tokens = ["<bos>", "KEY_0_maj", "BAR", "POS_0", "PITCH_60", "DUR_12", "VEL_4"]
    up = transpose_tokens(tokens, 2)
    assert "PITCH_62" in up and "KEY_2_maj" in up
    assert transpose_tokens(["PITCH_107"], 6) is None, "must reject off-keyboard notes"
    assert -7 <= _shift_fifths(6, 5) <= 7


def test_missing_model_degrades_gracefully():
    assert load_if_configured(None) is None
    assert load_if_configured("/definitely/not/here.pt") is None
    with pytest.raises(ModelUnavailable):
        NeuralComposer("/definitely/not/here.pt")
