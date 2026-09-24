"""Every score Motif writes must be valid MusicXML.

MuseScore checks each file it opens against the MusicXML schema and answers
a failure with an "import anyway?" prompt, so validity is something the
musician sees. The schema in ``schema/musicxml-3.1`` is the one MuseScore 3
embeds (MuseScore 4 validates against 4.0, which accepts every 3.1 file);
it is published by the W3C Music Notation Community Group under the W3C
Community Final Specification Agreement. Checked with xmllint, and skipped
where it isn't installed.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from motif.agent.prompt_parser import parse_prompt
from motif.compose.composer import compose
from motif.engrave.musicxml import to_musicxml
from motif.engrave.musicxml_reader import read_musicxml
from motif.notation import parse
from motif.notation.to_score import to_score
from motif.notation.validate import validate

HERE = Path(__file__).parent
SCHEMA = HERE / "schema" / "musicxml-3.1" / "musicxml.xsd"
XMLLINT = shutil.which("xmllint")
needs_xmllint = pytest.mark.skipif(not XMLLINT, reason="xmllint is not installed")


def schema_errors(xml: str, tmp_path: Path, name: str = "score") -> list[str]:
    path = tmp_path / f"{name}.musicxml"
    path.write_text(xml, encoding="utf-8")
    r = subprocess.run([XMLLINT, "--noout", "--nonet", "--schema", str(SCHEMA), str(path)],
                       capture_output=True, text=True, timeout=120)
    return [] if r.returncode == 0 else r.stderr.strip().splitlines()[:12]


def from_msn(name: str) -> str:
    score, issues = to_score(parse((HERE / "fixtures" / name).read_text()))
    assert not issues
    return to_musicxml(score)


def test_the_showcase_is_a_playable_piece():
    """The showcase uses every notation feature at once; it should also be
    something a real ensemble could play."""
    assert not validate(parse((HERE / "fixtures" / "showcase.msn").read_text()))
    assert not validate(parse((HERE / "fixtures" / "nocturne.msn").read_text()))


@needs_xmllint
@pytest.mark.parametrize("fixture", ["nocturne.msn", "showcase.msn"])
def test_notation_engraves_to_valid_musicxml(fixture, tmp_path):
    xml = from_msn(fixture)
    assert schema_errors(xml, tmp_path) == []
    again = to_musicxml(read_musicxml(xml))
    assert schema_errors(again, tmp_path, "again") == []


@needs_xmllint
@pytest.mark.parametrize("prompt", [
    "a chopin nocturne", "a haydn string quartet", "a rachmaninoff piano concerto",
    "a bach organ prelude", "a guitar prelude", "a schubert song for voice and piano",
    "a tchaikovsky symphony for orchestra",
])
def test_the_offline_engine_writes_valid_musicxml(prompt, tmp_path):
    assert schema_errors(to_musicxml(compose(parse_prompt(prompt, seed=3))), tmp_path) == []


def test_the_encoding_date_is_written_only_when_it_is_a_date():
    score, _ = to_score(parse((HERE / "fixtures" / "nocturne.msn").read_text()))
    assert "<encoding-date" not in to_musicxml(score)
    score.metadata["date"] = "1835"                 # a composer's year, not a date
    assert "<encoding-date" not in to_musicxml(score)
    score.metadata["date"] = "2026-09-24"
    assert "<encoding-date>2026-09-24</encoding-date>" in to_musicxml(score)


def test_tempo_words_are_spaced_from_the_metronome_mark():
    xml = from_msn("nocturne.msn")
    assert re.search(r'>Lento con gran espressione</words>\s*'
                     r'<words font-weight="normal"> </words>', xml)
    # ...and the space doesn't creep into the marking when the file is read back.
    assert read_musicxml(xml).tempos[0].text == "Lento con gran espressione"
