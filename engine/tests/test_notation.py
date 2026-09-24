"""MSN: the notation the composer writes in, and everything built on it."""
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from motif.engrave.midi import to_midi
from motif.engrave.musicxml import to_musicxml
from motif.engrave.musicxml_reader import read_musicxml
from motif.notation import parse, render
from motif.notation.analysis import report
from motif.notation.from_score import from_score
from motif.notation.msn import parse_duration, parse_key_text, parse_pitch
from motif.notation.spec import SPEC
from motif.notation.to_score import to_score
from motif.notation.validate import validate
from motif.score import DIVISIONS

FIXTURE = Path(__file__).parent / "fixtures" / "nocturne.msn"


def piano(body: str, header: str = "key: C major\ntime: 4/4\n") -> str:
    return header + body


def errors(piece, **kw):
    return [i for i in validate(piece, **kw) if i.severity == "error"]


# ---------------------------------------------------------------------------
class TestReading:
    def test_header_and_parts(self):
        p = parse("title: Study\nkey: Eb minor\ntime: 6/8\ntempo: 60 \"Andante\"\n"
                  "part: Vn1 violin \"Violin I\"\npart: Vc cello\nm1\n  Vn1: R\n  Vc: R\n")
        assert p.title == "Study"
        assert str(p.key) == "Eb minor"
        assert p.time == (6, 8)
        assert p.tempo == 60 and p.tempo_text == "Andante"
        assert [(x.id, x.instrument.key, x.display_name) for x in p.parts] == [
            ("Vn1", "violin", "Violin I"), ("Vc", "cello", "Violoncello")]

    def test_no_part_lines_means_solo_piano(self):
        p = parse(piano("m1\n  RH: C5:w\n  LH: C3:w\n"))
        assert [x.instrument.key for x in p.parts] == ["piano"]
        assert not p.issues

    @pytest.mark.parametrize("text,midi,alter", [
        ("C4", 60, 0), ("B3", 59, 0), ("C#4", 61, 1), ("Bb3", 58, -1),
        ("F##5", 79, 2), ("Ebb4", 62, -2), ("Cb4", 59, -1), ("B#3", 60, 1),
        ("bb4", 70, -1), ("A0", 21, 0), ("C8", 108, 0)])
    def test_pitches_are_absolute_and_spelled(self, text, midi, alter):
        p = parse_pitch(text)
        assert p.midi == midi and p.alter == alter

    @pytest.mark.parametrize("code,value,dots", [
        ("q", Fraction(1), 0), ("e.", Fraction(1, 2), 1), ("h..", Fraction(2), 2),
        ("s", Fraction(1, 4), 0), ("8", Fraction(1, 2), 0), ("w", Fraction(4), 0)])
    def test_durations(self, code, value, dots):
        assert parse_duration(code) == (value, dots)

    @pytest.mark.parametrize("text,expect", [
        ("C# minor", "C# minor"), ("c#m", "C# minor"), ("E-flat major", "Eb major"),
        ("Db", "Db major"), ("f", "F minor"), ("D dorian", "D dorian")])
    def test_keys_read_the_way_people_write_them(self, text, expect):
        assert str(parse_key_text(text)) == expect

    def test_chords_are_sorted_and_deduplicated(self):
        p = parse(piano("m1\n  RH: [G4 C4 E4 C4]:w\n  LH: R\n"))
        ev = p.measures[0].voices[0].events[0]
        assert [x.midi for x in ev.pitches] == [60, 64, 67]

    def test_bar_offsets_follow_the_durations(self):
        p = parse(piano("m1\n  RH: C5:q. D5:e {3 E5:e F5:e G5:e} A5:q\n  LH: R\n"))
        evs = p.measures[0].voices[0].events
        assert [e.offset for e in evs] == [0, Fraction(3, 2), 2, Fraction(7, 3),
                                          Fraction(8, 3), 3]
        assert p.measures[0].voices[0].duration == 4

    def test_ties_carry_across_the_bar_line(self):
        p = parse(piano("m1\n  RH: C5:h G5:h~\n  LH: R\nm2\n  RH: G5:q E5:h.\n  LH: R\n"))
        assert p.measures[0].voices[0].events[1].ties == [True]
        assert not p.issues

    def test_a_tie_to_a_different_pitch_is_dropped_with_a_warning(self):
        p = parse(piano("m1\n  RH: C5:h G5:h~\n  LH: R\nm2\n  RH: A5:w\n  LH: R\n"))
        assert p.measures[0].voices[0].events[1].ties == [False]
        assert any(i.code == "tie" for i in p.warnings)

    def test_partial_chord_ties(self):
        p = parse(piano("m1\n  RH: [E4~ G4 C5~]:h [E4 A4 C5]:h\n  LH: R\n"))
        assert p.measures[0].voices[0].events[0].ties == [True, False, True]

    def test_slurs_span_bars(self):
        p = parse(piano("m1\n  RH: (C5:h D5:h\n  LH: R\nm2\n  RH: E5:w)\n  LH: R\n"))
        assert p.measures[0].voices[0].events[0].slur_starts == 1
        assert p.measures[1].voices[0].events[0].slur_stops == 1

    def test_an_unclosed_slur_is_closed_at_the_end(self):
        p = parse(piano("m1\n  RH: (C5:h D5:h\n  LH: R\n"))
        assert p.measures[0].voices[0].events[-1].slur_stops == 1
        assert any(i.code == "slur" for i in p.warnings)

    def test_tuplet_ratios(self):
        p = parse(piano("m1\n  RH: {5 C5:s D5:s E5:s F5:s G5:s} {7 C5:s D5:s E5:s F5:s "
                        "G5:s A5:s B5:s} {3 C5:q D5:q E5:q}\n  LH: R\n"))
        evs = p.measures[0].voices[0].events
        assert evs[0].tuplet == (5, 4) and evs[0].duration == Fraction(1, 5)
        assert evs[5].tuplet == (7, 4) and evs[5].duration == Fraction(1, 7)
        assert evs[12].tuplet == (3, 2) and evs[12].duration == Fraction(2, 3)
        assert evs[0].tuplet_start and evs[4].tuplet_stop
        assert p.measures[0].voices[0].duration == 4

    def test_grace_notes_lead_into_the_next_note(self):
        p = parse(piano("m1\n  RH: {acc D5:s} C5:q {g E5:t D5:t} C5:q {app B4:e} C5:h\n"
                        "  LH: R\n"))
        evs = p.measures[0].voices[0].events
        assert len(evs) == 3
        assert evs[0].grace_slash and len(evs[0].graces) == 1
        assert not evs[1].grace_slash and len(evs[1].graces) == 2
        assert p.measures[0].voices[0].duration == 4

    def test_directions_and_text(self):
        p = parse(piano('m1\n  RH: !p !cresc C5:q D5:q !end !f E5:q "dolce" ^"rit." F5:q\n'
                        "  LH: !ped C3:h !pedup !rit C3:h\n"))
        rh = [(m.kind, m.value, m.placement) for m in p.measures[0].voices[0].markings]
        assert rh == [("dynamic", "p", ""), ("hairpin", "crescendo", ""),
                      ("hairpin_end", "", ""), ("dynamic", "f", ""),
                      ("text", "dolce", ""), ("text", "rit.", "above")]
        lh = [(m.kind, m.value) for m in p.measures[0].voices[1].markings]
        assert lh == [("pedal", "down"), ("pedal", "up"), ("text", "rit.")]

    def test_bar_attributes(self):
        p = parse(piano('m1\n  RH: R\n  LH: R\nm2 key="E major" time=3/4 tempo=72 "Più mosso" '
                        'mark="B" clef.LH=treble barline=double repeat=start\n'
                        "  RH: R\n  LH: R\nm3 tempo=\"Tempo I\" ending=1\n  RH: R\n  LH: R\n"))
        m2, m3 = p.measures[1], p.measures[2]
        assert str(m2.key) == "E major" and m2.time == (3, 4)
        assert m2.tempo == 72 and m2.tempo_text == "Più mosso" and m2.mark == "B"
        assert m2.clefs == {("Pno", 2): "G"} and m2.barline == "double"
        assert m2.repeat == "start"
        assert m3.tempo is None and m3.tempo_text == "Tempo I" and m3.ending == 1

    def test_comments_are_kept_with_their_bar(self):
        p = parse(piano("# the second theme\nm1  # arrives in the relative major\n"
                        "  RH: R\n  LH: R\n"))
        assert p.measures[0].comments == ["the second theme", "arrives in the relative major"]

    def test_fenced_output_is_accepted(self):
        p = parse("```msn\n" + piano("m1\n  RH: C5:w\n  LH: C3:w\n") + "```\n")
        assert p.numbers == [1] and not p.issues

    @pytest.mark.parametrize("line,fragment", [
        ("  XX: C5:w", "unknown voice label"),
        ("  RH: C5", "no duration"),
        ("  RH: H5:w", "could not read"),
        ("  RH: C5:w !loud", "unknown direction"),
        ("  RH: {3 C5:e D5:e E5:e", "never closed"),
        ("  RH: R C5:q", "whole-bar rest"),
    ])
    def test_errors_name_the_problem(self, line, fragment):
        p = parse(piano("m1\n" + line + "\n  LH: R\n"))
        assert any(fragment in i.message for i in p.errors), [str(i) for i in p.issues]

    def test_a_voice_written_twice_in_a_bar_is_an_error(self):
        p = parse(piano("m1\n  RH: C5:w\n  RH: D5:w\n  LH: R\n"))
        assert any("written twice" in i.message for i in p.errors)

    def test_render_is_stable(self):
        p = parse(FIXTURE.read_text())
        out = render(p)
        assert render(parse(out)) == out
        assert not parse(out).errors

    def test_the_reference_example_is_valid(self):
        ex = SPEC.split("## A complete example", 1)[1]
        body = "\n".join(l[4:] if l.startswith("    ") else l for l in ex.splitlines())
        p = parse(body)
        assert p.numbers == [1, 2, 3, 4]
        assert not validate(p)


# ---------------------------------------------------------------------------
class TestValidation:
    def test_short_and_long_bars(self):
        p = parse(piano("m1\n  RH: C5:h\n  LH: C3:w C3:q\n"))
        msgs = [str(i) for i in errors(p)]
        assert any("m1 RH" in m and "2 quarters short" in m for m in msgs)
        assert any("m1 LH" in m and "too long" in m for m in msgs)

    def test_metre_changes_are_respected(self):
        p = parse(piano("m1\n  RH: C5:w\n  LH: R\nm2 time=3/4\n  RH: C5:h.\n  LH: R\n"))
        assert not errors(p)

    def test_pickup_bar(self):
        p = parse(piano("m0\n  RH: G4:e A4:e\n  LH: r:q\nm1\n  RH: C5:w\n  LH: C3:w\n"))
        assert not errors(p)
        bad = parse(piano("m0\n  RH: G4:w\n  LH: R\nm1\n  RH: C5:w\n  LH: C3:w\n"))
        assert any("pickup" in i.message for i in errors(bad))

    def test_ranges(self):
        p = parse("part: Fl flute\nm1\n  Fl: C8:w\n")
        assert any(i.code == "range" for i in errors(p))

    def test_hand_span(self):
        wide = parse(piano("m1\n  RH: R\n  LH: [C2 F3]:w\n"))
        assert any(i.code == "span" for i in errors(wide))
        rolled = parse(piano("m1\n  RH: R\n  LH: [C2 G2 E3]:w+arp\n"))
        assert not errors(rolled)
        tenth = parse(piano("m1\n  RH: R\n  LH: [C3 E4]:w\n"))
        assert not errors(tenth)

    def test_voices_on_one_staff_share_a_hand(self):
        p = parse(piano("m1\n  RH: C6:w\n  RH2: C4:w\n  LH: R\n"))
        assert any(i.code == "span" for i in errors(p))

    def test_single_line_instruments_cannot_play_chords(self):
        p = parse("part: Ob oboe\nm1\n  Ob: [C5 E5]:w\n")
        assert any(i.code == "chord" for i in errors(p))

    def test_numbering(self):
        p = parse(piano("m1\n  RH: R\n  LH: R\nm3\n  RH: R\n  LH: R\n"))
        assert any(i.code == "numbering" for i in errors(p, expect=(1, 3)))

    def test_incomplete_tuplet_is_a_warning(self):
        p = parse(piano("m1\n  RH: {3 C5:e D5:e} E5:h.\n  LH: R\n"))
        assert any(i.code == "tuplet" for i in validate(p))


# ---------------------------------------------------------------------------
class TestEngraving:
    def test_tuplet_ticks_are_exact(self):
        p = parse(piano("m1\n  RH: {3 C5:e D5:e E5:e} {5 C5:s D5:s E5:s F5:s G5:s} "
                        "{7 C5:s D5:s E5:s F5:s G5:s A5:s B5:s} C5:q\n  LH: R\n"))
        score, issues = to_score(p)
        durs = [n.duration for n in score.parts[0].measures[0].voices[1]]
        assert durs[:3] == [DIVISIONS // 3] * 3
        assert durs[3:8] == [DIVISIONS // 5] * 5
        assert durs[8:15] == [DIVISIONS // 7] * 7
        assert not issues

    def test_repairs_are_reported(self):
        p = parse(piano("m1\n  RH: C5:h\n  LH: C3:w C3:w\n"))
        score, issues = to_score(p)
        assert len(issues) == 2
        m = score.parts[0].measures[0]
        assert sum(n.duration for n in m.voices[1]) == 4 * DIVISIONS
        assert sum(n.duration for n in m.voices[5]) == 4 * DIVISIONS

    def test_transposing_instruments_are_written_at_written_pitch(self):
        p = parse("key: Eb major\npart: Cl clarinet\npart: Hn horn\n"
                  "m1\n  Cl: Eb5:w\n  Hn: Bb3:w\n")
        score, _ = to_score(p)
        cl, hn = score.parts
        assert str(cl.measures[0].key) == "F major"
        assert cl.measures[0].voices[1][0].pitches[0].name == "F"
        assert cl.transpose == (-1, -2, 0)
        assert str(hn.measures[0].key) == "Bb major"
        assert hn.measures[0].voices[1][0].pitches[0].name == "F"
        root = ET.fromstring(to_musicxml(score))
        assert root.find(".//part[@id='P1']//transpose/chromatic").text == "-2"

    def test_transposed_key_is_readable(self):
        p = parse("key: B major\npart: Cl clarinet\nm1\n  Cl: B4:w\n")
        score, _ = to_score(p)
        assert abs(score.parts[0].measures[0].key.fifths) <= 6

    def test_pickup_bar_is_implicit_and_short(self):
        p = parse(piano("m0\n  RH: G4:e A4:e\n  LH: r:q\nm1\n  RH: C5:w\n  LH: C3:w\n"))
        score, _ = to_score(p)
        m0 = score.parts[0].measures[0]
        assert m0.implicit and m0.number == 0
        root = ET.fromstring(to_musicxml(score))
        assert root.find(".//measure").get("implicit") == "yes"
        midi = to_midi(score)
        assert midi[:4] == b"MThd"

    def test_whole_bar_and_hidden_rests(self):
        p = parse(piano("m1\n  RH: C5:w\n  RH2: s:h E4:h\n  LH: R\n"))
        score, _ = to_score(p)
        xml = to_musicxml(score)
        root = ET.fromstring(xml)
        assert root.find(".//rest[@measure='yes']") is not None
        assert any(n.get("print-object") == "no" for n in root.iter("note"))

    def test_pedal_marks_start_change_and_stop(self):
        p = parse(piano("m1\n  RH: C5:w\n  LH: !ped C3:h !ped G2:h\nm2\n  RH: C5:w\n"
                        "  LH: C3:h !pedup r:h\n"))
        score, _ = to_score(p)
        peds = [d.value for m in score.parts[0].measures for d in m.directions
                if d.kind == "pedal"]
        assert peds == ["start", "change", "stop"]

    def test_one_dynamic_between_the_staves(self):
        p = parse(piano("m1\n  RH: !p C5:w\n  LH: !p C3:w\n"))
        score, _ = to_score(p)
        dyn = [d for d in score.parts[0].measures[0].directions if d.kind == "dynamics"]
        assert len(dyn) == 1 and dyn[0].staff == 1

    def test_left_hand_climbing_high_changes_clef(self):
        p = parse(piano("m1\n  RH: C6:w\n  LH: C3:w\nm2\n  RH: C6:w\n  LH: [E4 G4]:w\n"
                        "m3\n  RH: C6:w\n  LH: C3:w\n"))
        score, _ = to_score(p)
        ms = score.parts[0].measures
        assert ms[1].clefs == {2: "G"} and ms[2].clefs == {2: "F"}

    def test_rit_is_heard(self):
        p = parse(piano("tempo: 80\nm1\n  RH: C5:w\n  LH: C3:w\nm2\n  RH: ^\"rit.\" C5:w\n"
                        "  LH: C3:w\nm3\n  RH: C5:w\n  LH: C3:w\n"))
        score, _ = to_score(p)
        hidden = [t for t in score.tempos if not t.visible]
        assert hidden and hidden[-1].bpm < 80
        assert "<sound tempo=" in to_musicxml(score)

    def test_accidentals_are_printed_only_where_needed(self):
        p = parse("key: D major\nm1\n  RH: F#4:q F4:q F4:q F#4:q\n  LH: R\n")
        score, _ = to_score(p)
        root = ET.fromstring(to_musicxml(score))
        notes = [n for n in root.iter("note") if n.find("pitch") is not None]
        shown = [(n.findtext("accidental") or "") for n in notes]
        assert shown == ["", "natural", "", "sharp"]

    def test_lyrics(self):
        p = parse('part: S soprano\nm1\n  S: C5:q@"Ah" D5:q@"lo-" E5:h@"ve"\n')
        score, _ = to_score(p)
        root = ET.fromstring(to_musicxml(score))
        syl = [(l.findtext("syllabic"), l.findtext("text")) for l in root.iter("lyric")]
        assert syl == [("single", "Ah"), ("begin", "lo"), ("end", "ve")]

    def test_volta_brackets(self):
        p = parse(piano("m1 repeat=start\n  RH: C5:w\n  LH: R\nm2 ending=1 repeat=end\n"
                        "  RH: D5:w\n  LH: R\nm3 ending=2\n  RH: E5:w\n  LH: R\n"))
        score, _ = to_score(p)
        root = ET.fromstring(to_musicxml(score))
        endings = [(e.get("number"), e.get("type")) for e in root.iter("ending")]
        assert endings == [("1", "start"), ("1", "stop"), ("2", "start"), ("2", "discontinue")]


# ---------------------------------------------------------------------------
class TestRoundTrip:
    def _signature(self, piece):
        out = []
        for m in piece.measures:
            for vl in sorted(m.voices, key=lambda v: (v.part, v.staff, v.voice)):
                out.append((m.number, vl.staff, vl.voice, [
                    (e.kind, tuple(p.midi for p in e.pitches), e.duration, tuple(e.ties),
                     e.slur_starts, e.slur_stops, tuple(sorted(e.marks)), len(e.graces))
                    for e in vl.events]))
        return out

    def test_fixture_survives_musicxml(self):
        src = parse(FIXTURE.read_text())
        score, issues = to_score(src)
        assert not issues
        back = from_score(read_musicxml(to_musicxml(score)))
        assert self._signature(back) == self._signature(src)
        assert str(back.key) == "C# minor" and back.tempo == 54

    def test_transposing_part_reads_back_in_concert_pitch(self):
        src = parse("key: Eb major\npart: Cl clarinet\nm1\n  Cl: Eb5:h G5:h\n")
        score, _ = to_score(src)
        back = from_score(read_musicxml(to_musicxml(score)))
        assert [p.midi for e in back.measures[0].voices[0].events for p in e.pitches] == \
            [75, 79]
        assert str(back.key) == "Eb major"

    def test_second_voice_entering_mid_bar_keeps_its_place(self):
        # The shape MuseScore exports: voice 2 starts after a <forward>.
        xml = """<?xml version="1.0"?><score-partwise version="4.0"><part-list>
        <score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
        <part id="P1"><measure number="1"><attributes><divisions>1</divisions>
        <key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time>
        </attributes>
        <note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration>
        <voice>1</voice><type>whole</type></note>
        <backup><duration>4</duration></backup><forward><duration>2</duration></forward>
        <direction><direction-type><dynamics><f/></dynamics></direction-type></direction>
        <note><pitch><step>E</step><octave>4</octave></pitch><duration>2</duration>
        <voice>2</voice><type>half</type></note>
        </measure></part></score-partwise>"""
        piece = from_score(read_musicxml(xml))
        m = piece.measures[0]
        v2 = next(v for v in m.voices if v.voice == 2)
        assert [e.kind for e in v2.events] == ["spacer", "note"]
        assert v2.events[1].offset == 2
        v1 = next(v for v in m.voices if v.voice == 1)
        assert [(k.kind, k.value, k.offset) for k in v1.markings] == [("dynamic", "f", 2)]


class TestAnalysis:
    def test_report_reads_like_a_digest(self):
        text = report(parse(FIXTURE.read_text()))
        assert "8 bars for Piano" in text
        assert "m2:" in text and "G#4" in text
        assert "Melody (top line)" in text
