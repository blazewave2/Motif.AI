"""Voice leading is checked the way a harmony exam would check it."""
import random

import pytest

from motif.compose.voicing import VoicingStyle, voice_progression
from motif.theory.harmony import progression
from motif.theory.pitch import Key


def parallels(a, b):
    """Count parallel fifths and octaves between two voicings."""
    n = 0
    for i in range(len(a)):
        for j in range(i + 1, len(a)):
            now = (a[j].midi - a[i].midi) % 12
            then = (b[j].midi - b[i].midi) % 12
            if now in (0, 7) and now == then and a[i].midi != b[i].midi \
                    and a[j].midi != b[j].midi:
                n += 1
    return n


CASES = [
    ("C", "major", ["I", "vi", "IV", "ii6", "V7", "I"]),
    ("Eb", "minor", ["i", "iv", "bII6", "V7", "i"]),
    ("A", "minor", ["i", "iio6", "V7", "VI", "iv", "V", "i"]),
    ("Db", "major", ["I", "V65/vi", "vi", "IV", "V7", "I"]),
    ("F#", "minor", ["i", "VI", "iv", "V7", "i"]),
]


@pytest.mark.parametrize("tonic,mode,romans", CASES)
def test_voicings_are_clean(tonic, mode, romans):
    key = Key(tonic, mode)
    chords = progression(romans, key)
    style = VoicingStyle(n_voices=4, low=40, high=79)
    voiced = voice_progression(chords, key, style, rng=random.Random(2))

    assert len(voiced) == len(chords)
    for v in voiced:
        assert len(v) == 4
        assert v == sorted(v, key=lambda p: p.midi), "voices must not cross"
        assert all(40 <= p.midi <= 79 for p in v), "voices must stay in range"
        for i in range(1, len(v) - 1):
            assert v[i + 1].midi - v[i].midi <= 14, "upper voices spaced too widely"

    total = sum(parallels(voiced[i], voiced[i + 1]) for i in range(len(voiced) - 1))
    assert total <= 1, f"{total} parallel fifths/octaves"


def test_dominant_seventh_resolves_downward():
    key = Key("C", "major")
    chords = progression(["V7", "I"], key)
    voiced = voice_progression(chords, key, VoicingStyle(n_voices=4, low=40, high=79),
                               rng=random.Random(2))
    seventh_pc = (chords[0].root.pc + chords[0].intervals[-1]) % 12
    idx = [i for i, p in enumerate(voiced[0]) if p.pc == seventh_pc]
    assert idx, "the seventh should be present in the V7 voicing"
    for i in idx:
        moved = voiced[1][i].midi - voiced[0][i].midi
        assert moved <= 0, "a chordal seventh must not rise"


def test_leading_tone_rises_to_the_tonic():
    key = Key("C", "major")
    chords = progression(["V", "I"], key)
    voiced = voice_progression(chords, key, VoicingStyle(n_voices=4, low=40, high=79),
                               rng=random.Random(5))
    lt = (key.tonic_pc - 1) % 12
    upper = [i for i, p in enumerate(voiced[0]) if p.pc == lt and i > 0]
    for i in upper:
        assert voiced[1][i].midi - voiced[0][i].midi in (1, 0, -4, -3), \
            "the leading tone should resolve up or be handled as an inner voice"
