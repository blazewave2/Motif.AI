"""Convert whatever the corpus contains into Motif's Score model.

Humdrum, MusicXML, MIDI and ABC all go through music21, which is then exported
to MusicXML and read back with Motif's own reader.  Routing everything through
one already-tested parser is worth the extra CPU: the training data ends up in
exactly the representation the runtime uses.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from motif.engrave.musicxml_reader import read_musicxml   # noqa: E402
from motif.score import Score                             # noqa: E402

READABLE = {".krn", ".kern", ".musicxml", ".xml", ".mxl", ".mid", ".midi",
            ".abc", ".rntxt"}

#: Filename fragments that identify a composer, used to tag training examples.
STYLE_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("bach", "chorale", "bwv"), "bach"),
    (("mozart", "kv", "k279", "sonata0"), "mozart"),
    (("beethoven", "op027", "op057", "op013"), "beethoven"),
    (("haydn", "hob"), "haydn"),
    (("chopin", "mazurka", "prelude28", "nocturne"), "chopin"),
    (("scarlatti", "longo", "kirkpatrick"), "scarlatti"),
    (("liszt",), "liszt"),
    (("rachmanin",), "rachmaninoff"),
    (("scriabin", "skryabin"), "scriabin"),
    (("debussy",), "debussy"),
    (("ravel",), "ravel"),
    (("satie", "gymnop"), "satie"),
    (("brahms",), "brahms"),
    (("schubert", "lieder", "d0", "winterreise"), "schubert"),
    (("tchaikovsky", "chaikovsky"), "tchaikovsky"),
    (("mendelssohn",), "mendelssohn"),
    (("grieg",), "grieg"),
    (("handel", "hwv"), "handel"),
    (("vivaldi", "rv0"), "vivaldi"),
    (("clementi",), "clementi"),
    (("joplin", "rag"), "classical"),
]


def guess_style(path: Path, corpus_style: str = "unknown") -> str:
    text = str(path).lower()
    for needles, style in STYLE_HINTS:
        if any(n in text for n in needles):
            return style
    return corpus_style


def load_score(path: Path, max_bars: int = 512) -> Score | None:
    """Parse one file into a Score, or return None if it is unusable."""
    try:
        from music21 import converter
        from music21.musicxml import m21ToXml
    except ImportError as exc:                       # pragma: no cover
        raise SystemExit("music21 is required for data preparation: "
                         "pip install music21") from exc
    try:
        parsed = converter.parse(str(path), forceSource=False)
    except Exception:
        return None
    try:
        if parsed.highestTime <= 0:
            return None
        exporter = m21ToXml.GeneralObjectExporter()
        data = exporter.parse(parsed)
    except Exception:
        return None
    try:
        score = read_musicxml(data)
    except Exception:
        return None
    if score.measure_count == 0 or score.measure_count > max_bars:
        return None
    if not _has_notes(score):
        return None
    return score


def _has_notes(score: Score, minimum: int = 24) -> bool:
    n = 0
    for part in score.parts:
        for m in part.measures:
            for notes in m.voices.values():
                for note in notes:
                    if note.pitches:
                        n += 1
                        if n >= minimum:
                            return True
    return False


def iter_files(root: Path, formats: set[str] | None = None):
    exts = {f".{f.lstrip('.')}" for f in formats} if formats else READABLE
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in exts:
            # Humdrum repos ship analysis spines and incipits alongside scores.
            if any(part in path.parts for part in ("incipit", "harm", "analysis")):
                continue
            yield path
