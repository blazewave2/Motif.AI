"""MusicXML and MIDI output must be structurally valid and round-trip."""
import struct
import xml.dom.minidom as minidom
from xml.etree import ElementTree as ET

import pytest

from motif.engrave.beaming import apply_beams
from motif.engrave.midi import to_midi
from motif.engrave.musicxml import to_musicxml
from motif.engrave.musicxml_reader import read_musicxml
from motif.score import (DIVISIONS, EIGHTH, HALF, Direction, Note, Part, QUARTER, Score,
                         SIXTEENTH, TempoMark, Tuplet, WHOLE,
                         note_type_and_dots, split_duration)
from motif.theory.pitch import Key, Pitch


@pytest.fixture
def sample_score():
    s = Score(title="Test", key=Key("Eb", "minor"), time=(4, 4))
    p = Part(staves=2, clefs={1: "G", 2: "F"})
    s.add_part(p)
    s.tempos.append(TempoMark(1, 72, text="Andante"))
    m = p.measure(1)
    m.add(Note([Pitch.parse("Eb5")], QUARTER, voice=1, staff=1, slur_start=1))
    m.add(Note([Pitch.parse("Gb5")], QUARTER, voice=1, staff=1,
               articulations=["tenuto"]))
    m.add(Note([Pitch.parse("Bb5")], HALF, voice=1, staff=1, slur_stop=1))
    m.add(Note([Pitch.parse("Eb2"), Pitch.parse("Bb2")], WHOLE, voice=5, staff=2))
    m.directions.append(Direction("dynamics", "p", staff=1))
    m.directions.append(Direction("pedal", "start", staff=2))
    return s


class TestDurations:
    def test_note_types(self):
        assert note_type_and_dots(QUARTER) == ("quarter", 0)
        assert note_type_and_dots(QUARTER + QUARTER // 2) == ("quarter", 1)
        assert note_type_and_dots(WHOLE) == ("whole", 0)

    def test_offbeat_note_is_split_for_readability(self):
        # Three quarters starting on the offbeat notate as 8th + half + 8th.
        pieces = split_duration(QUARTER * 3, QUARTER // 2, QUARTER, WHOLE)
        assert sum(pieces) == QUARTER * 3
        assert len(pieces) > 1

    def test_splits_always_preserve_total(self):
        for offset in range(0, WHOLE, SIXTEENTH):
            for dur in range(SIXTEENTH, WHOLE + 1, SIXTEENTH):
                if offset + dur > WHOLE:
                    continue
                assert sum(split_duration(dur, offset, QUARTER, WHOLE)) == dur


class TestMusicXML:
    def test_is_well_formed(self, sample_score):
        xml = to_musicxml(sample_score)
        minidom.parseString(xml)
        root = ET.fromstring(xml)
        assert root.tag == "score-partwise"
        assert root.get("version") == "4.0"

    def test_carries_key_metre_and_markings(self, sample_score):
        root = ET.fromstring(to_musicxml(sample_score))
        assert root.findtext(".//key/fifths") == "-6"
        assert root.findtext(".//time/beats") == "4"
        assert root.find(".//dynamics/p") is not None
        assert root.find(".//pedal") is not None
        assert root.find(".//slur") is not None
        assert root.find(".//articulations/tenuto") is not None

    def test_round_trips(self, sample_score):
        back = read_musicxml(to_musicxml(sample_score))
        assert back.title == "Test"
        assert str(back.key) == "Eb minor"
        assert back.time == (4, 4)
        assert back.measure_count == 1

    def test_pickup_bar_numbered_zero_is_read(self):
        # music21 and many publishers number an anacrusis 0; indexing by that
        # number used to crash the reader and silently drop real scores.
        xml = to_musicxml(Score(parts=[Part(measures=[])]))
        xml = xml.replace('<measure number="1"', '<measure number="0"')
        score = read_musicxml(xml)
        assert score.measure_count >= 0

    def test_measure_numbers_are_one_based(self):
        p = Part()
        with pytest.raises(ValueError):
            p.measure(0)

    def test_provenance_metadata_round_trips(self, sample_score):
        # "Continue in the same style" depends on reading this back exactly,
        # rather than re-guessing the composer from the notes.
        sample_score.metadata.update({
            "style": "chopin", "form": "nocturne", "ensemble": "solo_piano",
            "character": "wistful", "seed": 42, "prompt": "a nocturne",
        })
        back = read_musicxml(to_musicxml(sample_score))
        assert back.metadata["style"] == "chopin"
        assert back.metadata["form"] == "nocturne"
        assert back.metadata["ensemble"] == "solo_piano"
        assert back.metadata["seed"] == 42          # comes back as an int
        assert back.metadata["prompt"] == "a nocturne"

    def test_missing_provenance_metadata_is_simply_absent(self, sample_score):
        # A score with no Motif provenance (hand-written, or from another
        # application) must not crash the reader or fabricate a style.
        back = read_musicxml(to_musicxml(sample_score))
        assert "style" not in back.metadata


class TestBeaming:
    """Nothing upstream ever set ``Note.beam`` — without this pass every
    eighth note and shorter prints as an isolated flagged note."""

    def _voice(self, durations, time=(4, 4)):
        p = Part()
        m = p.measure(1)
        for d in durations:
            m.add(Note([Pitch.parse("C4")], d, voice=1, staff=1))
        apply_beams(p, time)
        return m.voices[1]

    def test_four_eighths_beam_in_pairs_per_beat(self):
        # Simple quadruple time beams by the quarter-note beat, not the whole
        # bar: two pairs, not one group of four.
        notes = self._voice([EIGHTH] * 4)
        assert [n.beam for n in notes] == [["begin"], ["end"], ["begin"], ["end"]]

    def test_quarter_notes_are_never_beamed(self):
        notes = self._voice([QUARTER, QUARTER, QUARTER, QUARTER])
        assert all(n.beam == [] for n in notes)

    def test_a_lone_eighth_with_no_beamable_partner_is_not_beamed(self):
        # The eighth shares its beat only with a rest, so it has no partner.
        p = Part()
        m = p.measure(1)
        m.add(Note([Pitch.parse("C4")], QUARTER, voice=1, staff=1))
        m.add(Note([Pitch.parse("D4")], EIGHTH, voice=1, staff=1))
        m.add(Note([], EIGHTH, voice=1, staff=1))
        m.add(Note([Pitch.parse("E4")], QUARTER, voice=1, staff=1))
        m.add(Note([Pitch.parse("F4")], QUARTER, voice=1, staff=1))
        apply_beams(p, (4, 4))
        assert m.voices[1][1].beam == []

    def test_rest_breaks_a_beam_group(self):
        p = Part()
        m = p.measure(1)
        m.add(Note([Pitch.parse("C4")], EIGHTH, voice=1, staff=1))
        m.add(Note([], EIGHTH, voice=1, staff=1))                 # rest
        m.add(Note([Pitch.parse("D4")], EIGHTH, voice=1, staff=1))
        m.add(Note([Pitch.parse("E4")], EIGHTH, voice=1, staff=1))
        apply_beams(p, (4, 4))
        notes = m.voices[1]
        assert notes[0].beam == [] and notes[1].beam == []        # isolated either side
        assert notes[2].beam == ["begin"] and notes[3].beam == ["end"]

    def test_dotted_eighth_sixteenth_pair_hooks_the_sixteenth(self):
        notes = self._voice([EIGHTH + SIXTEENTH, SIXTEENTH])
        assert notes[0].beam == ["begin"]
        assert notes[1].beam == ["end", "backward hook"]

    def test_beam_group_never_crosses_a_beat_boundary(self):
        # An eighth ending a beat and one opening the next do not share a beam.
        notes = self._voice([QUARTER, EIGHTH, EIGHTH, EIGHTH, EIGHTH, QUARTER])
        assert notes[1].beam == ["begin"] and notes[2].beam == ["end"]
        assert notes[3].beam == ["begin"] and notes[4].beam == ["end"]

    def test_compound_metre_beams_the_whole_dotted_quarter(self):
        notes = self._voice([EIGHTH, EIGHTH, EIGHTH, EIGHTH, EIGHTH, EIGHTH], time=(6, 8))
        assert [n.beam for n in notes[:3]] == [["begin"], ["continue"], ["end"]]
        assert [n.beam for n in notes[3:]] == [["begin"], ["continue"], ["end"]]

    def test_triplet_eighths_beam_together(self):
        p = Part()
        m = p.measure(1)
        for i in range(3):
            n = Note([Pitch.parse("C4")], DIVISIONS // 3, voice=1, staff=1)
            n.tuplet = Tuplet(3, 2, "eighth", start=(i == 0), stop=(i == 2))
            m.add(n)
        m.add(Note([Pitch.parse("C4")], QUARTER * 3, voice=1, staff=1))
        apply_beams(p, (4, 4))
        notes = m.voices[1]
        assert [n.beam for n in notes[:3]] == [["begin"], ["continue"], ["end"]]

    def test_musicxml_export_carries_beam_elements(self):
        p = Part()
        m = p.measure(1)
        for _ in range(4):
            m.add(Note([Pitch.parse("C4")], EIGHTH, voice=1, staff=1))
        apply_beams(p, (4, 4))
        score = Score(parts=[p])
        root = ET.fromstring(to_musicxml(score))
        beams = root.findall(".//beam")
        assert len(beams) == 4
        assert [b.text for b in beams] == ["begin", "end", "begin", "end"]


class TestMIDI:
    def test_header_and_tracks_parse(self, sample_score):
        data = to_midi(sample_score)
        assert data[:4] == b"MThd"
        ntracks = struct.unpack(">H", data[10:12])[0]
        assert struct.unpack(">H", data[12:14])[0] == DIVISIONS
        pos, seen = 14, 0
        while pos < len(data):
            assert data[pos:pos + 4] == b"MTrk"
            length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
            pos += 8 + length
            seen += 1
        assert seen == ntracks
