"""Composer profiles: what each composer's music is made of.

A profile ties together the harmonic idiom, the melodic habits and the
piano textures a composer reaches for in each kind of passage, plus the
tempo, metre, pedalling and dynamic range typical of their music. Requests
for a composer without a profile of their own use the nearest one (Medtner
writes like Rachmaninoff here; Fauré like the Romantics with a French
harmonic colour), so any composer can be asked for.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Profile:
    name: str
    display: str
    harmony: str                       # a HarmonyStyle name
    melody: str                        # a MelodyStyle name
    #: Textures for each kind of passage: theme, contrast (the middle section),
    #: climax, return, closing. Several per role: one is chosen per piece.
    textures: dict[str, list[str]]
    pedal: str = "harmony"             # harmony (change with each chord) | sparse | none
    dynamics: tuple[str, str] = ("p", "f")   # quietest and loudest ordinary levels
    climax_dynamic: str = "ff"
    rubato: float = 0.2                # how much the tempo breathes at cadences
    ornaments: float = 0.1
    octave_climax: bool = False        # double the melody in octaves at the climax
    planing: bool = False              # returns harmonise the tune in parallel chords
    tenor: float = 0.0                 # chance the middle section sings in the tenor
    bass_low: int = 31
    minor_bias: float = 0.5
    phrase: str = "sentence"           # preferred theme structure: sentence | period
    genres: tuple[str, ...] = ()
    words: dict[str, str] = field(default_factory=dict)   # expressive words for sections
    intro: float = 0.3                 # chance the accompaniment starts alone for a bar or two
    inner: float = 0.0                 # chance a lyrical phrase gains a singing inner voice
    language: str = "it"               # tempo words: it | fr | de
    lean: str = "lyrical"              # the character a request without one gets


PROFILES: dict[str, Profile] = {}


def _add(p: Profile) -> None:
    PROFILES[p.name] = p


_add(Profile("bach", "J. S. Bach", "baroque", "baroque",
             {"theme": ["walking"], "contrast": ["walking"], "climax": ["walking"],
              "return": ["walking"], "closing": ["block"]},
             pedal="none", dynamics=("p", "f"), climax_dynamic="f", rubato=0.03,
             ornaments=0.15, phrase="sentence",
             genres=("invention", "prelude", "fugue", "minuet", "gigue", "sarabande"),
             intro=0.0, lean="lively"))
_add(Profile("handel", "Handel", "baroque", "baroque",
             {"theme": ["walking", "block"], "contrast": ["walking"], "climax": ["block"],
              "return": ["walking"], "closing": ["block"]},
             pedal="none", dynamics=("p", "f"), climax_dynamic="f", rubato=0.03,
             intro=0.0, lean="lively"))
_add(Profile("scarlatti", "Scarlatti", "baroque", "baroque",
             {"theme": ["walking", "alberti"], "contrast": ["walking"], "climax": ["block"],
              "return": ["walking"], "closing": ["block"]},
             pedal="none", dynamics=("p", "f"), climax_dynamic="f", rubato=0.05,
             intro=0.0, lean="lively"))
_add(Profile("vivaldi", "Vivaldi", "baroque", "baroque",
             {"theme": ["repeated", "walking"], "contrast": ["walking"],
              "climax": ["repeated"], "return": ["repeated"], "closing": ["block"]},
             pedal="none", dynamics=("p", "f"), climax_dynamic="f", rubato=0.03,
             intro=0.0, lean="lively"))
_add(Profile("mozart", "Mozart", "classical", "classical",
             {"theme": ["alberti", "alberti", "waltz"], "contrast": ["alberti", "repeated"],
              "climax": ["block", "alberti"], "return": ["alberti"], "closing": ["block"]},
             pedal="sparse", dynamics=("p", "f"), climax_dynamic="f", rubato=0.06,
             ornaments=0.2, phrase="period",
             genres=("sonata", "minuet", "rondo", "variations", "fantasia"),
             intro=0.0, lean="lively"))
_add(Profile("haydn", "Haydn", "classical", "classical",
             {"theme": ["alberti", "block"], "contrast": ["repeated", "alberti"],
              "climax": ["block"], "return": ["alberti"], "closing": ["block"]},
             pedal="sparse", dynamics=("p", "f"), climax_dynamic="f", rubato=0.05,
             phrase="period",
             intro=0.0, lean="lively"))
_add(Profile("clementi", "Clementi", "classical", "classical",
             {"theme": ["alberti"], "contrast": ["alberti"], "climax": ["block"],
              "return": ["alberti"], "closing": ["block"]},
             pedal="sparse", rubato=0.05, phrase="period",
             intro=0.0, lean="lively"))
_add(Profile("beethoven", "Beethoven", "classical", "classical",
             {"theme": ["block", "alberti", "repeated"], "contrast": ["repeated", "sweep16"],
              "climax": ["block", "repeated"], "return": ["alberti", "block"],
              "closing": ["block"]},
             pedal="sparse", dynamics=("p", "f"), climax_dynamic="ff", rubato=0.08,
             phrase="sentence",
             genres=("sonata", "bagatelle", "variations", "rondo", "scherzo"),
             intro=0.1, lean="stormy"))
_add(Profile("schubert", "Schubert", "romantic", "romantic",
             {"theme": ["repeated", "nocturne"], "contrast": ["repeated", "block"],
              "climax": ["block"], "return": ["repeated"], "closing": ["block"]},
             pedal="harmony", rubato=0.12, phrase="period",
             genres=("impromptu", "moment musical", "lied"),
             intro=0.6, inner=0.3))
_add(Profile("mendelssohn", "Mendelssohn", "romantic", "romantic",
             {"theme": ["nocturne", "repeated"], "contrast": ["sweep16"],
              "climax": ["block"], "return": ["nocturne"], "closing": ["block"]},
             pedal="harmony", rubato=0.12, genres=("song without words",),
             intro=0.5, inner=0.3))
_add(Profile("chopin", "Chopin", "romantic", "romantic",
             {"theme": ["nocturne"], "contrast": ["block", "sweep"], "climax": ["sweep", "block"],
              "return": ["nocturne"], "closing": ["nocturne", "block"]},
             pedal="harmony", dynamics=("pp", "f"), climax_dynamic="ff", rubato=0.22,
             ornaments=0.35, phrase="period",
             genres=("nocturne", "prelude", "waltz", "mazurka", "etude", "ballade", "polonaise"),
             words={"theme": "dolce", "contrast": "agitato", "return": "con anima"},
             intro=0.5, inner=0.45, tenor=0.25))
_add(Profile("schumann", "Schumann", "romantic", "romantic",
             {"theme": ["repeated", "nocturne"], "contrast": ["repeated"], "climax": ["block"],
              "return": ["nocturne"], "closing": ["block"]},
             pedal="harmony", rubato=0.15,
             intro=0.3, language="de", inner=0.35, tenor=0.3))
_add(Profile("liszt", "Liszt", "romantic", "russian",
             {"theme": ["sweep", "nocturne"], "contrast": ["sweep16", "bells"],
              "climax": ["bells", "sweep16"], "return": ["sweep"], "closing": ["block"]},
             pedal="harmony", dynamics=("p", "ff"), climax_dynamic="fff", rubato=0.2,
             ornaments=0.2, octave_climax=True, bass_low=26,
             genres=("etude", "consolation", "liebestraum", "rhapsody", "ballade"),
             words={"theme": "espressivo", "contrast": "agitato", "climax": "appassionato"},
             intro=0.5, inner=0.3))
_add(Profile("brahms", "Brahms", "romantic", "romantic",
             {"theme": ["nocturne", "repeated"], "contrast": ["block", "repeated"],
              "climax": ["block"], "return": ["nocturne"], "closing": ["block"]},
             pedal="harmony", rubato=0.12, genres=("intermezzo", "rhapsody", "waltz"),
             intro=0.3, inner=0.4, tenor=0.35))
_add(Profile("grieg", "Grieg", "romantic", "romantic",
             {"theme": ["nocturne", "block"], "contrast": ["repeated"], "climax": ["block"],
              "return": ["nocturne"], "closing": ["block"]},
             pedal="harmony", rubato=0.15, genres=("lyric piece",),
             intro=0.4, inner=0.3, tenor=0.2))
_add(Profile("tchaikovsky", "Tchaikovsky", "russian", "romantic",
             {"theme": ["nocturne", "block"], "contrast": ["repeated", "sweep"],
              "climax": ["block", "bells"], "return": ["nocturne"], "closing": ["block"]},
             pedal="harmony", dynamics=("p", "f"), climax_dynamic="ff", rubato=0.18,
             genres=("romance", "barcarolle", "waltz", "elegy"),
             intro=0.5, inner=0.4, tenor=0.25))
_add(Profile("rachmaninoff", "Rachmaninoff", "russian", "russian",
             {"theme": ["sweep", "nocturne", "bells"], "contrast": ["sweep", "sweep16"],
              "climax": ["bells", "block"], "return": ["bells", "sweep"],
              "closing": ["bells", "block"]},
             pedal="harmony", dynamics=("pp", "ff"), climax_dynamic="fff", rubato=0.2,
             ornaments=0.05, octave_climax=True, bass_low=24, minor_bias=0.8,
             phrase="sentence",
             genres=("prelude", "etude-tableau", "elegie", "romance", "moment musical"),
             words={"theme": "cantabile", "contrast": "agitato",
                    "climax": "con passione", "return": "maestoso"},
             intro=0.75, lean="slow", inner=0.5, tenor=0.3))
_add(Profile("scriabin", "Scriabin", "russian", "russian",
             {"theme": ["sweep", "nocturne"], "contrast": ["sweep16"], "climax": ["bells"],
              "return": ["sweep"], "closing": ["sustained"]},
             pedal="harmony", dynamics=("pp", "f"), climax_dynamic="ff", rubato=0.25,
             octave_climax=True,
             intro=0.3, inner=0.3))
_add(Profile("debussy", "Debussy", "impressionist", "impressionist",
             {"theme": ["sustained", "nocturne"], "contrast": ["sweep"], "climax": ["block"],
              "return": ["sustained"], "closing": ["sustained"]},
             pedal="harmony", dynamics=("pp", "mf"), climax_dynamic="f", rubato=0.2,
             genres=("prelude", "arabesque", "reverie", "clair de lune"),
             words={"theme": "doux et expressif", "contrast": "un peu animé"},
             intro=0.5, language="fr", lean="slow", planing=True))
_add(Profile("ravel", "Ravel", "impressionist", "impressionist",
             {"theme": ["sustained", "sweep"], "contrast": ["sweep16"], "climax": ["block"],
              "return": ["sustained"], "closing": ["sustained"]},
             pedal="harmony", dynamics=("pp", "f"), climax_dynamic="f", rubato=0.15,
             intro=0.5, language="fr", planing=True))
_add(Profile("satie", "Satie", "impressionist", "impressionist",
             {"theme": ["waltz"], "contrast": ["waltz"], "climax": ["waltz"],
              "return": ["waltz"], "closing": ["sustained"]},
             pedal="harmony", dynamics=("pp", "p"), climax_dynamic="mf", rubato=0.1,
             words={"theme": "lent et douloureux"},
             intro=1.0, language="fr", lean="slow"))
_add(Profile("einaudi", "Einaudi", "film", "film",
             {"theme": ["nocturne"], "contrast": ["sweep16"], "climax": ["block"],
              "return": ["nocturne"], "closing": ["sustained"]},
             pedal="harmony", dynamics=("p", "f"), climax_dynamic="f", rubato=0.1,
             intro=0.8))
_add(Profile("film", "cinematic", "film", "film",
             {"theme": ["nocturne", "sustained"], "contrast": ["sweep"], "climax": ["block", "bells"],
              "return": ["nocturne"], "closing": ["sustained"]},
             pedal="harmony", dynamics=("p", "ff"), climax_dynamic="ff", rubato=0.12,
             octave_climax=True,
             intro=0.6))
_add(Profile("classical", "Classical", "classical", "classical",
             {"theme": ["alberti"], "contrast": ["repeated"], "climax": ["block"],
              "return": ["alberti"], "closing": ["block"]},
             pedal="sparse", rubato=0.06, phrase="period"))
_add(Profile("romantic", "Romantic", "romantic", "romantic",
             {"theme": ["nocturne"], "contrast": ["repeated"], "climax": ["block"],
              "return": ["nocturne"], "closing": ["block"]},
             pedal="harmony", rubato=0.15,
             intro=0.4, inner=0.3, tenor=0.2))

#: Composers without a profile of their own, and whose music theirs is like.
KIN = {
    "medtner": "rachmaninoff", "rachmaninov": "rachmaninoff", "rakhmaninov": "rachmaninoff",
    "arensky": "tchaikovsky", "glazunov": "tchaikovsky", "rimsky-korsakov": "tchaikovsky",
    "mussorgsky": "tchaikovsky", "borodin": "tchaikovsky", "glinka": "tchaikovsky",
    "fauré": "romantic", "faure": "romantic", "franck": "romantic", "saint-saëns": "romantic",
    "saint-saens": "romantic", "dvořák": "brahms", "dvorak": "brahms", "smetana": "brahms",
    "field": "chopin", "paderewski": "chopin", "moszkowski": "chopin", "godowsky": "liszt",
    "alkan": "liszt", "busoni": "liszt", "albeniz": "liszt", "granados": "chopin",
    "mahler": "brahms", "wagner": "romantic", "wolf": "schumann", "strauss": "brahms",
    "elgar": "brahms", "sibelius": "tchaikovsky", "janacek": "debussy", "fauré ": "romantic",
    "telemann": "bach", "rameau": "handel", "couperin": "scarlatti", "purcell": "handel",
    "corelli": "handel", "pachelbel": "bach", "cpe bach": "haydn", "hummel": "mozart",
    "czerny": "clementi", "field ": "chopin", "gershwin": "film", "joplin": "classical",
    "glass": "einaudi", "part": "einaudi", "pärt": "einaudi", "yiruma": "einaudi",
    "hisaishi": "film", "zimmer": "film", "williams": "film", "morricone": "film",
    "prokofiev": "rachmaninoff", "shostakovich": "rachmaninoff", "scriabine": "scriabin",
    "poulenc": "ravel", "chaminade": "romantic", "clara schumann": "schumann",
    "hensel": "mendelssohn", "fanny mendelssohn": "mendelssohn",
    "bartók": "liszt", "bartok": "liszt", "stravinsky": "ravel", "puccini": "romantic",
    "verdi": "romantic", "bellini": "chopin", "donizetti": "chopin", "rossini": "mozart",
    "bizet": "romantic", "massenet": "romantic", "gounod": "romantic", "bruckner": "brahms",
    "reger": "brahms", "nielsen": "brahms", "grainger": "grieg", "sinding": "grieg",
    "albinoni": "handel", "boccherini": "haydn", "gluck": "mozart", "salieri": "mozart",
    "weber": "schubert", "spohr": "mendelssohn", "hahn": "romantic", "boulanger": "debussy",
    "messiaen": "scriabin", "copland": "film", "barber": "romantic", "bernstein": "film",
    "max richter": "einaudi", "richter": "einaudi", "arnalds": "einaudi", "nyman": "einaudi",
    "sakamoto": "einaudi", "tiersen": "einaudi", "howard shore": "film", "horner": "film",
    "desplat": "film", "kapustin": "film", "mompou": "debussy", "satie": "satie",
    "lyadov": "tchaikovsky", "liadov": "tchaikovsky", "rubinstein": "tchaikovsky",
    "balakirev": "tchaikovsky", "rachmaninoff": "rachmaninoff", "schumann": "schumann",
    "arvo pärt": "einaudi", "arvo part": "einaudi", "philip glass": "einaudi",
    "john williams": "film", "hans zimmer": "film", "joe hisaishi": "film",
}

#: How a composer's name is written, where it is not simply capitalised.
_DISPLAY = {
    "fauré": "Fauré", "faure": "Fauré", "dvořák": "Dvořák", "dvorak": "Dvořák",
    "saint-saëns": "Saint-Saëns", "saint-saens": "Saint-Saëns", "bartók": "Bartók",
    "bartok": "Bartók", "janacek": "Janáček", "albeniz": "Albéniz", "pärt": "Pärt",
    "part": "Pärt", "arvo part": "Arvo Pärt", "arvo pärt": "Arvo Pärt",
    "rimsky-korsakov": "Rimsky-Korsakov", "cpe bach": "C. P. E. Bach",
    "clara schumann": "Clara Schumann", "fanny mendelssohn": "Fanny Mendelssohn",
    "max richter": "Max Richter", "howard shore": "Howard Shore", "philip glass": "Philip Glass",
    "john williams": "John Williams", "hans zimmer": "Hans Zimmer",
    "joe hisaishi": "Joe Hisaishi", "rachmaninov": "Rachmaninov", "rakhmaninov": "Rachmaninov",
    "scriabine": "Scriabin", "liadov": "Lyadov",
}

#: Names that are also ordinary words: taken as a composer only when the
#: request says so ("in the style of Glass", "like Field") or capitalises them.
_AMBIGUOUS = {"field", "field ", "glass", "part", "wolf", "williams", "hahn", "barber",
              "richter", "weber", "strauss", "horner", "reger", "shore"}
_CUES = ("style of", "manner of", "like", "by", "after", "à la", "a la", "vein of",
         "inspired by", "spirit of", "such as", "influenced by")
_GENERIC = {"classical", "romantic", "film"}


def named_composer(text: str) -> tuple[str, str] | None:
    """The composer a request names — any composer, those without a profile
    of their own writing through their nearest kin (Medtner through
    Rachmaninoff, Fauré through the Romantics) — as (profile, name as
    written). The first composer named wins."""
    import re
    if not text:
        return None
    low = text.lower()
    names = [k for k in PROFILES if k not in _GENERIC] + list(KIN)
    best: tuple[int, str] | None = None
    for name in sorted(set(n.strip() for n in names), key=len, reverse=True):
        for m in re.finditer(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", low):
            if name in _AMBIGUOUS or f"{name} " in _AMBIGUOUS:
                before = low[max(0, m.start() - 16):m.start()]
                written = text[m.start():m.end()]
                if not (any(before.rstrip().endswith(c) for c in _CUES) or
                        (written[:1].isupper() and m.start() > 0)):
                    continue
            if best is None or m.start() < best[0] or \
                    (m.start() == best[0] and len(name) > len(best[1])):
                best = (m.start(), name)
            break
    if best is None:
        return None
    name = best[1]
    target = name if name in PROFILES else KIN[name] if name in KIN else KIN.get(name + " ")
    if target is None:
        return None
    shown = PROFILES[name].display if name in PROFILES else \
        _DISPLAY.get(name, " ".join(w.capitalize() for w in name.split()))
    return target, shown


def profile(name: str | None) -> Profile:
    if not name:
        return PROFILES["romantic"]
    key = name.lower().strip()
    if key in PROFILES:
        return PROFILES[key]
    if key in KIN:
        return PROFILES[KIN[key]]
    for k, v in KIN.items():
        if k in key:
            return PROFILES[v]
    for k in PROFILES:
        if k in key:
            return PROFILES[k]
    return PROFILES["romantic"]


# ---------------------------------------------------------------------------
# tempo
# ---------------------------------------------------------------------------
#: The tempo a piece takes when the request doesn't name one, by genre and
#: character: (words, beats per minute of the notated beat).
_TEMPI: dict[str, dict[str, list[tuple[str, int]]]] = {
    "nocturne": {"slow": [("Lento", 52), ("Larghetto", 58), ("Lento sostenuto", 50)],
                 "lyrical": [("Andante cantabile", 66), ("Andante", 72), ("Larghetto", 60)],
                 "lively": [("Andante con moto", 84), ("Allegretto", 100)],
                 "stormy": [("Agitato", 104), ("Con fuoco", 112)]},
    "prelude": {"slow": [("Lento", 54), ("Largo", 48), ("Lento sostenuto", 50)],
                "lyrical": [("Andante cantabile", 66), ("Moderato", 80), ("Andante", 72)],
                "lively": [("Allegretto", 112), ("Allegro vivace", 144)],
                "stormy": [("Allegro agitato", 132), ("Presto", 160), ("Allegro appassionato", 138)]},
    "waltz": {"slow": [("Tempo di valse, lento", 112), ("Moderato", 120)],
              "lyrical": [("Tempo di valse", 138), ("Tempo giusto", 144)],
              "lively": [("Vivace", 168), ("Tempo di valse", 156)],
              "stormy": [("Molto vivace", 176)]},
    "mazurka": {"slow": [("Lento", 96), ("Mesto", 100)],
                "lyrical": [("Moderato", 126), ("Allegretto", 132)],
                "lively": [("Vivace", 152), ("Allegro non troppo", 144)],
                "stormy": [("Vivace", 160)]},
    "etude": {"slow": [("Lento ma non troppo", 60), ("Andante", 72)],
              "lyrical": [("Moderato", 96), ("Allegretto", 112)],
              "lively": [("Allegro", 132), ("Vivace", 152)],
              "stormy": [("Presto", 160), ("Allegro con fuoco", 144), ("Agitato", 138)]},
    "sonata": {"slow": [("Adagio", 60), ("Largo", 52)],
               "lyrical": [("Allegro moderato", 116), ("Andante", 76)],
               "lively": [("Allegro", 138), ("Allegro con spirito", 144)],
               "stormy": [("Allegro con brio", 152), ("Allegro appassionato", 144)]},
    "minuet": {"slow": [("Tempo di minuetto", 104)], "lyrical": [("Tempo di minuetto", 112)],
               "lively": [("Allegretto", 126)], "stormy": [("Allegro", 138)]},
    "invention": {"slow": [("Andante", 72)], "lyrical": [("Moderato", 88)],
                  "lively": [("Allegro", 112)], "stormy": [("Presto", 132)]},
    "rondo": {"slow": [("Andante", 76), ("Allegretto", 96)],
              "lyrical": [("Allegretto", 104), ("Allegro moderato", 112)],
              "lively": [("Allegro", 132), ("Allegro vivace", 144), ("Presto", 152)],
              "stormy": [("Allegro con fuoco", 144), ("Presto", 160)]},
    # a theme for variations is plain and unhurried, so its variations can
    # quicken and slow around it
    "variations": {"slow": [("Andante", 66), ("Andante sostenuto", 60)],
                   "lyrical": [("Andante", 76), ("Andante grazioso", 84), ("Allegretto", 96)],
                   "lively": [("Allegretto", 108), ("Allegro moderato", 116)],
                   "stormy": [("Allegro moderato", 112), ("Allegro", 126)]},
}
_TEMPI_FR = {
    "slow": [("Lent", 52), ("Très lent", 44), ("Lent et grave", 50)],
    "lyrical": [("Modéré", 72), ("Andantino", 80), ("Doucement soutenu", 66)],
    "lively": [("Animé", 116), ("Assez vif", 126)],
    "stormy": [("Très animé", 144), ("Tumultueux", 138)],
}
_TEMPI_DE = {
    "slow": [("Langsam", 56), ("Sehr langsam", 48)],
    "lyrical": [("Innig", 66), ("Nicht schnell", 72)],
    "lively": [("Lebhaft", 132), ("Frisch", 126)],
    "stormy": [("Sehr lebhaft", 152), ("Leidenschaftlich", 138)],
}
#: Character words from the request, grouped by the tempo they suggest.
_CHARACTER = {
    "slow": ("sad", "calm", "dark", "mysterious", "nostalgic"),
    "lyrical": ("romantic", "hopeful"),
    "lively": ("joyful", "playful", "triumphant"),
    "stormy": ("stormy", "dramatic"),
}


def tempo_class(character: str, prof: Profile) -> str:
    for cls, moods in _CHARACTER.items():
        if any(m in (character or "") for m in moods):
            return cls
    return prof.lean


#: Pieces whose name carries its tempo (in quarter notes; a compound metre
#: takes the dotted beat from it).
_GENRE_TEMPI = {
    "gigue": [("Allegro", 132), ("Presto", 150)],
    "sarabande": [("Lento", 54), ("Grave", 48), ("Largo", 52)],
    "gavotte": [("Allegretto", 100), ("Tempo di gavotta", 96)],
    "polonaise": [("Alla polacca", 92), ("Maestoso", 88), ("Allegro maestoso", 100)],
    "scherzo": [("Presto", 168), ("Vivace", 160), ("Allegro vivace", 152)],
    "barcarolle": [("Allegretto", 84), ("Andante", 76)],
    "berceuse": [("Andante", 76), ("Andantino", 80)],
    "lullaby": [("Andante", 72), ("Andantino", 78)],
    "siciliano": [("Andante", 72), ("Larghetto", 66)],
    "siciliana": [("Andante", 72), ("Larghetto", 66)],
    "march": [("Tempo di marcia", 108), ("Alla marcia", 112), ("Maestoso", 96)],
    "marche": [("Tempo di marcia", 108), ("Alla marcia", 112)],
    "tarantella": [("Presto", 176), ("Prestissimo", 184)],
    "toccata": [("Allegro", 132), ("Presto", 152)],
    "hymn": [("Andante maestoso", 72), ("Moderato", 80)],
}
_GENRE_CLASS = {"gigue": "lively", "sarabande": "slow", "gavotte": "lively",
                "polonaise": "stormy", "scherzo": "lively", "barcarolle": "lyrical",
                "berceuse": "slow", "lullaby": "slow", "siciliano": "lyrical",
                "siciliana": "lyrical", "march": "lively", "marche": "lively",
                "tarantella": "stormy", "toccata": "stormy", "hymn": "slow"}


def choose_tempo(prof: Profile, family: str, character: str, rng, genre: str = ""
                 ) -> tuple[str, int]:
    """Tempo words and a metronome mark in the composer's own language."""
    cls = tempo_class(character, prof)
    g = (genre or "").lower()
    named = next((k for k in _GENRE_TEMPI if k in g), None)
    if named and prof.language not in ("fr", "de") and not character:
        return rng.choice(_GENRE_TEMPI[named])
    if named and not character:
        cls = _GENRE_CLASS[named]
    if prof.name == "satie":
        return rng.choice([("Lent et douloureux", 66), ("Lent et triste", 60),
                           ("Lent et grave", 58)])
    if prof.language == "fr":
        return rng.choice(_TEMPI_FR[cls])
    if prof.language == "de":
        return rng.choice(_TEMPI_DE[cls])
    table = _TEMPI.get(family) or _TEMPI["prelude"]
    return rng.choice(table.get(cls) or table["lyrical"])
