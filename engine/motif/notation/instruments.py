"""The instruments Motif writes for, with the facts an orchestrator needs.

Ranges are *sounding* MIDI pitches and are the professional practical range,
not the theoretical extreme — a line that sits at the very top of a
bassoon's compass is technically possible and never what a composer means.

Transposing instruments carry the interval from written to sounding pitch,
exactly as MusicXML's ``<transpose>`` element expresses it: a clarinet in
B-flat sounds a major second below what is written, so its entry is
``diatonic=-1, chromatic=-2``. Motif's notation is always in concert pitch;
the engraver converts to written pitch using these numbers, which is what
lets MuseScore's concert-pitch toggle work on the result.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Instrument:
    key: str
    name: str
    abbreviation: str
    program: int                      # General MIDI, 0-based
    low: int                          # sounding range, MIDI numbers
    high: int
    clefs: tuple[str, ...] = ("G",)   # one per staff
    family: str = "other"
    sound: str = "keyboard.piano"     # MusicXML instrument-sound id
    #: Written -> sounding, as (diatonic steps, semitones), octaves included:
    #: a B-flat clarinet is (-1, -2), a double bass (-7, -12).
    transpose: tuple[int, int] = (0, 0)
    keyboard: bool = False            # one player, two hands, several staves
    comfortable: tuple[int, int] | None = None   # where it sings; defaults to range

    @property
    def staves(self) -> int:
        return len(self.clefs)

    @property
    def transposes(self) -> bool:
        return self.transpose != (0, 0)

    def musicxml_transpose(self) -> tuple[int, int, int]:
        """(diatonic, chromatic, octave-change) as MusicXML spells them.

        MusicXML keeps whole octaves out of the other two numbers, so a tenor
        saxophone (a major ninth down) is -1, -2 and an octave of -1.
        """
        steps, semis = self.transpose
        octave = int(steps / 7)            # truncates toward zero
        return steps - 7 * octave, semis - 12 * octave, octave

    @property
    def sweet_spot(self) -> tuple[int, int]:
        return self.comfortable or (self.low, self.high)


def _i(key, name, abbr, program, low, high, clefs=("G",), family="other",
       sound="keyboard.piano", transpose=(0, 0), keyboard=False,
       comfortable=None) -> Instrument:
    return Instrument(key, name, abbr, program, low, high, tuple(clefs), family,
                      sound, tuple(transpose), keyboard, comfortable)


INSTRUMENTS: dict[str, Instrument] = {i.key: i for i in [
    # -- keyboards ---------------------------------------------------------
    _i("piano", "Piano", "Pno.", 0, 21, 108, ("G", "F"), "keyboard",
       "keyboard.piano", keyboard=True, comfortable=(28, 100)),
    _i("harpsichord", "Harpsichord", "Hpschd.", 6, 29, 89, ("G", "F"), "keyboard",
       "keyboard.harpsichord", keyboard=True),
    _i("organ", "Organ", "Org.", 19, 36, 96, ("G", "F", "F"), "keyboard",
       "keyboard.organ.pipe", keyboard=True),
    _i("celesta", "Celesta", "Cel.", 8, 60, 108, ("G", "F"), "keyboard",
       "keyboard.celesta", transpose=(7, 12), keyboard=True),
    _i("harp", "Harp", "Hp.", 46, 24, 103, ("G", "F"), "pluck",
       "pluck.harp", keyboard=True, comfortable=(31, 96)),
    # -- strings -----------------------------------------------------------
    _i("violin", "Violin", "Vln.", 40, 55, 100, ("G",), "strings",
       "strings.violin", comfortable=(55, 93)),
    _i("viola", "Viola", "Vla.", 41, 48, 88, ("C",), "strings",
       "strings.viola", comfortable=(48, 81)),
    _i("cello", "Violoncello", "Vc.", 42, 36, 81, ("F",), "strings",
       "strings.cello", comfortable=(36, 76)),
    _i("double_bass", "Contrabass", "Cb.", 43, 28, 67, ("F",), "strings",
       "strings.contrabass", transpose=(-7, -12),
       comfortable=(28, 60)),
    _i("strings", "Strings", "Str.", 48, 28, 100, ("G", "F"), "strings",
       "strings.group", keyboard=True),
    # -- woodwinds ---------------------------------------------------------
    _i("piccolo", "Piccolo", "Picc.", 72, 74, 108, ("G",), "woodwinds",
       "wind.flutes.flute.piccolo", transpose=(7, 12)),
    _i("flute", "Flute", "Fl.", 73, 60, 96, ("G",), "woodwinds",
       "wind.flutes.flute", comfortable=(62, 93)),
    _i("oboe", "Oboe", "Ob.", 68, 58, 91, ("G",), "woodwinds",
       "wind.reed.oboe", comfortable=(60, 86)),
    _i("english_horn", "English Horn", "E.H.", 69, 52, 81, ("G",), "woodwinds",
       "wind.reed.english-horn", transpose=(-4, -7)),
    _i("clarinet", "Clarinet in B♭", "Cl.", 71, 50, 91, ("G",), "woodwinds",
       "wind.reed.clarinet.bflat", transpose=(-1, -2), comfortable=(52, 86)),
    _i("bass_clarinet", "Bass Clarinet", "B. Cl.", 71, 34, 77, ("G",), "woodwinds",
       "wind.reed.clarinet.bass", transpose=(-8, -14)),
    _i("bassoon", "Bassoon", "Bsn.", 70, 34, 75, ("F",), "woodwinds",
       "wind.reed.bassoon", comfortable=(36, 72)),
    _i("contrabassoon", "Contrabassoon", "Cbsn.", 70, 22, 53, ("F",), "woodwinds",
       "wind.reed.contrabassoon", transpose=(-7, -12)),
    _i("soprano_sax", "Soprano Saxophone", "S. Sax.", 64, 56, 87, ("G",), "woodwinds",
       "wind.reed.saxophone.soprano", transpose=(-1, -2)),
    _i("alto_sax", "Alto Saxophone", "A. Sax.", 65, 49, 80, ("G",), "woodwinds",
       "wind.reed.saxophone.alto", transpose=(-5, -9)),
    _i("tenor_sax", "Tenor Saxophone", "T. Sax.", 66, 44, 75, ("G",), "woodwinds",
       "wind.reed.saxophone.tenor", transpose=(-8, -14)),
    _i("recorder", "Recorder", "Rec.", 74, 72, 98, ("G",), "woodwinds",
       "wind.flutes.recorder", transpose=(7, 12)),
    # -- brass -------------------------------------------------------------
    _i("horn", "Horn in F", "Hn.", 60, 41, 77, ("G",), "brass",
       "brass.french-horn", transpose=(-4, -7), comfortable=(45, 74)),
    _i("trumpet", "Trumpet in B♭", "Tpt.", 56, 54, 82, ("G",), "brass",
       "brass.trumpet.bflat", transpose=(-1, -2), comfortable=(58, 79)),
    _i("trumpet_c", "Trumpet in C", "Tpt.", 56, 54, 84, ("G",), "brass",
       "brass.trumpet.c"),
    _i("trombone", "Trombone", "Tbn.", 57, 40, 72, ("F",), "brass",
       "brass.trombone", comfortable=(41, 70)),
    _i("bass_trombone", "Bass Trombone", "B. Tbn.", 57, 34, 67, ("F",), "brass",
       "brass.trombone.bass"),
    _i("tuba", "Tuba", "Tba.", 58, 26, 58, ("F",), "brass", "brass.tuba"),
    # -- percussion (pitched) ---------------------------------------------
    _i("timpani", "Timpani", "Timp.", 47, 38, 57, ("F",), "percussion",
       "drum.timpani"),
    _i("glockenspiel", "Glockenspiel", "Glk.", 9, 79, 108, ("G",), "percussion",
       "pitched-percussion.glockenspiel", transpose=(14, 24)),
    _i("xylophone", "Xylophone", "Xyl.", 13, 65, 108, ("G",), "percussion",
       "pitched-percussion.xylophone", transpose=(7, 12)),
    _i("marimba", "Marimba", "Mar.", 12, 45, 96, ("G", "F"), "percussion",
       "pitched-percussion.marimba", keyboard=True),
    _i("vibraphone", "Vibraphone", "Vib.", 11, 53, 89, ("G",), "percussion",
       "pitched-percussion.vibraphone"),
    _i("tubular_bells", "Tubular Bells", "T. Bells", 14, 60, 77, ("G",),
       "percussion", "metal.bells.tubular"),
    # -- plucked -----------------------------------------------------------
    _i("guitar", "Guitar", "Gtr.", 24, 40, 83, ("G8vb",), "pluck",
       "pluck.guitar"),              # the treble-8vb clef carries the octave
    _i("mandolin", "Mandolin", "Mdn.", 25, 55, 88, ("G",), "pluck",
       "pluck.mandolin"),
    # -- voices ------------------------------------------------------------
    _i("soprano", "Soprano", "S.", 52, 60, 81, ("G",), "voice", "voice.soprano"),
    _i("mezzo", "Mezzo-soprano", "Mz.", 52, 57, 77, ("G",), "voice",
       "voice.mezzo-soprano"),
    _i("alto", "Alto", "A.", 52, 53, 74, ("G",), "voice", "voice.alto"),
    _i("tenor", "Tenor", "T.", 52, 48, 69, ("G8vb",), "voice", "voice.tenor"),
    _i("baritone", "Baritone", "Bar.", 52, 45, 65, ("F",), "voice", "voice.baritone"),
    _i("bass", "Bass", "B.", 52, 40, 62, ("F",), "voice", "voice.bass"),
    _i("voice", "Voice", "V.", 52, 55, 79, ("G",), "voice", "voice.vocals"),
]}

#: Everything a musician might call an instrument, mapped home.
ALIASES: dict[str, str] = {
    "pianoforte": "piano", "grand_piano": "piano", "keyboard": "piano",
    "clavier": "piano", "fortepiano": "piano", "cembalo": "harpsichord",
    "pipe_organ": "organ", "church_organ": "organ",
    "violin_i": "violin", "violin_ii": "violin", "violin_1": "violin",
    "violin_2": "violin", "vln": "violin", "fiddle": "violin",
    "violoncello": "cello", "vc": "cello", "contrabass": "double_bass",
    "bass_viol": "double_bass", "string_bass": "double_bass", "upright_bass": "double_bass",
    "db": "double_bass", "cb": "double_bass", "string_section": "strings",
    "string_orchestra": "strings",
    "cor_anglais": "english_horn", "clarinet_in_bb": "clarinet",
    "clarinet_in_b_flat": "clarinet", "bb_clarinet": "clarinet", "cl": "clarinet",
    "fl": "flute", "ob": "oboe", "bsn": "bassoon", "fagotto": "bassoon",
    "saxophone": "alto_sax", "alto_saxophone": "alto_sax",
    "tenor_saxophone": "tenor_sax", "soprano_saxophone": "soprano_sax",
    "french_horn": "horn", "horn_in_f": "horn", "hn": "horn",
    "trumpet_in_bb": "trumpet", "trumpet_in_b_flat": "trumpet", "tpt": "trumpet",
    "trumpet_in_c": "trumpet_c", "tbn": "trombone", "timp": "timpani",
    "kettledrums": "timpani", "glock": "glockenspiel", "bells": "tubular_bells",
    "chimes": "tubular_bells", "vibes": "vibraphone",
    "acoustic_guitar": "guitar", "classical_guitar": "guitar",
    "voice_soprano": "soprano", "mezzo_soprano": "mezzo", "contralto": "alto",
    "singer": "voice", "vocals": "voice", "solo_voice": "voice",
}


def instrument(name: str | None) -> Instrument | None:
    """Find an instrument by key, alias or plain-English name."""
    if not name:
        return None
    raw = name.strip().lower()
    key = (raw.replace("♭", "b").replace("-", "_").replace(" ", "_")
           .replace(".", "").replace("__", "_"))
    if key in INSTRUMENTS:
        return INSTRUMENTS[key]
    if key in ALIASES:
        return INSTRUMENTS[ALIASES[key]]
    # "Violin I", "2nd violin", "Horn in F 1" — strip numbering and try again.
    import re
    stripped = re.sub(r"(^|_)(\d+(st|nd|rd|th)?|i{1,3}|iv|v)(_|$)", "_", key).strip("_")
    if stripped in INSTRUMENTS:
        return INSTRUMENTS[stripped]
    if stripped in ALIASES:
        return INSTRUMENTS[ALIASES[stripped]]
    for k, inst in INSTRUMENTS.items():
        if inst.name.lower().replace(" ", "_") == key:
            return inst
    for word in sorted(INSTRUMENTS, key=len, reverse=True):
        if word in key:
            return INSTRUMENTS[word]
    for word in sorted(ALIASES, key=len, reverse=True):
        if len(word) > 3 and word in key:
            return INSTRUMENTS[ALIASES[word]]
    return None


def by_program(program: int, staves: int = 1) -> Instrument | None:
    """Best guess from a General MIDI program — for scores Motif didn't write."""
    matches = [i for i in INSTRUMENTS.values() if i.program == program]
    if not matches:
        return None
    exact = [i for i in matches if i.staves == staves]
    return (exact or matches)[0]


def catalogue_text() -> str:
    """The instrument list as the composer sees it in its instructions."""
    rows = []
    for inst in INSTRUMENTS.values():
        lo, hi = inst.low, inst.high
        rows.append(f"{inst.key} ({inst.name}; {_name(lo)}–{_name(hi)} sounding"
                    + (", 2 staves RH/LH" if inst.staves == 2 else "")
                    + (", 3 staves RH/LH/Ped" if inst.staves == 3 else "")
                    + ")")
    return "; ".join(rows)


_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def _name(midi: int) -> str:
    return f"{_NAMES[midi % 12]}{midi // 12 - 1}"


@dataclass
class PartSpec:
    """One part in a piece: an instrument, and what the score calls it."""

    id: str
    instrument: Instrument
    name: str = ""
    abbreviation: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return self.name or self.instrument.name

    @property
    def display_abbreviation(self) -> str:
        return self.abbreviation or self.instrument.abbreviation

    @property
    def staves(self) -> int:
        return self.instrument.staves
