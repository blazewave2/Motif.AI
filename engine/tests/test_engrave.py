"""MusicXML and MIDI output must be structurally valid and round-trip."""
import struct
import xml.dom.minidom as minidom
from xml.etree import ElementTree as ET

import pytest

from motif.engrave.midi import to_midi
from motif.engrave.musicxml import to_musicxml
from motif.engrave.musicxml_reader import read_musicxml
from motif.score import (DIVISIONS, HALF, Direction, Note, Part, QUARTER, Score,
                         TempoMark, WHOLE, bar_duration, note_type_and_dots,
                         split_duration)
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
        for offset in range(0, WHOLE, 120):
            for dur in range(120, WHOLE + 1, 120):
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
