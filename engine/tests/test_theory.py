"""Theory: spelling, chords and voice leading."""
import pytest

from motif.theory.harmony import Chord, progression, roman_to_chord, sequence_progression
from motif.theory.pitch import Interval, Key, Pitch, from_midi


class TestPitch:
    def test_parse_and_name(self):
        assert str(Pitch.parse("Eb4")) == "Eb4"
        assert str(Pitch.parse("F#5")) == "F#5"
        assert Pitch.parse("Cb5").midi == Pitch.parse("B4").midi

    def test_diatonic_transposition_uses_key_signature(self):
        # A step below Eb in Eb minor is Db, never the enharmonic D#.
        k = Key("Eb", "minor")
        assert str(Pitch.parse("Eb5").transpose_diatonic(-1, k)) == "Db5"
        assert str(Pitch.parse("Eb5").transpose_diatonic(-2, k)) == "Cb5"

    def test_harmonic_minor_raises_the_seventh(self):
        k = Key("Eb", "minor")
        pcs = k.scale_pcs_for("harmonic_minor")
        assert str(Pitch.parse("Eb5").transpose_diatonic(-1, k, pcs)) == "D5"

    @pytest.mark.parametrize("tonic,mode,expected", [
        ("Eb", "minor", ["Eb4", "F4", "Gb4", "Ab4", "Bb4", "Cb5", "Db5"]),
        ("C#", "major", ["C#4", "D#4", "E#4", "F#4", "G#4", "A#4", "B#4"]),
        ("C", "major", ["C4", "D4", "E4", "F4", "G4", "A4", "B4"]),
    ])
    def test_scale_spelling(self, tonic, mode, expected):
        k = Key(tonic, mode)
        assert [str(k.degree_pitch(d, 4)) for d in range(1, 8)] == expected

    def test_key_signature_fifths(self):
        assert Key("Eb", "minor").fifths == -6
        assert Key("C#", "major").fifths == 7
        assert Key("C", "major").fifths == 0

    def test_spelling_stays_on_the_flat_side(self):
        k = Key("Eb", "minor")
        for midi in range(48, 84):
            p = k.spell(midi)
            assert p.alter <= 0 or p.alter == 0, f"{p} used a sharp in a 6-flat key"

    def test_intervals(self):
        assert Interval.named("m", 3).semitones == 3
        assert Interval.named("P", 5).semitones == 7
        assert str(Pitch.parse("Eb4").transpose_by(Interval.named("m", 3))) == "Gb4"

    @pytest.mark.parametrize("text", ["ZZZ", "!!!", "", "Hb major", "C quantum"])
    def test_bad_keys_are_rejected(self, text):
        with pytest.raises(ValueError):
            Key.parse(text)

    @pytest.mark.parametrize("text,expected", [
        ("Eb minor", "Eb minor"), ("F# dorian", "F# dorian"),
        ("C", "C major"), ("db MAJOR", "Db major"),
    ])
    def test_good_keys_parse(self, text, expected):
        assert str(Key.parse(text)) == expected


class TestHarmony:
    def test_diminished_seventh_spells_in_thirds(self):
        c = roman_to_chord("viio7", Key("Eb", "minor"))
        assert [str(p) for p in c.pitches()] == ["D5", "F5", "Ab5", "Cb6"]

    def test_neapolitan_keeps_its_letter(self):
        c = roman_to_chord("bII6", Key("Eb", "minor"))
        assert "Fb5" in [str(p) for p in c.pitches()]

    def test_applied_dominant(self):
        c = roman_to_chord("V7/V", Key("C", "major"))
        assert c.root.name == "D" and c.quality == "dom7"

    def test_inversion_moves_the_bass(self):
        c = roman_to_chord("I64", Key("C", "major"))
        assert c.bass_pitch(3).name == "G"

    def test_every_roman_in_the_library_builds(self):
        from motif.theory.harmony import CADENCES, PROGRESSION_LIBRARY
        for key in (Key("C", "major"), Key("Eb", "minor"), Key("F#", "minor")):
            for romans in list(PROGRESSION_LIBRARY.values()):
                for r in [x for group in romans for x in group]:
                    assert roman_to_chord(r, key).pitches()
            for romans in CADENCES.values():
                for r in romans:
                    assert roman_to_chord(r, key).pitches()

    def test_sequences_have_the_requested_length(self):
        assert len(sequence_progression("i", Key("A", "minor"), 7)) == 7
