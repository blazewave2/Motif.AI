"""Motif Score Notation (MSN): the text notation Motif's composer writes in.

A language model writes music far more reliably in a notation with no hidden
state. MSN is built around that: every note carries its own absolute pitch
and its own duration, every bar is numbered, and every voice is on its own
labelled line — so a bar can be checked, reported on and rewritten on its
own, and nothing depends on remembering an accidental from three notes ago.

    title: Nocturne
    key: C# minor
    time: 4/4
    tempo: 56 "Lento con gran espressione"

    m1
      RH: r:h !p (G#4:q. A4:e
      LH: !ped C#2:e G#2:e E3:e G#3:e !ped C#3:e G#2:e E3:e G#2:e
    m2
      RH: G#4:h~ G#4:e F#4:e E4:e D#4:e)
      LH: ...

``SPEC`` in ``spec.py`` is the full reference the composer is given. This
module turns text into a ``MsnPiece`` and reports every problem it finds,
with the bar and voice it was in, rather than guessing silently.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction

from ..theory.pitch import Key, Pitch
from .instruments import INSTRUMENTS, Instrument, PartSpec, instrument

# ---------------------------------------------------------------------------
# vocabulary
# ---------------------------------------------------------------------------
DURATION_LETTERS: dict[str, Fraction] = {
    "b": Fraction(8), "w": Fraction(4), "h": Fraction(2), "q": Fraction(1),
    "e": Fraction(1, 2), "s": Fraction(1, 4), "t": Fraction(1, 8), "x": Fraction(1, 16),
}
DURATION_NUMBERS: dict[str, Fraction] = {
    "1": Fraction(4), "2": Fraction(2), "4": Fraction(1), "8": Fraction(1, 2),
    "16": Fraction(1, 4), "32": Fraction(1, 8), "64": Fraction(1, 16),
}
TYPE_NAMES: dict[Fraction, str] = {
    Fraction(8): "breve", Fraction(4): "whole", Fraction(2): "half",
    Fraction(1): "quarter", Fraction(1, 2): "eighth", Fraction(1, 4): "16th",
    Fraction(1, 8): "32nd", Fraction(1, 16): "64th", Fraction(1, 32): "128th",
}
LETTER_FOR: dict[Fraction, str] = {v: k for k, v in DURATION_LETTERS.items()}

#: Note-attached marks, keyed by every spelling the notation accepts.
MARKS: dict[str, tuple[str, str]] = {
    "stacc": ("art", "staccato"), "staccato": ("art", "staccato"),
    "stacciss": ("art", "staccatissimo"), "staccatissimo": ("art", "staccatissimo"),
    "accent": ("art", "accent"), ">": ("art", "accent"),
    "marc": ("art", "strong-accent"), "marcato": ("art", "strong-accent"),
    "^": ("art", "strong-accent"),
    "ten": ("art", "tenuto"), "tenuto": ("art", "tenuto"),
    "port": ("art", "detached-legato"), "portato": ("art", "detached-legato"),
    "breath": ("art", "breath-mark"),
    "fermata": ("fermata", ""), "ferm": ("fermata", ""),
    "tr": ("orn", "trill-mark"), "trill": ("orn", "trill-mark"),
    "mord": ("orn", "mordent"), "mordent": ("orn", "mordent"),
    "prall": ("orn", "inverted-mordent"), "invmord": ("orn", "inverted-mordent"),
    "turn": ("orn", "turn"), "invturn": ("orn", "inverted-turn"),
    "arp": ("arp", ""), "arpeggio": ("arp", ""),
    "trem": ("trem", "3"), "trem1": ("trem", "1"), "trem2": ("trem", "2"),
    "trem3": ("trem", "3"),
    "upbow": ("tech", "up-bow"), "downbow": ("tech", "down-bow"),
    "harm": ("tech", "harmonic"), "open": ("tech", "open-string"),
    "pizz": ("text", "pizz."), "arco": ("text", "arco"),
    "f1": ("finger", "1"), "f2": ("finger", "2"), "f3": ("finger", "3"),
    "f4": ("finger", "4"), "f5": ("finger", "5"),
}
MARK_NAMES: dict[tuple[str, str], str] = {}
for _name, _val in MARKS.items():
    MARK_NAMES.setdefault(_val, _name)

DYNAMICS = ("pppp", "ppp", "pp", "p", "mp", "mf", "f", "ff", "fff", "ffff",
            "sf", "sfz", "sffz", "sfp", "sfpp", "fp", "fz", "rf", "rfz", "mfp")
HAIRPIN_START = {"cresc": "crescendo", "<": "crescendo", "crescendo": "crescendo",
                 "dim": "diminuendo", "decresc": "diminuendo", ">": "diminuendo",
                 "diminuendo": "diminuendo"}
HAIRPIN_END = {"end", "/", "!", "hairpin_end", "endhairpin"}
PEDAL = {"ped": "down", "pedal": "down", "pedup": "up", "*": "up", "ped_up": "up",
         "pedoff": "up", "ped*": "up"}
#: ``!rit`` and friends are accepted as shorthand for the printed words.
WORD_SHORTCUTS = {"rit": "rit.", "rall": "rall.", "accel": "accel.",
                  "atempo": "a tempo", "a_tempo": "a tempo", "string": "stringendo",
                  "allarg": "allargando", "morendo": "morendo", "smorz": "smorzando",
                  "calando": "calando", "rubato": "rubato", "dolce": "dolce",
                  "espr": "espressivo", "legato": "legato", "subito": "subito"}

KEYBOARD_STAVES = {"RH": 1, "LH": 2, "PED": 3, "UP": 1, "LOW": 2}
HEADER_KEYS = {"title", "subtitle", "composer", "style", "key", "time", "tempo",
               "pickup", "part", "movement", "arranger", "lyricist", "copyright"}
RESERVED_IDS = {"H", "M", "RH", "LH", "PED", "PART", "KEY", "TIME", "TEMPO", "TITLE"}


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------
@dataclass
class Issue:
    """Something wrong with a piece, located as precisely as possible."""

    severity: str                 # "error" must be fixed; "warning" is advisory
    message: str
    measure: int | None = None
    voice: str | None = None
    code: str = "syntax"

    def __str__(self) -> str:
        where = []
        if self.measure is not None:
            where.append(f"m{self.measure}")
        if self.voice:
            where.append(self.voice)
        loc = " ".join(where)
        return f"{loc}: {self.message}" if loc else self.message


@dataclass
class Event:
    """A note, chord or rest in one voice."""

    kind: str                                   # note | rest | spacer | bar_rest
    pitches: list[Pitch] = field(default_factory=list)
    ties: list[bool] = field(default_factory=list)   # per pitch: tied to the next event
    base: Fraction = Fraction(1)                # written value before dots
    dots: int = 0
    tuplet: tuple[int, int] | None = None       # (actual, normal)
    tuplet_start: bool = False
    tuplet_stop: bool = False
    slur_starts: int = 0
    slur_stops: int = 0
    marks: list[str] = field(default_factory=list)   # canonical names from MARKS
    graces: list["Event"] = field(default_factory=list)
    grace_slash: bool = False
    lyric: str | None = None
    source: str = ""
    offset: Fraction = Fraction(0)              # position in the bar, in quarters

    @property
    def written(self) -> Fraction:
        """The value as printed — dots included, tuplet ratio not."""
        total, add = self.base, self.base
        for _ in range(self.dots):
            add /= 2
            total += add
        return total

    @property
    def duration(self) -> Fraction:
        """How long it actually lasts, in quarter notes."""
        if self.tuplet:
            actual, normal = self.tuplet
            return self.written * normal / actual
        return self.written

    @property
    def is_rest(self) -> bool:
        return self.kind in ("rest", "spacer", "bar_rest")

    @property
    def tie_all(self) -> bool:
        return bool(self.ties) and all(self.ties)


@dataclass
class Marking:
    """Something placed at a point in a voice rather than on a note."""

    kind: str          # dynamic | hairpin | hairpin_end | pedal | text
    value: str = ""
    offset: Fraction = Fraction(0)
    placement: str = ""            # "above" | "below" | "" (engraver decides)
    source: str = ""


@dataclass
class VoiceLine:
    label: str
    part: str
    staff: int
    voice: int
    items: list = field(default_factory=list)     # Events and Markings, in order
    line: int = 0

    @property
    def events(self) -> list[Event]:
        return [i for i in self.items if isinstance(i, Event)]

    @property
    def markings(self) -> list[Marking]:
        return [i for i in self.items if isinstance(i, Marking)]

    @property
    def duration(self) -> Fraction:
        return sum((e.duration for e in self.events if e.kind != "bar_rest"),
                   Fraction(0))

    @property
    def has_bar_rest(self) -> bool:
        return any(e.kind == "bar_rest" for e in self.events)


@dataclass
class MsnMeasure:
    number: int
    key: Key | None = None
    time: tuple[int, int] | None = None
    tempo: float | None = None
    tempo_text: str = ""
    texts: list[str] = field(default_factory=list)
    mark: str = ""                                     # rehearsal mark
    clefs: dict[tuple[str, int], str] = field(default_factory=dict)
    barline: str = ""                                  # double | final | dashed
    repeat: str = ""                                   # start | end | both
    ending: int | None = None
    voices: list[VoiceLine] = field(default_factory=list)
    harmony: list[tuple[Fraction, str]] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    line: int = 0

    def voice(self, part: str, staff: int, voice: int) -> VoiceLine | None:
        for v in self.voices:
            if v.part == part and v.staff == staff and v.voice == voice:
                return v
        return None


@dataclass
class MsnPiece:
    title: str = "Untitled"
    subtitle: str = ""
    composer: str = ""
    style: str = ""
    key: Key = field(default_factory=Key)
    time: tuple[int, int] = (4, 4)
    tempo: float = 96.0
    tempo_text: str = ""
    parts: list[PartSpec] = field(default_factory=list)
    measures: list[MsnMeasure] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    def part(self, pid: str) -> PartSpec | None:
        return next((p for p in self.parts if p.id == pid), None)

    def measure(self, number: int) -> MsnMeasure | None:
        return next((m for m in self.measures if m.number == number), None)

    @property
    def numbers(self) -> list[int]:
        return [m.number for m in self.measures]

    @property
    def has_pickup(self) -> bool:
        return bool(self.measures) and self.measures[0].number == 0

    def keyboard_parts(self) -> list[PartSpec]:
        return [p for p in self.parts if p.instrument.keyboard]


# ---------------------------------------------------------------------------
# small parsers
# ---------------------------------------------------------------------------
_PITCH_RE = re.compile(r"^([A-Ga-g])(##|bb|x|#|b|n|♯|♭|♮)?(-?\d{1,2})$")


def parse_pitch(text: str) -> Pitch:
    """``C#4``, ``Bb3``, ``F##5``, ``Ebb2``; middle C is C4."""
    m = _PITCH_RE.match(text.strip())
    if not m:
        raise ValueError(f"not a pitch: {text!r}")
    letter, acc, octave = m.group(1).upper(), m.group(2) or "", int(m.group(3))
    alter = {"": 0, "n": 0, "♮": 0, "#": 1, "♯": 1, "##": 2, "x": 2,
             "b": -1, "♭": -1, "bb": -2}[acc]
    if not -1 <= octave <= 9:
        raise ValueError(f"octave out of range in {text!r}")
    p = Pitch.build(letter, alter, octave)
    if not 0 <= p.midi <= 127:
        raise ValueError(f"pitch out of range: {text!r}")
    return p


def pitch_text(p: Pitch) -> str:
    acc = {0: "", 1: "#", 2: "##", -1: "b", -2: "bb"}.get(p.alter, "")
    return f"{p.step}{acc}{p.octave}"


def parse_key_text(text: str) -> Key:
    """Accept the ways people write keys: "C# minor", "c#m", "E-flat major", "Db"."""
    t = (text or "").strip().strip('"').strip()
    t = t.replace("♯", "#").replace("♭", "b")
    t = re.sub(r"[-\s]+flat\b", "b", t, flags=re.I)
    t = re.sub(r"[-\s]+sharp\b", "#", t, flags=re.I)
    t = re.sub(r"\s+", " ", t)
    m = re.match(r"^([A-Ga-g])(##|bb|#|b)?\s*(.*)$", t)
    if not m:
        raise ValueError(f"unreadable key {text!r}")
    letter, acc, rest = m.group(1), m.group(2) or "", m.group(3).strip().lower()
    if not rest:
        # Lower-case tonic on its own is the German convention for minor.
        rest = "minor" if letter.islower() else "major"
    rest = {"m": "minor", "min": "minor", "maj": "major", "M": "major"}.get(rest, rest)
    return Key.parse(f"{letter.upper()}{acc} {rest}")


def parse_time_text(text: str) -> tuple[int, int]:
    t = (text or "").strip().strip('"')
    if t in ("C", "c", "common"):
        return (4, 4)
    if t in ("C|", "c|", "cut", "alla breve"):
        return (2, 2)
    m = re.match(r"^(\d{1,2})\s*/\s*(\d{1,2})$", t)
    if not m:
        raise ValueError(f"unreadable time signature {text!r}")
    num, den = int(m.group(1)), int(m.group(2))
    if den not in (1, 2, 4, 8, 16, 32) or not 1 <= num <= 32:
        raise ValueError(f"unsupported time signature {text!r}")
    return (num, den)


def bar_length(time: tuple[int, int]) -> Fraction:
    """Length of a full bar, in quarter notes."""
    return Fraction(time[0] * 4, time[1])


def beat_unit(time: tuple[int, int]) -> tuple[Fraction, str, bool]:
    """The felt beat of a metre: (length in quarters, MusicXML type, dotted)."""
    num, den = time
    if den == 8 and num % 3 == 0 and num >= 6:
        return Fraction(3, 2), "quarter", True
    if den == 2:
        return Fraction(2), "half", False
    if den == 8:
        return Fraction(1, 2), "eighth", False
    if den == 16:
        return Fraction(1, 4), "16th", False
    return Fraction(1), "quarter", False


def parse_duration(code: str) -> tuple[Fraction, int]:
    """``q`` -> (1, 0); ``e.`` -> (1/2, 1); ``8`` -> (1/2, 0)."""
    code = code.strip()
    dots = len(code) - len(code.rstrip("."))
    core = code[:len(code) - dots] if dots else code
    if core in DURATION_LETTERS:
        return DURATION_LETTERS[core], dots
    if core in DURATION_NUMBERS:
        return DURATION_NUMBERS[core], dots
    raise ValueError(f"unknown duration {code!r}")


def duration_code(base: Fraction, dots: int = 0) -> str:
    return LETTER_FOR[base] + "." * dots


def split_quarters(value: Fraction) -> list[tuple[Fraction, int]]:
    """Express a length as notatable (base, dots) values, longest first."""
    out: list[tuple[Fraction, int]] = []
    remaining = value
    bases = sorted(DURATION_LETTERS.values(), reverse=True)
    guard = 0
    while remaining > 0 and guard < 32:
        guard += 1
        best: tuple[Fraction, int] | None = None
        for b in bases:
            for dots in (2, 1, 0):
                total, add = b, b
                for _ in range(dots):
                    add /= 2
                    total += add
                if total <= remaining and (best is None or total > _dotted(*best)):
                    best = (b, dots)
        if best is None:
            break
        out.append(best)
        remaining -= _dotted(*best)
    return out


def _dotted(base: Fraction, dots: int) -> Fraction:
    total, add = base, base
    for _ in range(dots):
        add /= 2
        total += add
    return total


def default_tuplet_normal(actual: int) -> int:
    if actual == 2:
        return 3
    if actual == 4:
        return 3
    n = 1
    while n * 2 < actual:
        n *= 2
    return n


# ---------------------------------------------------------------------------
# tokenising a line
# ---------------------------------------------------------------------------
def split_attrs(text: str) -> list[str]:
    """Whitespace-split, keeping "quoted strings" (with spaces) whole."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        j = i
        while j < n and not text[j].isspace():
            if text[j] == '"':
                k = text.find('"', j + 1)
                j = n if k < 0 else k + 1
                continue
            j += 1
        out.append(text[i:j])
        i = j
    return out


def _item_tokens(text: str) -> list[str]:
    """Split a voice line into items, pulling brackets and braces apart."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace() or c == "|":
            i += 1
            continue
        if c in "{}()":
            out.append(c)
            i += 1
            continue
        if c in "^_" and i + 1 < n and text[i + 1] == '"':
            k = text.find('"', i + 2)
            k = n - 1 if k < 0 else k
            out.append(text[i:k + 1])
            i = k + 1
            continue
        if c == '"':
            k = text.find('"', i + 1)
            k = n - 1 if k < 0 else k
            out.append(text[i:k + 1])
            i = k + 1
            continue
        j = i
        if c == "[":
            k = text.find("]", i)
            j = n if k < 0 else k + 1
        while j < n and not text[j].isspace() and text[j] not in "{}()|":
            if text[j] == '"':                        # a lyric: @"text"
                k = text.find('"', j + 1)
                j = n if k < 0 else k + 1
                continue
            if text[j] == "[":
                break
            j += 1
        out.append(text[i:j])
        i = j
    return out


_EVENT_RE = re.compile(
    r"^(?P<head>\[[^\]]*\]|[A-Ga-g](?:##|bb|x|#|b|n|♯|♭)?-?\d{1,2}~?|[rRsS_])"
    r"(?:~)?(?::(?P<dur>b|w|h|q|e|s|t|x|64|32|16|8|4|2|1)(?P<dots>\.{0,3}))?"
    r"(?P<rest>.*)$")


# ---------------------------------------------------------------------------
# the parser
# ---------------------------------------------------------------------------
class _Reader:
    def __init__(self, text: str, *, default_part: str = "Pno"):
        self.lines = text.splitlines()
        self.piece = MsnPiece()
        self.default_part = default_part
        self.saw_measure = False
        self.cur: MsnMeasure | None = None
        self.pending_comments: list[str] = []
        self.last_event: dict[str, Event] = {}          # voice key -> last real event
        self.last_duration: dict[str, tuple[Fraction, int]] = {}
        self.slur_depth: dict[str, int] = {}

    # -- issues ------------------------------------------------------------
    def err(self, msg: str, measure=None, voice=None, code="syntax") -> None:
        self.piece.issues.append(Issue("error", msg, measure, voice, code))

    def warn(self, msg: str, measure=None, voice=None, code="syntax") -> None:
        self.piece.issues.append(Issue("warning", msg, measure, voice, code))

    # -- driver ------------------------------------------------------------
    def run(self) -> MsnPiece:
        for idx, raw in enumerate(self.lines, start=1):
            stripped = raw.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                continue
            line, comment = _split_comment(raw)
            if not line.strip():
                if comment:
                    self.pending_comments.append(comment)
                continue
            self._line(line.strip(), idx, comment)
        self._finish()
        return self.piece

    def _line(self, line: str, idx: int, comment: str = "") -> None:
        m = re.match(r"^(?:[mM]|bar\s+|measure\s+)(\d{1,4})(?=$|[\s:|])\s*:?\s*\|?\s*(.*)$",
                     line)
        if m:
            self._measure(int(m.group(1)), m.group(2), idx)
            if comment and self.cur is not None:
                self.cur.comments.append(comment)
            return
        h = re.match(r"^([A-Za-z_]+)\s*:\s*(.*)$", line)
        if h and h.group(1).lower() in HEADER_KEYS and not self.saw_measure:
            self._header(h.group(1).lower(), h.group(2).strip(), idx)
            return
        v = re.match(r"^([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9]*)?)\s*:\s*(.*)$", line)
        if v:
            label = v.group(1)
            if self.cur is None:
                self.err(f"line {idx}: '{label}:' appears before any bar (write m1 first)")
                return
            if label in ("H", "h", "Harmony", "harmony", "HARM"):
                self._harmony(v.group(2), idx)
            elif label.lower() in HEADER_KEYS:
                self.err(f"'{label}:' cannot change mid-piece; put it on the bar line "
                         f"instead, e.g. m{self.cur.number} {label.lower()}=...",
                         self.cur.number)
            else:
                self._voice(label, v.group(2), idx)
            return
        self.err(f"line {idx}: could not read {line[:60]!r}",
                 self.cur.number if self.cur else None)

    # -- header ------------------------------------------------------------
    def _header(self, key: str, value: str, idx: int) -> None:
        p = self.piece
        try:
            if key == "title":
                p.title = value.strip('"') or p.title
            elif key == "subtitle":
                p.subtitle = value.strip('"')
            elif key == "composer":
                p.composer = value.strip('"')
            elif key == "style":
                p.style = value.strip('"')
            elif key == "key":
                p.key = parse_key_text(value)
            elif key == "time":
                p.time = parse_time_text(value)
            elif key == "tempo":
                bpm, text = _tempo_value(value)
                if bpm:
                    p.tempo = bpm
                p.tempo_text = text
            elif key == "part":
                self._part(value, idx)
            else:
                p.meta[key] = value.strip('"')
        except ValueError as exc:
            self.err(f"header '{key}': {exc}")

    def _part(self, value: str, idx: int) -> None:
        toks = split_attrs(value.replace("=", " "))
        if not toks:
            self.err(f"line {idx}: empty part declaration")
            return
        pid = toks[0].strip('"')
        if (not re.match(r"^[A-Za-z][A-Za-z0-9_]{0,11}$", pid) or pid.upper() in RESERVED_IDS
                or re.match(r"^[mM]\d+$", pid)
                or re.match(r"^(RH|LH|PED|UP|LOW)\d*$", pid, re.I)):
            self.err(f"part id {pid!r} must be a short name like Vn1, Vla or Pno "
                     f"(letters and digits, not RH/LH/H)")
            return
        if self.piece.part(pid):
            self.err(f"part {pid!r} is declared twice")
            return
        name = ""
        inst: Instrument | None = None
        for t in toks[1:]:
            if t.startswith('"'):
                name = t.strip('"')
            elif inst is None:
                inst = instrument(t)
                if inst is None:
                    self.err(f"part {pid}: unknown instrument {t!r}")
                    return
        inst = inst or instrument(name) or instrument(pid)
        if inst is None:
            self.err(f"part {pid}: say which instrument it is, e.g. 'part: {pid} violin'")
            return
        self.piece.parts.append(PartSpec(pid, inst, name))

    # -- measures ------------------------------------------------------------
    def _measure(self, number: int, rest: str, idx: int) -> None:
        self.saw_measure = True
        m = MsnMeasure(number=number, line=idx, comments=self.pending_comments)
        self.pending_comments = []
        self.cur = m
        self.piece.measures.append(m)
        toks = split_attrs(rest)
        i = 0
        while i < len(toks):
            tok = toks[i]
            i += 1
            if tok.startswith('"'):
                m.texts.append(tok.strip('"'))
                continue
            if "=" not in tok:
                self.warn(f"ignored {tok!r} after the bar number", number)
                continue
            raw_name, value = tok.split("=", 1)
            raw_name = raw_name.strip()
            name = raw_name.lower()
            value = value.strip()
            try:
                if name == "key":
                    m.key = parse_key_text(value)
                elif name == "time":
                    m.time = parse_time_text(value)
                elif name == "tempo":
                    bpm, text = _tempo_value(value)
                    if i < len(toks) and toks[i].startswith('"'):
                        text = toks[i].strip('"')
                        i += 1
                    if bpm is None and not text:
                        raise ValueError("tempo needs a number, e.g. tempo=72")
                    m.tempo = bpm
                    m.tempo_text = text
                elif name in ("text", "expr", "expression"):
                    m.texts.append(value.strip('"'))
                elif name in ("mark", "rehearsal", "section"):
                    m.mark = value.strip('"')
                elif name.startswith("clef"):
                    self._clef(m, raw_name, value)
                elif name == "barline":
                    m.barline = {"||": "double", "|.": "final", "double": "double",
                                 "final": "final", "end": "final", "dashed": "dashed",
                                 ":": "dashed"}.get(value.strip('"'), "")
                    if not m.barline:
                        raise ValueError(f"unknown barline {value!r}")
                elif name == "repeat":
                    v = value.strip('"').lower()
                    if v not in ("start", "end", "both"):
                        raise ValueError("repeat must be start, end or both")
                    m.repeat = v
                elif name == "ending":
                    m.ending = int(value.strip('"'))
                else:
                    self.warn(f"unknown bar attribute {name!r}", number)
            except ValueError as exc:
                self.err(str(exc), number)

    def _clef(self, m: MsnMeasure, name: str, value: str) -> None:
        # clef.LH=treble, clef.Pno.LH=treble, clef.Vla=treble
        target = name.split(".", 1)[1] if "." in name else "LH"
        clef = {"treble": "G", "g": "G", "bass": "F", "f": "F", "alto": "C",
                "c": "C", "tenor": "tenor", "treble8vb": "G8vb", "g8vb": "G8vb",
                "percussion": "percussion"}.get(value.strip('"').lower())
        if clef is None:
            raise ValueError(f"unknown clef {value!r} (treble, bass, alto, tenor)")
        part, staff, _ = self._resolve_label(target, quiet=True, measure=m.number)
        if part is None:
            # Be forgiving about case: clef.lh=treble, clef.vla=treble.
            for p in self.piece.parts:
                if p.id.lower() == target.lower() and p.staves == 1:
                    part, staff = p.id, 1
            if part is None:
                pid, _, staff_name = target.rpartition(".")
                fixed = (f"{pid}." if pid else "") + staff_name.upper()
                for p in self.piece.parts:
                    if pid and p.id.lower() == pid.lower():
                        fixed = f"{p.id}.{staff_name.upper()}"
                part, staff, _ = self._resolve_label(fixed, quiet=True, measure=m.number)
        if part is None:
            raise ValueError(f"clef change for unknown staff {target!r}")
        m.clefs[(part, staff)] = clef

    # -- labels ------------------------------------------------------------
    def _ensure_default_part(self) -> None:
        if not self.piece.parts:
            self.piece.parts.append(PartSpec(self.default_part, INSTRUMENTS["piano"]))

    def _resolve_label(self, label: str, *, quiet: bool = False,
                       measure: int | None = None) -> tuple[str | None, int, int]:
        """``RH2`` -> (piano id, staff 1, voice 2); ``Vn1`` -> ("Vn1", 1, 1)."""
        self._ensure_default_part()
        parts = self.piece.parts
        # A single-staff part named directly.
        for p in parts:
            if label == p.id:
                if p.staves == 1:
                    return p.id, 1, 1
                if not quiet:
                    self.err(f"{label} has {p.staves} staves; write {label}.RH / {label}.LH",
                             measure, label)
                return None, 0, 0
        m = re.match(r"^(?:([A-Za-z][A-Za-z0-9_]*)\.)?(RH|LH|Ped|PED|UP|LOW|rh|lh)(\d)?$", label)
        if m:
            pid, staff_name, vnum = m.group(1), m.group(2).upper(), m.group(3)
            staff = KEYBOARD_STAVES[staff_name]
            voice = int(vnum) if vnum else 1
            if not 1 <= voice <= 4:
                if not quiet:
                    self.err(f"voice {label}: at most four voices per staff", measure, label)
                return None, 0, 0
            if pid:
                p = self.piece.part(pid)
                if p is None:
                    if not quiet:
                        self.err(f"unknown part {pid!r}", measure, label)
                    return None, 0, 0
            else:
                kb = [p for p in parts if p.staves >= 2]
                if len(kb) != 1:
                    if not quiet:
                        self.err(f"{label} is ambiguous: prefix it with the part id "
                                 f"({', '.join(p.id for p in kb) or 'no keyboard part declared'})",
                                 measure, label)
                    return None, 0, 0
                p = kb[0]
            if staff > p.staves:
                if not quiet:
                    self.err(f"{p.display_name} has no {staff_name} staff", measure, label)
                return None, 0, 0
            return p.id, staff, voice
        if not quiet:
            known = ", ".join(p.id for p in parts)
            self.err(f"unknown voice label {label!r} (parts: {known})", measure, label)
        return None, 0, 0

    # -- harmony -----------------------------------------------------------
    def _harmony(self, text: str, idx: int) -> None:
        m = self.cur
        toks = [t for t in split_attrs(text) if t not in ("|",)]
        entries: list[tuple[str, Fraction | None]] = []
        for t in toks:
            if ":" in t and not t.startswith(":"):
                sym, _, dur = t.rpartition(":")
                try:
                    base, dots = parse_duration(dur)
                    entries.append((sym, _dotted(base, dots)))
                except ValueError:
                    entries.append((t, None))
            else:
                entries.append((t, None))
        if not entries:
            return
        pos = Fraction(0)
        undated = [e for e in entries if e[1] is None]
        span = None
        if undated:
            bar = bar_length(self._time_at(m))
            known = sum((d for _, d in entries if d is not None), Fraction(0))
            span = max(Fraction(0), bar - known) / len(undated)
        for sym, dur in entries:
            m.harmony.append((pos, sym))
            pos += dur if dur is not None else (span or Fraction(0))

    def _time_at(self, measure: MsnMeasure) -> tuple[int, int]:
        t = self.piece.time
        for mm in self.piece.measures:
            if mm.time:
                t = mm.time
            if mm is measure:
                break
        return t

    # -- voices ------------------------------------------------------------
    def _voice(self, label: str, text: str, idx: int) -> None:
        m = self.cur
        part, staff, voice = self._resolve_label(label, measure=m.number)
        if part is None:
            return
        if m.voice(part, staff, voice) is not None:
            self.err(f"{label} is written twice in this bar", m.number, label)
            return
        vl = VoiceLine(label=label, part=part, staff=staff, voice=voice, line=idx)
        m.voices.append(vl)
        vkey = f"{part}/{staff}/{voice}"
        self._items(vl, _item_tokens(text), m.number, vkey)
        pos = Fraction(0)
        for it in vl.items:
            if isinstance(it, Event):
                it.offset = pos
                if it.kind != "bar_rest":
                    pos += it.duration
            else:
                it.offset = pos

    def _items(self, vl: VoiceLine, toks: list[str], mnum: int, vkey: str) -> None:
        label = vl.label
        i = 0
        tuplet: tuple[int, int] | None = None
        tuplet_events: list[Event] = []
        grace_mode: str | None = None               # "acc" | "app" | "g"
        graces: list[Event] = []
        pending_graces: list[Event] = []
        pending_slash = False
        pending_slurs = 0
        depth_stack: list[str] = []                  # "tuplet" | "grace"

        def attach(ev: Event) -> None:
            nonlocal pending_graces, pending_slash, pending_slurs
            if pending_graces:
                ev.graces = pending_graces
                ev.grace_slash = pending_slash
                pending_graces = []
                pending_slash = False
            if pending_slurs:
                ev.slur_starts += pending_slurs
                self.slur_depth[vkey] = self.slur_depth.get(vkey, 0) + pending_slurs
                pending_slurs = 0
            vl.items.append(ev)
            if not ev.is_rest:
                self.last_event[vkey] = ev
            if tuplet is not None:
                ev.tuplet = tuplet
                tuplet_events.append(ev)

        while i < len(toks):
            tok = toks[i]
            i += 1
            if tok == "(":
                pending_slurs += 1
                continue
            if tok == ")":
                target = self.last_event.get(vkey)
                if graces and grace_mode is not None:
                    target = graces[-1]
                if target is None:
                    self.warn("slur closed with nothing before it", mnum, label)
                elif self.slur_depth.get(vkey, 0) <= 0:
                    self.warn("')' closes a slur that was never opened", mnum, label)
                else:
                    target.slur_stops += 1
                    self.slur_depth[vkey] -= 1
                continue
            if tok == "{":
                head = toks[i] if i < len(toks) else ""
                tm = re.match(r"^(\d{1,2})(?::(\d{1,2}))?:?$", head)
                if tm:
                    i += 1
                    if tuplet is not None:
                        self.err("tuplets cannot be nested", mnum, label)
                        depth_stack.append("bad")
                        continue
                    actual = int(tm.group(1))
                    normal = int(tm.group(2)) if tm.group(2) else default_tuplet_normal(actual)
                    if actual < 2 or normal < 1:
                        self.err(f"bad tuplet ratio {head!r}", mnum, label)
                    tuplet = (actual, normal)
                    tuplet_events = []
                    depth_stack.append("tuplet")
                    continue
                gm = head.lower().rstrip(":")
                if gm in ("acc", "app", "g", "grace", "gr"):
                    i += 1
                    grace_mode = {"grace": "g", "gr": "g"}.get(gm, gm)
                    graces = []
                    depth_stack.append("grace")
                    continue
                self.err(f"'{{' must be followed by a tuplet number ({{3 ...}}) or "
                         f"acc/app/g for grace notes, found {head!r}", mnum, label)
                depth_stack.append("bad")
                continue
            if tok == "}":
                kind = depth_stack.pop() if depth_stack else None
                if kind == "tuplet":
                    if tuplet_events:
                        tuplet_events[0].tuplet_start = True
                        tuplet_events[-1].tuplet_stop = True
                    else:
                        self.warn("empty tuplet", mnum, label)
                    tuplet = None
                    tuplet_events = []
                elif kind == "grace":
                    if not graces:
                        self.warn("empty grace-note group", mnum, label)
                    pending_graces = graces
                    pending_slash = grace_mode == "acc"
                    graces = []
                    grace_mode = None
                elif kind is None:
                    self.err("'}' without a matching '{'", mnum, label)
                continue
            if tok.startswith("!"):
                self._direction(vl, tok[1:], mnum, label)
                continue
            if tok.startswith('"') or tok[:2] in ('^"', '_"'):
                placement = {"^": "above", "_": "below"}.get(tok[0], "")
                text = tok.lstrip("^_").strip('"').strip()
                if text:
                    vl.items.append(Marking("text", text, placement=placement, source=tok))
                continue
            ev = self._event(tok, mnum, label, vkey,
                             grace_default=({"app": Fraction(1, 2)}.get(grace_mode, Fraction(1, 4))
                                            if grace_mode is not None else None))
            if ev is None:
                continue
            if grace_mode is not None:
                if ev.is_rest:
                    self.warn("rests are not allowed as grace notes", mnum, label)
                    continue
                graces.append(ev)
                continue
            if (ev.kind == "bar_rest" and (tuplet is not None or vl.events)) or \
                    (ev.kind != "bar_rest" and vl.has_bar_rest):
                self.err("R (a whole-bar rest) must be the only thing in its voice",
                         mnum, label, "duration")
                continue
            attach(ev)

        if tuplet is not None:
            self.err("tuplet opened with '{' but never closed with '}'", mnum, label)
            if tuplet_events:
                tuplet_events[0].tuplet_start = True
                tuplet_events[-1].tuplet_stop = True
        if grace_mode is not None:
            self.err("grace-note group never closed with '}'", mnum, label)
        if pending_graces:
            self.warn("grace notes at the end of a bar have no note to lead into",
                      mnum, label)
        if pending_slurs:
            self.warn("'(' at the end of a line opens a slur on nothing", mnum, label)

    def _event(self, tok: str, mnum: int, label: str, vkey: str,
               grace_default: Fraction | None = None) -> Event | None:
        m = _EVENT_RE.match(tok)
        if not m:
            self.err(f"could not read {tok!r}", mnum, label)
            return None
        head, dur, dots, rest = m.group("head"), m.group("dur"), m.group("dots"), m.group("rest")
        ev = Event(kind="note", source=tok)
        tie_all = False
        if head.endswith("~") and not head.startswith("["):
            head = head[:-1]
            tie_all = True
        if head in ("R",):
            ev.kind = "bar_rest"
            return ev
        if head in ("r",):
            ev.kind = "rest"
        elif head in ("s", "S", "_"):
            ev.kind = "spacer"
        elif head.startswith("["):
            inner = head[1:-1].replace(",", " ").split()
            if not inner:
                self.err(f"empty chord {tok!r}", mnum, label)
                return None
            for ptxt in inner:
                tied = ptxt.endswith("~")
                ptxt = ptxt.rstrip("~")
                try:
                    p = parse_pitch(ptxt)
                except ValueError as exc:
                    self.err(f"{exc} in {tok!r}", mnum, label)
                    return None
                ev.pitches.append(p)
                ev.ties.append(tied)
            order = sorted(range(len(ev.pitches)), key=lambda k: ev.pitches[k].midi)
            ev.pitches = [ev.pitches[k] for k in order]
            ev.ties = [ev.ties[k] for k in order]
            seen = set()
            uniq_p, uniq_t = [], []
            for p, t in zip(ev.pitches, ev.ties):
                if p.midi in seen:
                    continue
                seen.add(p.midi)
                uniq_p.append(p)
                uniq_t.append(t)
            ev.pitches, ev.ties = uniq_p, uniq_t
        else:
            try:
                ev.pitches = [parse_pitch(head)]
                ev.ties = [False]
            except ValueError as exc:
                self.err(f"{exc}", mnum, label)
                return None

        if dur is None and grace_default is not None:
            ev.base, ev.dots = grace_default, 0
        elif dur is None:
            prev = self.last_duration.get(vkey)
            if prev is None:
                self.err(f"{tok!r} has no duration (write e.g. {head}:q)", mnum, label,
                         "duration")
                return None
            ev.base, ev.dots = prev
            self.warn(f"{tok!r} has no duration; assumed the previous one", mnum, label)
        else:
            try:
                ev.base, ev.dots = parse_duration(dur + (dots or ""))
            except ValueError as exc:
                self.err(f"{exc} in {tok!r}", mnum, label)
                return None
            if grace_default is None:
                self.last_duration[vkey] = (ev.base, ev.dots)

        # Modifiers: ~ tie, +mark, @"lyric", trailing dots misplaced after marks.
        rest = rest or ""
        while rest:
            if rest.startswith("~"):
                tie_all = True
                rest = rest[1:]
                continue
            if rest.startswith("+"):
                mm = re.match(r"^\+([A-Za-z0-9_^>*]+|\^|>)", rest)
                if not mm:
                    self.err(f"bad mark in {tok!r}", mnum, label)
                    break
                name = mm.group(1).lower()
                if name in DYNAMICS:
                    ev.marks.append(f"dyn:{name}")
                elif name in MARKS:
                    ev.marks.append(name if name in ("arp", "fermata") else
                                    MARK_NAMES[MARKS[name]])
                else:
                    self.warn(f"unknown mark +{name} ignored", mnum, label)
                rest = rest[mm.end():]
                continue
            if rest.startswith("@"):
                lm = re.match(r'^@"([^"]*)"?', rest)
                if lm:
                    ev.lyric = lm.group(1)
                    rest = rest[lm.end():]
                    continue
            if rest.startswith("."):
                self.err(f"dots belong straight after the duration in {tok!r}",
                         mnum, label, "duration")
                rest = rest.lstrip(".")
                continue
            self.err(f"could not read {rest!r} in {tok!r}", mnum, label)
            break
        if tie_all and ev.pitches:
            ev.ties = [True] * len(ev.pitches)
        if ev.is_rest:
            ev.ties = []
        return ev

    def _direction(self, vl: VoiceLine, body: str, mnum: int, label: str) -> None:
        b = body.strip()
        low = b.lower()
        if low in DYNAMICS:
            vl.items.append(Marking("dynamic", low, source="!" + b))
        elif low in HAIRPIN_START or b in HAIRPIN_START:
            vl.items.append(Marking("hairpin", HAIRPIN_START.get(low, HAIRPIN_START.get(b)),
                                    source="!" + b))
        elif low in HAIRPIN_END or b in HAIRPIN_END:
            vl.items.append(Marking("hairpin_end", "", source="!" + b))
        elif low in PEDAL:
            vl.items.append(Marking("pedal", PEDAL[low], source="!" + b))
        elif low in WORD_SHORTCUTS:
            vl.items.append(Marking("text", WORD_SHORTCUTS[low], source="!" + b))
        elif low.startswith("tempo="):
            self.warn("write tempo changes on the bar line (m12 tempo=80)", mnum, label)
        else:
            self.err(f"unknown direction '!{b}'", mnum, label)

    # -- whole-piece checks after reading -----------------------------------
    def _finish(self) -> None:
        p = self.piece
        self._ensure_default_part()
        seen: set[int] = set()
        for m in p.measures:
            if m.number in seen:
                self.err(f"bar m{m.number} is written twice", m.number, code="numbering")
            seen.add(m.number)
        _resolve_ties(p)
        for vkey, depth in self.slur_depth.items():
            if depth > 0:
                last = self.last_event.get(vkey)
                if last is not None:
                    last.slur_stops += depth
                    self.warn(f"{depth} slur(s) left open were closed at the last note",
                              code="slur")


def _resolve_ties(piece: MsnPiece) -> None:
    """A tie needs the same pitch next in the same voice; drop any that don't."""
    last: dict[tuple[str, int, int], Event] = {}
    for m in piece.measures:
        for vl in m.voices:
            key = (vl.part, vl.staff, vl.voice)
            for ev in vl.events:
                prev = last.get(key)
                if prev is not None and any(prev.ties):
                    targets = {p.midi for p in ev.pitches}
                    for k, p in enumerate(prev.pitches):
                        if prev.ties[k] and p.midi not in targets:
                            prev.ties[k] = False
                            piece.issues.append(Issue(
                                "warning", f"tie from {pitch_text(p)} has no matching "
                                f"note after it; removed", m.number, vl.label, "tie"))
                if not ev.is_rest or ev.kind == "bar_rest":
                    last[key] = ev
                elif ev.kind in ("rest", "spacer"):
                    if prev is not None and any(prev.ties):
                        prev.ties = [False] * len(prev.ties)
                    last[key] = ev
    for ev in last.values():
        if any(ev.ties):
            ev.ties = [False] * len(ev.ties)


def _split_comment(raw: str) -> tuple[str, str]:
    """Separate a line from its '# comment' (a '#' after whitespace, outside quotes)."""
    s = raw.rstrip("\n")
    lead = s.lstrip()
    if lead.startswith("#") or lead.startswith("//"):
        return "", lead.lstrip("#/ ").strip()
    in_q = False
    for i, c in enumerate(s):
        if c == '"':
            in_q = not in_q
        if in_q:
            continue
        if (c == "#" or s[i:i + 2] == "//") and i > 0 and s[i - 1].isspace():
            return s[:i], s[i:].lstrip("#/ ").strip()
    return s, ""


def _tempo_value(value: str) -> tuple[float | None, str]:
    """``56``, ``56 "Lento"``, ``Lento (56)``, ``"Allegro"`` -> (bpm, text)."""
    v = value.strip()
    text = ""
    q = re.search(r'"([^"]*)"', v)
    if q:
        text = q.group(1).strip()
        v = (v[:q.start()] + v[q.end():]).strip()
    num = re.search(r"(\d{2,3}(?:\.\d+)?)", v)
    bpm = float(num.group(1)) if num else None
    if not text:
        leftover = re.sub(r"[\d.()=♩]+", " ", v).strip(" ,;-")
        if leftover:
            text = leftover
    if bpm is not None and not 20 <= bpm <= 300:
        raise ValueError(f"tempo {bpm:g} is outside 20-300")
    return bpm, text


def parse(text: str, *, default_part: str = "Pno") -> MsnPiece:
    """Read MSN text. Never raises: problems are listed in ``piece.issues``."""
    return _Reader(text or "", default_part=default_part).run()


def parse_measures(text: str, context: MsnPiece) -> MsnPiece:
    """Read a passage of bars written against an existing piece's header.

    The composer writes a section at a time; those bars carry no header of
    their own, so the piece they belong to supplies the parts and metre.
    """
    header = render_header(context)
    piece = parse(header + "\n" + (text or ""))
    return piece


# ---------------------------------------------------------------------------
# writing MSN back out
# ---------------------------------------------------------------------------
def render_header(piece: MsnPiece) -> str:
    lines = [f"title: {piece.title}"]
    if piece.subtitle:
        lines.append(f"subtitle: {piece.subtitle}")
    if piece.composer:
        lines.append(f"composer: {piece.composer}")
    if piece.style:
        lines.append(f"style: {piece.style}")
    lines.append(f"key: {key_text(piece.key)}")
    lines.append(f"time: {piece.time[0]}/{piece.time[1]}")
    tempo = f"tempo: {piece.tempo:g}"
    if piece.tempo_text:
        tempo += f' "{piece.tempo_text}"'
    lines.append(tempo)
    for p in piece.parts:
        name = f' "{p.name}"' if p.name and p.name != p.instrument.name else ""
        lines.append(f"part: {p.id} {p.instrument.key}{name}")
    return "\n".join(lines)


def key_text(k: Key) -> str:
    mode = "minor" if k.mode in ("minor", "natural_minor") else k.mode.replace("_", " ")
    return f"{k.tonic} {mode}"


def render_event(ev: Event) -> str:
    if ev.kind == "bar_rest":
        return "R"
    if ev.kind == "rest":
        head = "r"
    elif ev.kind == "spacer":
        head = "s"
    elif len(ev.pitches) == 1:
        head = pitch_text(ev.pitches[0])
    else:
        mixed = any(ev.ties) and not all(ev.ties)
        head = "[" + " ".join(pitch_text(p) + ("~" if mixed and t else "")
                              for p, t in zip(ev.pitches, ev.ties)) + "]"
    out = head + ":" + duration_code(ev.base, ev.dots)
    if ev.pitches and ev.ties and all(ev.ties):
        out += "~"
    for mk in ev.marks:
        out += "+" + (mk[4:] if mk.startswith("dyn:") else mk)
    if ev.lyric:
        out += f'@"{ev.lyric}"'
    return out


def render_voice_items(vl: VoiceLine) -> str:
    parts: list[str] = []
    open_tuplet = False
    for it in vl.items:
        if isinstance(it, Marking):
            parts.append(_render_marking(it))
            continue
        ev = it
        if ev.graces:
            kind = "acc" if ev.grace_slash else ("app" if len(ev.graces) == 1 else "g")
            parts.append("{" + kind + " " + " ".join(render_event(g) for g in ev.graces) + "}")
        if ev.tuplet and ev.tuplet_start and not open_tuplet:
            actual, normal = ev.tuplet
            ratio = str(actual) if normal == default_tuplet_normal(actual) else f"{actual}:{normal}"
            parts.append("{" + ratio)
            open_tuplet = True
        tok = render_event(ev)
        tok = "(" * ev.slur_starts + tok + ")" * ev.slur_stops
        parts.append(tok)
        if ev.tuplet and ev.tuplet_stop and open_tuplet:
            parts[-1] = parts[-1] + "}"
            open_tuplet = False
    if open_tuplet:
        parts[-1] = parts[-1] + "}"
    return " ".join(parts)


def _render_marking(mk: Marking) -> str:
    if mk.kind == "dynamic":
        return "!" + mk.value
    if mk.kind == "hairpin":
        return "!cresc" if mk.value == "crescendo" else "!dim"
    if mk.kind == "hairpin_end":
        return "!end"
    if mk.kind == "pedal":
        return "!ped" if mk.value == "down" else "!pedup"
    prefix = {"above": "^", "below": "_"}.get(mk.placement, "")
    return f'{prefix}"{mk.value}"'


def label_for(piece: MsnPiece, part: str, staff: int, voice: int) -> str:
    p = piece.part(part)
    if p is None or p.staves == 1:
        return part
    staff_name = {1: "RH", 2: "LH", 3: "Ped"}.get(staff, "RH")
    several = len([q for q in piece.parts if q.staves >= 2]) > 1
    return f"{part + '.' if several else ''}{staff_name}{voice if voice > 1 else ''}"


def time_at(piece: MsnPiece, number: int) -> tuple[int, int]:
    """The metre in force at bar ``number``."""
    t = piece.time
    for mm in piece.measures:
        if mm.number > number:
            break
        if mm.time:
            t = mm.time
    return t


def key_at(piece: MsnPiece, number: int) -> Key:
    k = piece.key
    for mm in piece.measures:
        if mm.number > number:
            break
        if mm.key is not None:
            k = mm.key
    return k


def render_measure(piece: MsnPiece, m: MsnMeasure,
                   time: tuple[int, int] | None = None) -> str:
    time = time or time_at(piece, m.number)
    head = [f"m{m.number}"]
    if m.key is not None:
        head.append(f'key="{key_text(m.key)}"')
    if m.time is not None:
        head.append(f"time={m.time[0]}/{m.time[1]}")
    if m.tempo is not None:
        head.append(f"tempo={m.tempo:g}" + (f' "{m.tempo_text}"' if m.tempo_text else ""))
    elif m.tempo_text:
        head.append(f'tempo="{m.tempo_text}"')
    if m.mark:
        head.append(f'mark="{m.mark}"')
    for (part, staff), clef in m.clefs.items():
        name = {"G": "treble", "F": "bass", "C": "alto", "tenor": "tenor",
                "G8vb": "treble8vb"}.get(clef, clef)
        head.append(f"clef.{label_for(piece, part, staff, 1)}={name}")
    if m.barline:
        head.append(f"barline={m.barline}")
    if m.repeat:
        head.append(f"repeat={m.repeat}")
    if m.ending:
        head.append(f"ending={m.ending}")
    for t in m.texts:
        head.append(f'text="{t}"')
    lines = [f"# {c}" for c in m.comments if c]
    lines.append(" ".join(head))
    order = {p.id: i for i, p in enumerate(piece.parts)}
    for vl in sorted(m.voices, key=lambda v: (order.get(v.part, 99), v.staff, v.voice)):
        lines.append(f"  {label_for(piece, vl.part, vl.staff, vl.voice)}: "
                     f"{render_voice_items(vl)}")
    if m.harmony:
        bar = bar_length(time)
        toks = []
        for i, (off, sym) in enumerate(m.harmony):
            end = m.harmony[i + 1][0] if i + 1 < len(m.harmony) else bar
            pieces = split_quarters(end - off) if end > off else []
            toks.append(f"{sym}:{duration_code(*pieces[0])}" if len(pieces) == 1 else sym)
        lines.append("  H: " + " ".join(toks))
    return "\n".join(lines)


def render(piece: MsnPiece, *, measures: list[MsnMeasure] | None = None,
           header: bool = True) -> str:
    chunks = [render_header(piece)] if header else []
    for m in (measures if measures is not None else piece.measures):
        chunks.append(render_measure(piece, m, time_at(piece, m.number)))
    return "\n".join(chunks) + "\n"
