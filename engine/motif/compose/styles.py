"""Style profiles — the encoded stylistic knowledge Motif composes from.

Each profile captures how a composer actually writes: which textures the hands
play, how chromatic the harmony gets, where phrases breathe, how wide the
dynamic arc runs and what the page is marked with.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .melody import MelodyStyle


@dataclass
class StyleProfile:
    name: str = "classical"
    display: str = "Classical"
    era: str = "classical"

    # -- global shape -----------------------------------------------------
    tempo_range: tuple[int, int] = (80, 132)
    meters: tuple[tuple[int, int], ...] = ((4, 4), (3, 4), (2, 4))
    forms: tuple[str, ...] = ("ternary", "period", "rounded_binary")
    phrase_bars: tuple[int, ...] = (4, 8)

    # -- harmony ----------------------------------------------------------
    progression_pool_major: str = "classical_major"
    progression_pool_minor: str = "classical_minor"
    chromaticism: float = 0.15          # secondary dominants, borrowed chords
    seventh_rate: float = 0.35
    extension_rate: float = 0.05        # 9ths, 11ths, 13ths
    harmonic_rhythm: str = "moderate"
    modulation_rate: float = 0.3
    cadence_pool: tuple[str, ...] = ("authentic", "half", "perfect_authentic")

    # -- texture ----------------------------------------------------------
    lh_textures: tuple[str, ...] = ("alberti", "block_chords", "waltz")
    rh_style: str = "melody"            # melody | counterpoint | chordal | figuration
    inner_voice: bool = False
    doubling: str = "none"              # none | octave | thirds | sixths | chords

    # -- melody -----------------------------------------------------------
    melody: MelodyStyle = field(default_factory=MelodyStyle)
    rhythm_density: float = 0.45
    motif_length: tuple[int, int] = (3, 5)

    # -- surface ----------------------------------------------------------
    ornaments: tuple[str, ...] = ("trill-mark", "turn", "mordent")
    ornament_rate: float = 0.06
    grace_rate: float = 0.05
    articulation_rate: float = 0.25
    pedal: str = "harmonic"             # none | harmonic | long | syncopated
    dynamic_range: tuple[str, str] = ("p", "f")
    dynamic_volatility: float = 0.4
    rubato_terms: tuple[str, ...] = ()
    tempo_terms: tuple[str, ...] = ("Allegro", "Andante", "Moderato")

    # -- register ---------------------------------------------------------
    rh_range: tuple[int, int] = (55, 88)
    lh_range: tuple[int, int] = (33, 64)
    hand_span: int = 14

    keywords: tuple[str, ...] = ()

    def with_energy(self, energy: float) -> "StyleProfile":
        """Scale density and dynamics for a more or less intense moment."""
        m = replace(self.melody,
                    leap_tolerance=self.melody.leap_tolerance * (0.8 + energy * 0.5),
                    ornament_rate=self.melody.ornament_rate * (0.6 + energy))
        return replace(self, melody=m,
                       rhythm_density=min(0.95, self.rhythm_density * (0.65 + energy * 0.8)))


def _m(**kw) -> MelodyStyle:
    return MelodyStyle(**kw)


STYLES: dict[str, StyleProfile] = {}


def _add(p: StyleProfile) -> StyleProfile:
    STYLES[p.name] = p
    return p


# --- Baroque ---------------------------------------------------------------
_add(StyleProfile(
    name="bach", display="J.S. Bach", era="baroque",
    tempo_range=(58, 126), meters=((4, 4), (3, 4), (12, 8), (2, 2), (6, 8)),
    forms=("invention", "prelude", "fugue", "binary", "chorale"),
    phrase_bars=(4, 8, 6),
    progression_pool_major="baroque_major", progression_pool_minor="baroque_minor",
    chromaticism=0.18, seventh_rate=0.45, harmonic_rhythm="fast", modulation_rate=0.45,
    cadence_pool=("authentic", "perfect_authentic", "phrygian", "half"),
    lh_textures=("two_part_invention", "walking_bass", "arpeggio", "chorale"),
    rh_style="counterpoint", inner_voice=True,
    melody=_m(leap_tolerance=0.85, chromaticism=0.10, step_preference=1.35,
              repeat_tolerance=0.2, appoggiatura_rate=0.10, suspension_rate=0.28,
              range_low=55, range_high=86),
    rhythm_density=0.62, motif_length=(4, 8),
    ornaments=("trill-mark", "mordent", "inverted-mordent", "turn"),
    ornament_rate=0.10, grace_rate=0.06, articulation_rate=0.12,
    pedal="none", dynamic_range=("mp", "f"), dynamic_volatility=0.15,
    tempo_terms=("Allegro", "Andante", "Allegro moderato", "Vivace", "Adagio"),
    rh_range=(55, 88), lh_range=(36, 67), hand_span=12,
    keywords=("bach", "baroque", "fugue", "invention", "counterpoint", "contrapuntal",
              "prelude", "chorale", "toccata")))

_add(replace(STYLES["bach"], name="handel", display="Handel",
             forms=("binary", "prelude", "chorale", "theme_and_variations"),
             ornament_rate=0.12, rhythm_density=0.55,
             keywords=("handel", "baroque suite", "sarabande")))

_add(replace(STYLES["bach"], name="scarlatti", display="D. Scarlatti",
             forms=("binary", "sonata_binary"), tempo_range=(84, 152),
             lh_textures=("alberti", "arpeggio", "broken_octaves", "repeated_chords"),
             rh_style="figuration", rhythm_density=0.7, melody=_m(leap_tolerance=1.35),
             keywords=("scarlatti", "keyboard sonata", "spanish")))

_add(replace(STYLES["bach"], name="vivaldi", display="Vivaldi", era="baroque",
             forms=("ritornello", "binary"), rh_style="melody",
             lh_textures=("walking_bass", "repeated_chords", "arpeggio"),
             keywords=("vivaldi", "concerto grosso", "ritornello")))

# --- Classical -------------------------------------------------------------
_add(StyleProfile(
    name="mozart", display="Mozart", era="classical",
    tempo_range=(66, 152), meters=((4, 4), (3, 4), (2, 4), (6, 8), (2, 2)),
    forms=("sonata", "rondo", "ternary", "theme_and_variations", "period"),
    phrase_bars=(4, 8),
    chromaticism=0.12, seventh_rate=0.32, harmonic_rhythm="moderate", modulation_rate=0.4,
    cadence_pool=("perfect_authentic", "authentic", "half", "deceptive"),
    lh_textures=("alberti", "block_chords", "octave_bass", "march"),
    rh_style="melody", doubling="thirds",
    melody=_m(leap_tolerance=0.95, chromaticism=0.06, step_preference=1.25,
              appoggiatura_rate=0.20, suspension_rate=0.14, range_low=57, range_high=88),
    rhythm_density=0.5, motif_length=(3, 5),
    ornaments=("trill-mark", "turn", "mordent"), ornament_rate=0.09, grace_rate=0.10,
    articulation_rate=0.35, pedal="harmonic",
    dynamic_range=("p", "f"), dynamic_volatility=0.45,
    tempo_terms=("Allegro", "Andante", "Allegretto", "Adagio", "Presto", "Andante grazioso"),
    rh_range=(57, 88), lh_range=(36, 64), hand_span=13,
    keywords=("mozart", "classical", "galant", "elegant", "graceful", "alberti")))

_add(replace(STYLES["mozart"], name="haydn", display="Haydn",
             forms=("sonata", "rondo", "theme_and_variations", "minuet"),
             chromaticism=0.10, dynamic_volatility=0.55, articulation_rate=0.4,
             melody=_m(leap_tolerance=1.05, appoggiatura_rate=0.16, range_low=55, range_high=86),
             tempo_terms=("Allegro", "Andante", "Presto", "Allegro con brio", "Menuetto"),
             keywords=("haydn", "wit", "minuet", "surprise", "classical")))

_add(replace(STYLES["mozart"], name="clementi", display="Clementi",
             rhythm_density=0.6, lh_textures=("alberti", "broken_octaves", "block_chords"),
             keywords=("clementi", "sonatina", "study")))

_add(StyleProfile(
    name="beethoven", display="Beethoven", era="classical",
    tempo_range=(52, 168), meters=((4, 4), (3, 4), (2, 4), (6, 8), (2, 2), (3, 8)),
    forms=("sonata", "theme_and_variations", "rondo", "scherzo", "ternary"),
    phrase_bars=(4, 8, 6),
    chromaticism=0.22, seventh_rate=0.42, harmonic_rhythm="moderate", modulation_rate=0.55,
    cadence_pool=("perfect_authentic", "deceptive", "half", "authentic"),
    lh_textures=("octave_bass", "tremolo", "block_chords", "alberti", "broken_octaves"),
    rh_style="melody", doubling="octave", inner_voice=True,
    melody=_m(leap_tolerance=1.3, chromaticism=0.12, step_preference=1.1,
              appoggiatura_rate=0.18, range_low=45, range_high=92, peak_uniqueness=1.4),
    rhythm_density=0.55, motif_length=(2, 4),
    ornaments=("trill-mark", "turn"), ornament_rate=0.07, grace_rate=0.08,
    articulation_rate=0.45, pedal="harmonic",
    dynamic_range=("pp", "ff"), dynamic_volatility=0.85,
    tempo_terms=("Allegro con brio", "Adagio sostenuto", "Allegro assai",
                 "Andante con moto", "Presto agitato", "Molto allegro"),
    rh_range=(50, 92), lh_range=(28, 64), hand_span=14,
    keywords=("beethoven", "dramatic", "heroic", "stormy", "sonata", "fate", "struggle")))

# --- Romantic --------------------------------------------------------------
_add(StyleProfile(
    name="chopin", display="Chopin", era="romantic",
    tempo_range=(44, 152), meters=((4, 4), (3, 4), (6, 8), (12, 8), (2, 2), (9, 8)),
    forms=("nocturne", "ternary", "waltz", "mazurka", "prelude", "etude", "ballade"),
    phrase_bars=(4, 8),
    progression_pool_major="romantic_major", progression_pool_minor="romantic_minor",
    chromaticism=0.34, seventh_rate=0.5, extension_rate=0.14,
    harmonic_rhythm="moderate", modulation_rate=0.5,
    cadence_pool=("romantic", "perfect_authentic", "deceptive", "neapolitan", "half"),
    lh_textures=("nocturne", "waltz", "arpeggio", "repeated_chords", "block_chords"),
    rh_style="melody", doubling="sixths",
    melody=_m(leap_tolerance=1.25, chromaticism=0.20, ornament_rate=0.22,
              step_preference=1.15, appoggiatura_rate=0.26, suspension_rate=0.2,
              range_low=55, range_high=96, peak_uniqueness=1.3),
    rhythm_density=0.5, motif_length=(3, 6),
    ornaments=("trill-mark", "turn", "mordent"), ornament_rate=0.2, grace_rate=0.22,
    articulation_rate=0.2, pedal="harmonic",
    dynamic_range=("pp", "ff"), dynamic_volatility=0.7,
    rubato_terms=("rubato", "con anima", "espressivo", "dolce", "appassionato",
                  "sotto voce", "legatissimo"),
    tempo_terms=("Lento", "Andante", "Larghetto", "Allegro", "Vivace",
                 "Andante spianato", "Moderato"),
    rh_range=(55, 96), lh_range=(28, 64), hand_span=15,
    keywords=("chopin", "nocturne", "romantic", "lyrical", "cantabile", "rubato",
              "mazurka", "waltz", "ballade", "poetic", "singing")))

_add(StyleProfile(
    name="liszt", display="Liszt", era="romantic",
    tempo_range=(44, 184), meters=((4, 4), (3, 4), (6, 8), (2, 2), (12, 8)),
    forms=("rhapsody", "etude", "ternary", "fantasy", "ballade"),
    phrase_bars=(4, 8, 6),
    progression_pool_major="romantic_major", progression_pool_minor="romantic_minor",
    chromaticism=0.45, seventh_rate=0.55, extension_rate=0.2,
    harmonic_rhythm="moderate", modulation_rate=0.7,
    cadence_pool=("romantic", "neapolitan", "deceptive", "perfect_authentic"),
    lh_textures=("broken_octaves", "tremolo", "arpeggio", "octave_bass",
                 "rachmaninoff_wide", "scale_run"),
    rh_style="figuration", doubling="octave",
    melody=_m(leap_tolerance=1.9, chromaticism=0.3, ornament_rate=0.25,
              step_preference=0.9, range_low=45, range_high=104, peak_uniqueness=1.6),
    rhythm_density=0.72, motif_length=(3, 6),
    ornaments=("trill-mark", "turn", "mordent"), ornament_rate=0.22, grace_rate=0.25,
    articulation_rate=0.3, pedal="harmonic",
    dynamic_range=("pp", "fff"), dynamic_volatility=0.95,
    rubato_terms=("appassionato", "grandioso", "con bravura", "espressivo", "marcato"),
    tempo_terms=("Allegro agitato", "Lento assai", "Vivace", "Presto con fuoco",
                 "Andante lagrimoso", "Allegro maestoso"),
    rh_range=(45, 104), lh_range=(21, 67), hand_span=17,
    keywords=("liszt", "virtuoso", "rhapsody", "transcendental", "octaves",
              "bravura", "cadenza", "fireworks", "dazzling")))

_add(StyleProfile(
    name="rachmaninoff", display="Rachmaninoff", era="late_romantic",
    tempo_range=(40, 168), meters=((4, 4), (3, 4), (12, 8), (2, 2), (6, 8), (5, 4)),
    forms=("prelude", "ternary", "etude_tableau", "concerto", "elegie", "rhapsody"),
    phrase_bars=(4, 8, 6),
    progression_pool_major="romantic_major", progression_pool_minor="romantic_minor",
    chromaticism=0.4, seventh_rate=0.62, extension_rate=0.28,
    harmonic_rhythm="moderate", modulation_rate=0.55,
    cadence_pool=("rach", "romantic", "neapolitan", "deceptive", "perfect_authentic"),
    lh_textures=("rachmaninoff_wide", "repeated_chords", "arpeggio", "octave_bass",
                 "block_chords", "tremolo"),
    rh_style="chordal", doubling="octave", inner_voice=True,
    melody=_m(leap_tolerance=1.35, chromaticism=0.22, ornament_rate=0.1,
              step_preference=1.3, appoggiatura_rate=0.3, suspension_rate=0.3,
              range_low=48, range_high=96, peak_uniqueness=1.5),
    rhythm_density=0.5, motif_length=(4, 7),
    ornaments=("turn", "trill-mark"), ornament_rate=0.07, grace_rate=0.12,
    articulation_rate=0.2, pedal="long",
    dynamic_range=("pp", "fff"), dynamic_volatility=0.9,
    rubato_terms=("espressivo", "appassionato", "cantabile", "sonoro",
                  "con moto", "largamente", "pesante"),
    tempo_terms=("Lento", "Moderato", "Allegro agitato", "Andante", "Adagio sostenuto",
                 "Allegro ma non tanto", "Non allegro"),
    rh_range=(48, 96), lh_range=(21, 62), hand_span=19,
    keywords=("rachmaninoff", "rachmaninov", "dark", "brooding", "sweeping", "lush",
              "russian", "romantic", "concerto", "bells", "elegiac", "melancholy")))

_add(StyleProfile(
    name="scriabin", display="Scriabin", era="late_romantic",
    tempo_range=(40, 152), meters=((4, 4), (3, 4), (6, 8), (5, 4), (9, 8)),
    forms=("prelude", "poem", "etude", "ternary"), phrase_bars=(4, 8),
    progression_pool_major="impressionist", progression_pool_minor="romantic_minor",
    chromaticism=0.6, seventh_rate=0.6, extension_rate=0.45,
    harmonic_rhythm="slow", modulation_rate=0.6,
    cadence_pool=("romantic", "deceptive", "neapolitan"),
    lh_textures=("arpeggio", "rachmaninoff_wide", "syncopated", "tremolo"),
    rh_style="melody", inner_voice=True, doubling="octave",
    melody=_m(leap_tolerance=1.5, chromaticism=0.4, step_preference=0.95,
              appoggiatura_rate=0.32, range_low=50, range_high=100),
    rhythm_density=0.55, motif_length=(3, 5),
    ornaments=("trill-mark", "turn"), ornament_rate=0.12, grace_rate=0.2,
    articulation_rate=0.25, pedal="long",
    dynamic_range=("ppp", "ff"), dynamic_volatility=0.85,
    rubato_terms=("misterioso", "languido", "estatico", "imperioso", "con luminosità"),
    tempo_terms=("Andante", "Allegro fantastico", "Lento", "Presto", "Allegro drammatico"),
    rh_range=(50, 100), lh_range=(24, 64), hand_span=16,
    keywords=("scriabin", "mystic", "ecstatic", "chromatic", "quartal", "visionary",
              "poem", "trance")))

_add(StyleProfile(
    name="brahms", display="Brahms", era="romantic",
    tempo_range=(46, 144), meters=((4, 4), (3, 4), (6, 8), (2, 2), (9, 8)),
    forms=("intermezzo", "ternary", "sonata", "theme_and_variations", "rhapsody"),
    phrase_bars=(4, 8, 5),
    progression_pool_major="romantic_major", progression_pool_minor="romantic_minor",
    chromaticism=0.3, seventh_rate=0.5, extension_rate=0.12,
    harmonic_rhythm="moderate", modulation_rate=0.5,
    cadence_pool=("romantic", "plagal", "perfect_authentic", "deceptive"),
    lh_textures=("syncopated", "arpeggio", "block_chords", "octave_bass"),
    rh_style="chordal", inner_voice=True, doubling="thirds",
    melody=_m(leap_tolerance=1.1, chromaticism=0.16, step_preference=1.25,
              suspension_rate=0.3, range_low=50, range_high=90),
    rhythm_density=0.5, motif_length=(3, 6),
    ornament_rate=0.05, grace_rate=0.08, articulation_rate=0.2, pedal="harmonic",
    dynamic_range=("pp", "ff"), dynamic_volatility=0.6,
    rubato_terms=("espressivo", "dolce", "poco rit.", "grazioso", "teneramente"),
    tempo_terms=("Andante", "Allegretto", "Poco allegretto", "Adagio", "Allegro energico"),
    rh_range=(50, 90), lh_range=(28, 62), hand_span=15,
    keywords=("brahms", "autumnal", "intermezzo", "warm", "cross-rhythm", "hemiola")))

_add(StyleProfile(
    name="schubert", display="Schubert", era="romantic",
    tempo_range=(50, 144), meters=((4, 4), (3, 4), (2, 4), (6, 8), (2, 2)),
    forms=("impromptu", "ternary", "theme_and_variations", "sonata", "lied"),
    chromaticism=0.24, seventh_rate=0.4, harmonic_rhythm="moderate", modulation_rate=0.6,
    cadence_pool=("perfect_authentic", "deceptive", "plagal", "half"),
    lh_textures=("repeated_chords", "waltz", "alberti", "arpeggio", "block_chords"),
    melody=_m(leap_tolerance=1.0, chromaticism=0.12, step_preference=1.3,
              range_low=55, range_high=88),
    rhythm_density=0.45, dynamic_range=("pp", "f"), dynamic_volatility=0.55,
    rubato_terms=("dolce", "espressivo", "cantabile"),
    tempo_terms=("Allegretto", "Andante", "Moderato", "Allegro moderato"),
    keywords=("schubert", "lyrical", "song", "impromptu", "wandering", "lied")))

_add(StyleProfile(
    name="tchaikovsky", display="Tchaikovsky", era="romantic",
    tempo_range=(48, 152), meters=((4, 4), (3, 4), (6, 8), (2, 4), (5, 4)),
    forms=("ternary", "waltz", "theme_and_variations", "concerto"),
    progression_pool_minor="romantic_minor",
    chromaticism=0.28, seventh_rate=0.45, harmonic_rhythm="moderate",
    lh_textures=("waltz", "repeated_chords", "arpeggio", "octave_bass"),
    doubling="octave",
    melody=_m(leap_tolerance=1.15, step_preference=1.3, appoggiatura_rate=0.25,
              range_low=52, range_high=92),
    dynamic_range=("pp", "fff"), dynamic_volatility=0.85,
    rubato_terms=("espressivo", "cantabile", "appassionato", "dolce"),
    tempo_terms=("Andante", "Allegro con spirito", "Valse", "Andante cantabile"),
    keywords=("tchaikovsky", "ballet", "waltz", "sweeping", "russian", "swan")))

_add(StyleProfile(
    name="mendelssohn", display="Mendelssohn", era="romantic",
    tempo_range=(56, 160), forms=("song_without_words", "ternary", "scherzo"),
    lh_textures=("arpeggio", "repeated_chords", "block_chords"),
    chromaticism=0.2, melody=_m(step_preference=1.3, range_low=55, range_high=90),
    rhythm_density=0.55, dynamic_range=("pp", "f"),
    tempo_terms=("Andante con moto", "Allegretto", "Presto", "Andante espressivo"),
    keywords=("mendelssohn", "song without words", "elfin", "scherzo")))

_add(StyleProfile(
    name="grieg", display="Grieg", era="romantic",
    tempo_range=(50, 144), forms=("lyric_piece", "ternary"),
    progression_pool_minor="modal", chromaticism=0.24,
    lh_textures=("block_chords", "arpeggio", "drone", "waltz"),
    melody=_m(step_preference=1.3, range_low=55, range_high=88),
    tempo_terms=("Allegretto", "Andante", "Poco allegro"),
    keywords=("grieg", "nordic", "folk", "lyric piece", "norwegian")))

# --- Impressionist / modern -----------------------------------------------
_add(StyleProfile(
    name="debussy", display="Debussy", era="impressionist",
    tempo_range=(40, 132), meters=((4, 4), (3, 4), (6, 8), (9, 8), (5, 4), (12, 8)),
    forms=("prelude", "arabesque", "ternary", "reverie"),
    progression_pool_major="impressionist", progression_pool_minor="impressionist",
    chromaticism=0.35, seventh_rate=0.7, extension_rate=0.55,
    harmonic_rhythm="slow", modulation_rate=0.35,
    cadence_pool=("plagal", "romantic", "deceptive"),
    lh_textures=("arpeggio", "sustained", "pedal_point", "block_chords", "ostinato"),
    rh_style="chordal", doubling="chords",
    melody=_m(leap_tolerance=1.1, chromaticism=0.25, step_preference=1.2,
              repeat_tolerance=0.5, range_low=52, range_high=98),
    rhythm_density=0.42, motif_length=(3, 5),
    ornaments=("turn",), ornament_rate=0.06, grace_rate=0.16,
    articulation_rate=0.15, pedal="long",
    dynamic_range=("ppp", "mf"), dynamic_volatility=0.5,
    rubato_terms=("doux et expressif", "en cédant", "lumineux", "très calme", "rubato"),
    tempo_terms=("Modéré", "Lent", "Andantino", "Très modéré", "Doucement expressif"),
    rh_range=(52, 100), lh_range=(24, 64), hand_span=15,
    keywords=("debussy", "impressionist", "whole tone", "dreamy", "water", "atmospheric",
              "floating", "misty", "pentatonic")))

_add(replace(STYLES["debussy"], name="ravel", display="Ravel",
             chromaticism=0.38, extension_rate=0.6, rhythm_density=0.55,
             forms=("prelude", "ternary", "pavane", "waltz"),
             tempo_terms=("Assez lent", "Modéré", "Vif", "Lent"),
             keywords=("ravel", "pavane", "jeux d'eau", "refined", "french")))

_add(StyleProfile(
    name="satie", display="Satie", era="impressionist",
    tempo_range=(48, 92), meters=((3, 4), (4, 4)),
    forms=("gymnopedie", "ternary"), progression_pool_major="impressionist",
    chromaticism=0.15, seventh_rate=0.75, extension_rate=0.35,
    harmonic_rhythm="slow", modulation_rate=0.15,
    lh_textures=("waltz", "sustained", "block_chords"),
    melody=_m(leap_tolerance=0.9, step_preference=1.4, repeat_tolerance=0.6,
              range_low=57, range_high=84),
    rhythm_density=0.22, ornament_rate=0.0, grace_rate=0.02,
    articulation_rate=0.05, pedal="long",
    dynamic_range=("ppp", "mp"), dynamic_volatility=0.2,
    rubato_terms=("lent et douloureux", "avec étonnement"),
    tempo_terms=("Lent", "Lent et douloureux", "Modéré"),
    keywords=("satie", "gymnopedie", "minimal", "sparse", "calm", "ambient", "simple")))

_add(StyleProfile(
    name="einaudi", display="Contemporary Minimal", era="contemporary",
    tempo_range=(56, 120), meters=((4, 4), (3, 4), (6, 8)),
    forms=("ternary", "ostinato_form"), progression_pool_major="pop",
    progression_pool_minor="modal",
    chromaticism=0.05, seventh_rate=0.3, extension_rate=0.25,
    harmonic_rhythm="slow", modulation_rate=0.1,
    cadence_pool=("plagal", "authentic"),
    lh_textures=("arpeggio", "ostinato", "sustained", "block_chords"),
    melody=_m(leap_tolerance=0.85, step_preference=1.5, repeat_tolerance=0.7,
              range_low=60, range_high=88),
    rhythm_density=0.4, ornament_rate=0.0, grace_rate=0.02,
    articulation_rate=0.05, pedal="long",
    dynamic_range=("pp", "mf"), dynamic_volatility=0.35,
    tempo_terms=("Andante", "Moderato", "Calmo"),
    keywords=("minimal", "modern", "cinematic", "ambient", "einaudi", "contemplative",
              "meditative", "film", "soundtrack", "peaceful", "calm")))

_add(StyleProfile(
    name="film", display="Cinematic", era="contemporary",
    tempo_range=(48, 140), meters=((4, 4), (3, 4), (6, 8), (12, 8)),
    forms=("ternary", "through_composed", "ostinato_form"),
    progression_pool_major="romantic_major", progression_pool_minor="modal",
    chromaticism=0.2, seventh_rate=0.45, extension_rate=0.3,
    harmonic_rhythm="slow", modulation_rate=0.3,
    lh_textures=("ostinato", "arpeggio", "sustained", "octave_bass", "tremolo"),
    doubling="octave",
    melody=_m(leap_tolerance=1.2, step_preference=1.3, range_low=52, range_high=92),
    rhythm_density=0.45, pedal="long",
    dynamic_range=("pp", "fff"), dynamic_volatility=0.8,
    tempo_terms=("Andante", "Moderato", "Adagio", "Allegro"),
    keywords=("film", "score", "cinematic", "epic", "trailer", "soundtrack",
              "mysterious", "forest", "scene", "atmosphere", "underscore")))

# A neutral default.
_add(StyleProfile(name="classical", display="Classical", era="classical",
                  keywords=("classical", "traditional")))


def resolve_style(name: str | None) -> StyleProfile:
    if not name:
        return STYLES["classical"]
    key = name.strip().lower().replace(" ", "_")
    if key in STYLES:
        return STYLES[key]
    aliases = {"rachmaninov": "rachmaninoff", "rachmaninoff": "rachmaninoff",
               "j.s._bach": "bach", "js_bach": "bach", "johann_sebastian_bach": "bach",
               "beethoven": "beethoven", "chopin": "chopin", "romantic": "chopin",
               "baroque": "bach", "impressionism": "debussy", "impressionist": "debussy",
               "minimalist": "einaudi", "minimal": "einaudi", "modern": "einaudi",
               "cinematic": "film", "soundtrack": "film"}
    if key in aliases:
        return STYLES[aliases[key]]
    for sname, prof in STYLES.items():
        if key in prof.keywords or sname in key:
            return prof
    return STYLES["classical"]


def match_styles(text: str) -> list[tuple[str, float]]:
    """Score every profile against free text — used by the prompt parser."""
    t = " " + text.lower() + " "
    scores: list[tuple[str, float]] = []
    for name, prof in STYLES.items():
        s = 0.0
        if f" {name} " in t or name in t:
            s += 6.0
        for kw in prof.keywords:
            if kw in t:
                s += 3.0 if " " in kw else 2.0
        if prof.era.replace("_", " ") in t:
            s += 1.5
        if s > 0:
            scores.append((name, s))
    scores.sort(key=lambda x: -x[1])
    return scores
