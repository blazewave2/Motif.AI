"""Form: the shape of a whole piece, down to its phrases.

Each genre has its own architecture — a nocturne's song with a stormier
middle and an ornamented return, a waltz's chain of sixteen-bar strains, a
sonata exposition with its two key areas, a development and a
recapitulation, a Rachmaninoff prelude that builds to a climax where the
theme returns in octaves over tolling bells. The planner lays the piece out
as sections of 4- and 8-bar phrases, each with its key, its cadence, how
much energy it carries, which texture it uses, and — for every return —
which earlier phrase it brings back, so the music is heard to come home.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from ..theory.pitch import Key
from .profiles import Profile


@dataclass
class PhraseSpec:
    section: str                 # A, B, A', coda …
    role: str                    # theme | contrast | climax | return | closing | intro | transition | development
    kind: str                    # sentence | antecedent | consequent | continuation | closing | intro | development
    bars: int
    key: Key
    cadence: str                 # PAC | IAC | HC | DC | plagal | none
    energy: float                # 0 calm .. 1 climactic
    texture: str
    recall: int | None = None    # index of an earlier phrase whose melody returns
    variation: str = ""          # how a return differs: ornament | octaves | softer | fuller
    words: str = ""              # expressive marking at the start of the phrase
    tempo_scale: float = 1.0
    new_section: bool = False    # the first phrase of a section
    #: In a concerto, who plays: tutti (everyone, the orchestra with the tune),
    #: solo (the piano alone), solo_lead (the piano with the tune, the
    #: orchestra accompanying), orch_lead (the orchestra with the tune, the
    #: piano accompanying) or cadenza.
    forces: str = ""
    register: str = ""           # "tenor": the tune moves to the left hand, under the harmony
    tempo_words: str = ""        # a new tempo at the start of the section (Adagio, Allegro …)


@dataclass
class FormPlan:
    genre: str
    phrases: list[PhraseSpec] = field(default_factory=list)

    @property
    def bars(self) -> int:
        return sum(p.bars for p in self.phrases)


def _related(key: Key, which: str) -> Key:
    minor = key.is_minor
    if which == "relative":
        return key.relative
    if which == "dominant":
        return key.dominant_key() if not minor else Key(key.relative.tonic, "major")
    if which == "subdominant":
        return key.subdominant_key()
    if which == "parallel":
        return key.parallel
    if which == "flat6":
        # A major third below: the Romantics' favourite remote key
        return key.transposed(-4) if not minor else Key(key.relative.transposed(-4).tonic, "major")
    if which == "submediant":
        rel = key.relative
        return rel if not minor else Key(key.transposed(8).tonic, "major")
    return key


def plan_form(genre: str, prof: Profile, key: Key, target_bars: int,
              rng: random.Random, character: str = "", **options) -> FormPlan:
    """Lay out a piece of about ``target_bars`` bars in ``genre`` (``options``
    say more about forms that take them: how many variations, how long a
    theme, or — as ``scope`` — the part of a piece that was asked for)."""
    genre = (genre or "").lower()
    if options.get("scope"):
        plan = _fragment(prof, key, target_bars, rng, character, **options)
        _dress_for_genre(plan, genre, prof)
        return plan
    fn = _TEMPLATES.get(_genre_family(genre), _ternary)
    plan = fn(prof, key, max(8, target_bars), rng, character, **options)
    plan.genre = genre or plan.genre
    _dress_for_genre(plan, genre, prof)
    if "fugue" in genre or "fugato" in genre:
        # a fugue answers its subject at the fifth, in the dominant
        for p in plan.phrases:
            if p.texture == "imitation":
                p.texture = "fugato"
    _add_intro(plan, prof, target_bars, rng)
    return plan


#: Accompaniments a named kind of piece has, by role (the rest as the
#: composer's own): the polonaise rhythm, the march bass, a toccata's
#: unbroken figuration.
_GENRE_TEXTURES = {
    "polonaise": {"theme": "polonaise", "return": "polonaise", "climax": "polonaise",
                  "closing": "polonaise"},
    "march": {"theme": "march", "return": "march", "contrast": "march", "closing": "march"},
    "marche": {"theme": "march", "return": "march", "contrast": "march", "closing": "march"},
    "sarabande": {"theme": "block", "return": "block"},
    "hymn": {"theme": "block", "return": "block", "contrast": "block", "closing": "block"},
    "scherzo": {"theme": "waltz", "return": "waltz"},
    "gavotte": {"theme": "block", "return": "block"},
}


def _dress_for_genre(plan: FormPlan, genre: str, prof: Profile) -> None:
    for name, by_role in _GENRE_TEXTURES.items():
        if name in genre:
            for p in plan.phrases:
                if p.role in by_role and p.kind != "intro":
                    p.texture = by_role[p.role]
            break
    if "toccata" in genre:
        for p in plan.phrases:
            if p.role != "intro":
                p.texture = "walking" if prof.harmony == "baroque" else "sweep16"
    if "polonaise" in genre or "march" in genre or "marche" in genre:
        # a polonaise and a march are stately, not dreamy
        for p in plan.phrases:
            if p.role in ("theme", "return"):
                p.energy = max(p.energy, 0.62)
                if p.new_section and p.words in ("", "dolce", "cantabile", "espressivo"):
                    p.words = "maestoso" if "polonaise" in genre else "marcato"


#: Textures that can set the scene on their own before the tune comes in.
_INTRO_TEXTURES = ("nocturne", "sweep", "sweep16", "bells", "repeated", "waltz", "sustained")


def _add_intro(plan: FormPlan, prof: Profile, target_bars: int, rng: random.Random) -> None:
    """A bar or two of accompaniment alone, as so many Romantic pieces begin."""
    if not plan.phrases or plan.genre in ("concerto", "continuation", "invention") or \
            _genre_family(plan.genre) == "variations":
        return
    first = plan.phrases[0]
    if first.role != "theme" or first.texture not in _INTRO_TEXTURES or \
            rng.random() >= prof.intro:
        return
    n = 2 if (target_bars >= 40 and rng.random() < 0.5) else 1
    for p in plan.phrases:
        if p.recall is not None:
            p.recall += 1
    plan.phrases.insert(0, PhraseSpec("intro", "intro", "intro", n, first.key, "none",
                                      max(0.2, first.energy - 0.1), first.texture,
                                      new_section=True))


def genre_family(genre: str) -> str:
    return _genre_family((genre or "").lower())


#: Names of pieces a request may ask for, most specific first.
GENRE_WORDS = (
    "etude-tableau", "étude-tableau", "etude tableau", "song without words", "moment musical",
    "concerto", "theme and variations", "variations", "variation", "rondo", "rondeau",
    "lyric piece", "gymnopédie", "gymnopedie", "gnossienne", "liebestraum", "consolation",
    "nocturne", "prelude", "prélude", "waltz", "valse", "mazurka", "polonaise", "sonatina",
    "sonata", "minuet", "menuet", "gavotte", "sarabande", "gigue", "invention", "fugue",
    "toccata", "etude", "étude", "study", "romance", "elegie", "élégie", "elegy", "berceuse",
    "barcarolle", "reverie", "rêverie", "intermezzo", "impromptu", "ballade", "rhapsody",
    "fantasy", "fantasia", "scherzo", "arabesque", "lied", "song",
    "march", "marche", "tarantella", "siciliano", "siciliana", "lullaby", "hymn",
    "humoresque", "fairy tale", "skazka", "bagatelle", "novelette", "caprice", "capriccio",
    "serenade", "idyll", "album leaf", "albumblatt",
)


_NOT_A_GENRE = re.compile(r"\s+(film|movie|game|scene|story|novel|world|series|show|trailer|"
                          r"soundtrack|book|land|tale\b)")


def detect_genre(text: str) -> str | None:
    """The kind of piece a request names, if it names one ("a fantasy film"
    names a film, not a fantasia)."""
    t = (text or "").lower()
    for w in GENRE_WORDS:
        i = t.find(w)
        while i >= 0:
            if not _NOT_A_GENRE.match(t, i + len(w)):
                return w
            i = t.find(w, i + 1)
    return None


def detect_scope(text: str) -> str | None:
    """The part of a piece a request asks for, when it asks for only a part:
    a motif, a phrase, a theme (or melody, or tune), an introduction, a
    cadenza or a chord progression."""
    import re
    t = (text or "").lower()
    if re.search(r"\b(chord progression|progression|chord sequence|sequence of chords)\b", t):
        return "progression"
    if "cadenza" in t and "concerto" not in t:
        return "cadenza"
    if re.search(r"\b(introduction|intro)\b", t) and not \
            re.search(r"\bwith (an? |the )?(short |brief |slow )?(introduction|intro)\b", t):
        return "introduction"
    if re.search(r"\b(motif|motive|musical idea|melodic idea|melodic cell)\b", t) and not \
            re.search(r"\b(on|from|using|around|based on|built on|develop|out of)\s+"
                      r"(an?|this|the|my)?\s*(\w+\s+)?(motif|motive)", t):
        return "motif"
    named = detect_genre(t)
    if named and named not in ("song",):
        return None
    if re.search(r"\bphrase\b", t):
        return "phrase"
    if re.search(r"\b(theme|melody|tune)\b", t) and not \
            re.search(r"variation|on a theme|theme (of|by|from)|themes? and|theme song", t):
        return "theme"
    return None


#: Words asking for the tune alone.
_MELODY_ONLY = ("no accompaniment", "without accompaniment", "unaccompanied", "melody only",
                "only the melody", "just the melody", "just a melody", "melody alone",
                "tune alone", "just the tune", "just a tune", "only a melody", "single line",
                "melodic line only", "a cappella", "no left hand", "without a left hand",
                "right hand only", "just the right hand")


def melody_only(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in _MELODY_ONLY)


#: How long each part of a piece is when the request doesn't say.
SCOPE_BARS = {"motif": 4, "phrase": 8, "theme": 8, "introduction": 4, "cadenza": 8,
              "progression": 8}


#: Usual metres for each family of pieces, with how often each is chosen.
_METRES = {
    "waltz": [((3, 4), 1)], "mazurka": [((3, 4), 1)], "minuet": [((3, 4), 1)],
    "nocturne": [((4, 4), 5), ((12, 8), 2), ((6, 8), 2), ((3, 4), 2)],
    "prelude": [((4, 4), 6), ((3, 4), 3), ((6, 8), 1)],
    "etude": [((4, 4), 6), ((2, 4), 2), ((6, 8), 1)],
    "sonata": [((4, 4), 6), ((3, 4), 2), ((2, 4), 1)],
    "invention": [((4, 4), 6), ((3, 4), 2)],
    "rondo": [((2, 4), 4), ((6, 8), 3), ((4, 4), 3)],
}


#: Pieces whose name fixes their metre, whatever family they belong to.
_GENRE_METRES = {
    "gigue": [((6, 8), 3), ((12, 8), 2)], "barcarolle": [((6, 8), 2), ((12, 8), 3)],
    "berceuse": [((6, 8), 1)], "lullaby": [((6, 8), 2), ((3, 4), 1)],
    "siciliano": [((6, 8), 2), ((12, 8), 1)], "siciliana": [((6, 8), 2), ((12, 8), 1)],
    "sarabande": [((3, 4), 1)], "gavotte": [((4, 4), 1)], "polonaise": [((3, 4), 1)],
    "scherzo": [((3, 4), 1)], "march": [((4, 4), 2), ((2, 4), 1)],
    "marche": [((4, 4), 2), ((2, 4), 1)], "tarantella": [((6, 8), 1)],
    "toccata": [((4, 4), 2), ((2, 4), 1)], "hymn": [((4, 4), 2), ((3, 4), 1)],
}


def genre_metres(genre: str) -> list | None:
    g = (genre or "").lower()
    return next((v for k, v in _GENRE_METRES.items() if k in g), None)


def choose_metre(family: str, prof: Profile, rng: random.Random, genre: str = ""
                 ) -> tuple[int, int]:
    named = genre_metres(genre)
    if named:
        metres, weights = zip(*named)
        return rng.choices(metres, weights)[0]
    if prof.name == "satie":
        return (3, 4)
    opts = _METRES.get(family, _METRES["prelude"])
    if prof.melody in ("classical", "baroque"):
        opts = [o for o in opts if o[0][1] == 4] or opts
    metres, weights = zip(*opts)
    return rng.choices(metres, weights)[0]


def _genre_family(genre: str) -> str:
    for fam, words in (
        ("continuation", ("continuation",)),
        ("concerto", ("concerto",)),
        ("variations", ("variation",)),
        ("rondo", ("rondo", "rondeau")),
        ("waltz", ("waltz", "valse", "ländler")),
        ("mazurka", ("mazurka", "polonaise")),
        ("sonata", ("sonata", "sonatina", "first movement")),
        ("minuet", ("minuet", "menuet", "gavotte", "bourrée", "sarabande", "gigue", "march",
                    "marche")),
        ("invention", ("invention", "fugue", "partita", "sinfonia")),
        ("etude", ("etude", "étude", "study", "toccata", "etude-tableau", "tarantella")),
        ("nocturne", ("nocturne", "romance", "song", "elegie", "élégie", "elegy", "lied",
                      "berceuse", "barcarolle", "reverie", "rêverie", "consolation",
                      "liebestraum", "lyric", "intermezzo", "impromptu", "moment",
                      "siciliano", "siciliana", "lullaby", "hymn", "serenade", "idyll",
                      "album leaf", "albumblatt")),
        ("prelude", ("prelude", "prélude", "ballade", "rhapsody", "fantasy", "fantasia",
                     "scherzo", "piece", "humoresque", "fairy tale", "skazka", "bagatelle",
                     "novelette", "caprice", "capriccio", "")),
    ):
        if any(w and w in genre for w in words):
            return fam
    return "prelude"


def _phr(section, role, kind, bars, key, cadence, energy, texture, **kw) -> PhraseSpec:
    return PhraseSpec(section, role, kind, bars, key, cadence, energy, texture, **kw)


def _tex(prof: Profile, role: str, rng: random.Random, choice: dict) -> str:
    """One texture per role for the whole piece, so the music keeps its
    identity."""
    if role not in choice:
        options = prof.textures.get(role) or prof.textures.get("theme") or ["block"]
        choice[role] = rng.choice(options)
    return choice[role]


def _ternary(prof: Profile, key: Key, bars: int, rng: random.Random, character: str, **_
             ) -> FormPlan:
    """ABA' with a coda: preludes, romances, elegies, most character pieces."""
    tx: dict = {}
    minor = key.is_minor
    b_key = _related(key, rng.choice(
        ["relative", "relative", "submediant"] if minor else ["dominant", "submediant", "flat6",
                                                             "parallel"]))
    # proportions: A 40%, B 30%, A' 25%, coda 5%
    a_bars = _phrase_bars(bars * 0.4)
    b_bars = _phrase_bars(bars * 0.3)
    r_bars = _phrase_bars(bars * 0.22)
    coda = 4 if bars >= 24 else 2
    short = bars < 30          # no room for a passage leading back
    phrases: list[PhraseSpec] = []
    words = prof.words
    # A: a period (antecedent + consequent) or a sentence
    phrases += _theme_group("A", "theme", key, a_bars, prof, rng, tx, energy=0.45,
                            words=words.get("theme", ""), short=bars <= 20)
    # B: contrasting key, more motion, building to the climax

    n_b = max(1, b_bars // 8) if b_bars >= 8 else 1
    # sometimes the middle section sings in the tenor, under repeated chords
    tenor = rng.random() < prof.tenor and not short
    for i in range(n_b):
        last = i == n_b - 1
        phrases.append(_phr("B", "contrast", "continuation" if i else "sentence",
                            8 if b_bars >= 8 else b_bars, b_key,
                            "HC" if last else "PAC", 0.55 + 0.2 * i / n_b,
                            "tenor" if tenor else _tex(prof, "contrast", rng, tx),
                            new_section=(i == 0), register="tenor" if tenor else "",
                            words=("sotto voce, cantando" if tenor else
                                   words.get("contrast", "")) if i == 0 else ""))
    # retransition back to the tonic
    if not short:
        phrases.append(_phr("B", "transition", "development", 4, key, "HC", 0.85,
                            _tex(prof, "contrast", rng, tx)))
    # A': the theme returns — at its climax for Rachmaninoff and Liszt,
    # ornamented and tender for Chopin
    grand = prof.octave_climax
    theme_idx = [i for i, p in enumerate(phrases) if p.section == "A"]
    if bars <= 20:
        theme_idx = theme_idx[-1:]          # a short piece brings back only its close
    for j, src in enumerate(theme_idx[:max(1, r_bars // 8)]):
        p = phrases[src]
        last = j == max(1, r_bars // 8) - 1
        phrases.append(_phr("A'", "return" if not grand else "climax",
                            p.kind, p.bars, key, "PAC" if last else p.cadence,
                            0.95 if grand else 0.5,
                            _tex(prof, "climax" if grand else "return", rng, tx),
                            recall=src, variation="octaves" if grand else
                            ("planing" if prof.planing else "ornament"),
                            new_section=(j == 0),
                            words=words.get("climax" if grand else "return", "")))
    # the return's cadence is sometimes evaded — a deceptive cadence — and the
    # music has to find its way home again before the coda
    last = phrases[-1]
    if not short and last.section == "A'" and prof.harmony in ("russian", "romantic") and \
            rng.random() < 0.5:
        last.cadence = "DC"
        phrases.append(_phr("A'", "closing", "closing", 4, key, "PAC",
                            max(0.6, last.energy - 0.1), last.texture,
                            variation=last.variation))
    phrases.append(_phr("coda", "closing", "closing", coda, key, "plagal" if
                        prof.harmony in ("russian", "romantic") else "PAC", 0.25,
                        _tex(prof, "closing", rng, tx), new_section=True))
    return FormPlan("ternary", phrases)


def _theme_group(section: str, role: str, key: Key, bars: int, prof: Profile,
                 rng: random.Random, tx: dict, energy: float, words: str = "",
                 short: bool = False) -> list[PhraseSpec]:
    out: list[PhraseSpec] = []
    tex = _tex(prof, role, rng, tx)
    if short and bars <= 8:
        # a small period: four bars that ask, four that answer
        return [_phr(section, role, "antecedent", 4, key, "HC", energy, tex, new_section=True,
                     words=words),
                _phr(section, role, "consequent", 4, key, "PAC", energy, tex)]
    if bars >= 16 and prof.phrase == "period":
        out.append(_phr(section, role, "antecedent", 8, key, "HC", energy, tex,
                        new_section=True, words=words))
        out.append(_phr(section, role, "consequent", 8, key, "PAC", energy + 0.05, tex,
                        recall=None))
        bars -= 16
    elif bars >= 16:
        out.append(_phr(section, role, "sentence", 8, key, "HC", energy, tex,
                        new_section=True, words=words))
        out.append(_phr(section, role, "consequent", 8, key, "PAC", energy + 0.08, tex))
        bars -= 16
    elif bars >= 8:
        kind = "antecedent" if prof.phrase == "period" else "sentence"
        out.append(_phr(section, role, kind, 8, key, "PAC", energy, tex, new_section=True,
                        words=words))
        bars -= 8
    else:
        out.append(_phr(section, role, "antecedent", 4, key, "HC", energy, tex,
                        new_section=True, words=words))
        out.append(_phr(section, role, "consequent", 4, key, "PAC", energy, tex))
        bars = 0
    while bars >= 8:
        out.append(_phr(section, role, "continuation", 8, key, "PAC", energy + 0.1, tex))
        bars -= 8
    return out


def _phrase_bars(x: float) -> int:
    """Round a section length to whole 8-bar phrases (4 when short)."""
    if x < 6:
        return 4
    return max(8, int(round(x / 8)) * 8)


def _waltz(prof: Profile, key: Key, bars: int, rng: random.Random, character: str, **_
           ) -> FormPlan:
    tx: dict = {"theme": "waltz", "contrast": "waltz", "return": "waltz", "closing": "waltz"}
    b_key = _related(key, "relative" if key.is_minor else rng.choice(["dominant",
                                                                      "subdominant"]))
    phrases = []
    phrases += _theme_group("A", "theme", key, 16, prof, rng, tx, 0.5, prof.words.get("theme", ""))
    phrases += _theme_group("B", "contrast", b_key, 16, prof, rng, tx, 0.65)
    for p in list(phrases[:2]):
        phrases.append(_phr("A'", "return", p.kind, p.bars, key, p.cadence, 0.55, "waltz",
                            recall=phrases.index(p), variation="ornament",
                            new_section=(p is phrases[0])))
    phrases.append(_phr("coda", "closing", "closing", 8 if bars >= 48 else 4, key, "PAC", 0.6,
                        "waltz", new_section=True))
    return FormPlan("waltz", phrases)


def _mazurka(prof: Profile, key: Key, bars: int, rng: random.Random, character: str, **_
             ) -> FormPlan:
    plan = _waltz(prof, key, bars, rng, character)
    plan.genre = "mazurka"
    return plan


def _sonata(prof: Profile, key: Key, bars: int, rng: random.Random, character: str, **_
            ) -> FormPlan:
    """An exposition with two key areas, a development and a recapitulation."""
    tx: dict = {}
    s_key = _related(key, "dominant" if not key.is_minor else "relative")
    ph: list[PhraseSpec] = []
    ph += _theme_group("P", "theme", key, 8, prof, rng, tx, 0.55)
    ph.append(_phr("TR", "transition", "development", 4, key, "HC", 0.7,
                   _tex(prof, "contrast", rng, tx)))
    ph[-1].key = s_key
    s_start = len(ph)
    ph += _theme_group("S", "contrast", s_key, 8, prof, rng, tx, 0.5)
    ph.append(_phr("K", "closing", "closing", 4, s_key, "PAC", 0.65,
                   _tex(prof, "closing", rng, tx)))
    dev_key = _related(key, "relative" if not key.is_minor else "subdominant")
    ph.append(_phr("Dev", "development", "development", 8, dev_key, "HC", 0.85,
                   _tex(prof, "contrast", rng, tx), new_section=True))
    ph.append(_phr("Dev", "transition", "development", 4, key, "HC", 0.9,
                   _tex(prof, "contrast", rng, tx)))
    ph.append(_phr("P'", "return", ph[0].kind, ph[0].bars, key, "PAC", 0.55, ph[0].texture,
                   recall=0, new_section=True))
    ph.append(_phr("S'", "return", ph[s_start].kind, ph[s_start].bars, key, "PAC", 0.55,
                   ph[s_start].texture, recall=s_start, variation="transpose"))
    ph.append(_phr("coda", "closing", "closing", 4, key, "PAC", 0.6,
                   _tex(prof, "closing", rng, tx), new_section=True))
    return FormPlan("sonata", ph)


def _minuet(prof: Profile, key: Key, bars: int, rng: random.Random, character: str, **_
            ) -> FormPlan:
    tx: dict = {}
    tex = _tex(prof, "theme", rng, tx)
    other = _related(key, "dominant" if not key.is_minor else "relative")
    ph = [
        _phr("A", "theme", "antecedent", 4, key, "HC", 0.5, tex, new_section=True),
        _phr("A", "theme", "consequent", 4, other, "PAC", 0.55, tex),
        _phr("B", "contrast", "continuation", 4, other, "HC", 0.6, tex, new_section=True),
        _phr("A'", "return", "consequent", 4, key, "PAC", 0.5, tex, recall=0),
    ]
    if bars >= 32:
        ph += [
            _phr("Trio", "contrast", "antecedent", 4, _related(key, "subdominant"), "HC", 0.45,
                 _tex(prof, "contrast", rng, tx), new_section=True, words="Trio"),
            _phr("Trio", "contrast", "consequent", 4, _related(key, "subdominant"), "PAC", 0.45,
                 _tex(prof, "contrast", rng, tx)),
            _phr("A''", "return", "antecedent", 4, key, "HC", 0.5, tex, recall=0,
                 new_section=True),
            _phr("A''", "return", "consequent", 4, key, "PAC", 0.55, tex, recall=3),
        ]
    return FormPlan("minuet", ph)


def _invention(prof: Profile, key: Key, bars: int, rng: random.Random, character: str, **_
               ) -> FormPlan:
    tx: dict = {}
    tex = _tex(prof, "theme", rng, tx)
    other = _related(key, "dominant" if not key.is_minor else "relative")
    # the subject alone, then answered in the other hand an octave lower
    lead = "imitation" if tex == "walking" else tex
    ph = [
        _phr("A", "theme", "sentence", 8, key, "HC", 0.5, lead, new_section=True),
        _phr("A", "development", "continuation", 8, other, "PAC", 0.6, tex),
        _phr("B", "development", "development", 8, _related(key, "submediant"), "PAC", 0.7, tex),
        _phr("A'", "return", "sentence", 8, key, "PAC", 0.6, lead, recall=0),
    ]
    return FormPlan("invention", ph)


def _etude(prof: Profile, key: Key, bars: int, rng: random.Random, character: str, **_
           ) -> FormPlan:
    plan = _ternary(prof, key, bars, rng, character)
    for p in plan.phrases:
        if p.role in ("theme", "return", "contrast", "climax", "transition"):
            p.texture = "sweep16" if prof.name not in ("bach",) else p.texture
            p.energy = min(1.0, p.energy + 0.15)
    plan.genre = "etude"
    return plan


def _continuation(prof: Profile, key: Key, bars: int, rng: random.Random, character: str, **_
                  ) -> FormPlan:
    """Carrying on from a piece that is already written: its theme developed
    away from home, a passage leading back, the theme restated and closed,
    and a coda."""
    tx: dict = {}
    ph: list[PhraseSpec] = []
    away = _related(key, "relative" if key.is_minor else rng.choice(["dominant", "submediant"]))
    if bars >= 24:
        ph.append(_phr("C", "development", "development", 8, away, "HC", 0.65,
                       _tex(prof, "contrast", rng, tx), new_section=True))
        ph.append(_phr("C", "transition", "development", 4, key, "HC", 0.8,
                       _tex(prof, "contrast", rng, tx)))
        ph.append(_phr("A", "return", "consequent", 8, key, "PAC", 0.6,
                       _tex(prof, "return", rng, tx), new_section=True))
        ph.append(_phr("coda", "closing", "closing", 4, key,
                       "plagal" if prof.harmony in ("russian", "romantic") else "PAC", 0.3,
                       _tex(prof, "closing", rng, tx), new_section=True))
    else:
        ph.append(_phr("C", "development", "continuation", 8, key, "HC", 0.6,
                       _tex(prof, "contrast", rng, tx), new_section=True))
        ph.append(_phr("coda", "closing", "closing", max(4, min(8, bars - 8)), key, "PAC", 0.35,
                       _tex(prof, "closing", rng, tx)))
    return FormPlan("continuation", ph)


def _concerto(prof: Profile, key: Key, bars: int, rng: random.Random, character: str, **_
              ) -> FormPlan:
    """A concerto first movement: an opening, the first theme, a passage to
    the second key and a lyrical second theme passed between piano and
    orchestra, a development in dialogue, a return at the climax, a cadenza
    for the piano alone and a coda for everyone."""
    tx: dict = {}
    romantic = prof.harmony in ("russian", "romantic", "film")
    second = _related(key, "relative" if key.is_minor else "dominant")
    dev = _related(key, "subdominant" if key.is_minor else "relative")
    words = prof.words
    ph: list[PhraseSpec] = []
    if romantic:
        # the piano alone, tolling chords that grow into the first tutti
        ph.append(_phr("intro", "intro", "intro", 4 if bars >= 80 else 2, key, "HC", 0.5,
                       "bells", new_section=True, forces="solo"))
        lead_tex = rng.choice(["sweep", "sweep16"]) if prof.octave_climax else \
            _tex(prof, "theme", rng, tx)
        ph.append(_phr("P", "theme", "sentence", 8, key, "HC", 0.6, lead_tex, new_section=True,
                       forces="orch_lead", words=words.get("theme", "")))
        ph.append(_phr("P", "theme", "consequent", 8, key, "PAC", 0.65, lead_tex,
                       forces="orch_lead"))
    else:
        # the orchestra's ritornello, then the soloist enters with the theme
        tex = _tex(prof, "theme", rng, tx)
        ph.append(_phr("R", "theme", "sentence", 8, key, "PAC", 0.65, tex, new_section=True,
                       forces="tutti"))
        ph.append(_phr("P", "return", "sentence", 8, key, "HC", 0.5, tex, recall=0,
                       new_section=True, forces="solo_lead"))
    ph.append(_phr("TR", "transition", "development", 4, second, "HC", 0.7,
                   _tex(prof, "contrast", rng, tx), forces="solo"))
    stex = _tex(prof, "return", rng, tx) if romantic else _tex(prof, "theme", rng, tx)
    s_idx = len(ph)
    ph.append(_phr("S", "contrast", "sentence", 8, second, "PAC", 0.5, stex, new_section=True,
                   forces="solo_lead", words="espressivo" if romantic else ""))
    if bars >= 80:
        ph.append(_phr("S", "contrast", "sentence", 8, second, "PAC", 0.65, stex, recall=s_idx,
                       forces="orch_lead"))
    ph.append(_phr("Dev", "development", "development", 8, dev, "HC", 0.7,
                   _tex(prof, "contrast", rng, tx), new_section=True, forces="tutti"))
    if bars >= 96:
        ph.append(_phr("Dev", "development", "development", 8, second, "HC", 0.8,
                       _tex(prof, "contrast", rng, tx), forces="solo"))
    ph.append(_phr("Dev", "transition", "development", 4, key, "HC", 0.88,
                   _tex(prof, "contrast", rng, tx), forces="tutti"))
    first_theme = next(i for i, p in enumerate(ph) if p.role == "theme")
    ph.append(_phr("P'", "climax", ph[first_theme].kind, 8, key, "PAC", 0.97,
                   _tex(prof, "climax", rng, tx), recall=first_theme,
                   variation="octaves" if prof.octave_climax else "", new_section=True,
                   forces="tutti", words=words.get("climax", "")))
    ph.append(_phr("Cad", "cadenza", "development", 8 if bars >= 96 else 4, key, "HC", 0.9,
                   "sustained" if prof.harmony != "baroque" else "walking",
                   new_section=True, forces="cadenza", variation="runs", words="Cadenza"))
    ph.append(_phr("coda", "closing", "closing", 4, key, "PAC", 0.95,
                   _tex(prof, "climax", rng, tx), new_section=True, forces="tutti"))
    return FormPlan("concerto", ph)


def _rondo(prof: Profile, key: Key, bars: int, rng: random.Random, character: str, **_
           ) -> FormPlan:
    """A refrain that keeps coming home between episodes — A B A C A and a
    coda. The refrain is a period in the home key; the first episode moves
    to the dominant (the relative major in minor) with a theme of its own,
    the second somewhere darker with another; each episode leads back over
    a dominant pedal, and the refrain's last return is its fullest."""
    tx: dict = {}
    minor = key.is_minor
    big = bars >= 72
    words = prof.words
    b_key = _related(key, "relative" if minor else "dominant")
    c_key = _related(key, "subdominant" if minor else rng.choice(["relative", "parallel"]))
    ph: list[PhraseSpec] = []
    ph += _theme_group("A", "theme", key, 16 if big else 8, prof, rng, tx, 0.55,
                       words=words.get("theme", ""), short=not big)
    refrain = list(range(len(ph)))
    ctex = _tex(prof, "contrast", rng, tx)
    for section, ekey, energy in (("B", b_key, 0.6), ("C", c_key, 0.7)):
        ph.append(_phr(section, "contrast", "sentence", 8, ekey, "PAC", energy, ctex,
                       new_section=True, words=words.get("contrast", "") if section == "C"
                       else ""))
        if big:
            ph.append(_phr(section, "contrast", "continuation", 8, ekey, "PAC", energy + 0.05,
                           ctex))
        ph.append(_phr(section, "transition", "development", 4, key, "HC", energy + 0.15,
                       ctex))
        last_return = section == "C"
        for j, src in enumerate(refrain):
            p = ph[src]
            variation = ("octaves" if prof.octave_climax else "ornament") if last_return \
                else ("ornament" if prof.ornaments >= 0.2 else "")
            ph.append(_phr("A'" if not last_return else "A''",
                           "climax" if last_return and prof.octave_climax else "return",
                           p.kind, p.bars, key, p.cadence, 0.8 if last_return else 0.55,
                           _tex(prof, "climax" if last_return and prof.octave_climax
                                else "return", rng, tx),
                           recall=src, variation=variation, new_section=(j == 0)))
    ph.append(_phr("coda", "closing", "closing", 8 if big else 4, key, "PAC", 0.75,
                   _tex(prof, "closing", rng, tx), new_section=True))
    return FormPlan("rondo", ph)


def _fragment(prof: Profile, key: Key, bars: int, rng: random.Random, character: str,
              scope: str = "theme", **_) -> FormPlan:
    """Part of a piece, as asked: a motif, a phrase, a theme, an
    introduction, a cadenza or a chord progression — each complete in
    itself and ready to be built on."""
    tx: dict = {}
    tex = _tex(prof, "theme", rng, tx)
    words = prof.words.get("theme", "")
    ph: list[PhraseSpec] = []
    if scope == "motif":
        ph.append(_phr("A", "theme", "motif", max(1, min(bars, 8)), key,
                       "none" if bars <= 2 else "PAC", 0.5, tex, new_section=True,
                       words=words))
    elif scope == "phrase" and bars <= 8:
        ph.append(_phr("A", "theme", "sentence", max(2, bars), key, "PAC", 0.5, tex,
                       new_section=True, words=words))
    elif scope in ("phrase", "theme"):
        ph += _theme_group("A", "theme", key, max(4, bars), prof, rng, tx, 0.5, words=words,
                           short=bars <= 8)
    elif scope == "introduction":
        if bars >= 6:
            ph.append(_phr("intro", "intro", "intro", 2, key, "none", 0.35,
                           tex if tex in _INTRO_TEXTURES else "sustained", new_section=True))
        ph.append(_phr("A", "theme", "antecedent", bars - 2 if bars >= 6 else max(2, bars),
                       key, "HC", 0.45, tex, new_section=not ph, words=words))
    elif scope == "cadenza":
        ph.append(_phr("Cad", "cadenza", "development", max(4, bars), key, "HC", 0.9,
                       "sustained" if prof.harmony != "baroque" else "walking",
                       new_section=True, variation="runs", words="Cadenza"))
    else:   # a chord progression
        ph.append(_phr("A", "theme", "progression", max(2, bars), key, "PAC", 0.5, "chorale",
                       new_section=True))
    return FormPlan(scope, ph)


#: The kinds of variation each idiom reaches for, in the order a set uses
#: them: the first is always a figuration, the last the finale.
_PROGRAMMES = {
    "classical": ["figural", "accomp", "minore", "triplets", "tenor", "adagio", "finale"],
    "baroque": ["figural", "walking", "minore", "triplets", "finale"],
    "romantic": ["triplets", "tenor", "agitato", "minore", "lento", "finale"],
}

_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]

_THEME_NAME = {"it": "Tema", "de": "Thema", "fr": "Thème"}


def _choose_variations(programme: list[str], n: int) -> list[str]:
    """``n`` kinds of variation from a programme: the first figuration, the
    change of mode near the middle, the slow variation just before the
    finale, and the finale last."""
    first, last = programme[0], programme[-1]
    slow = next((k for k in programme if k in ("adagio", "lento")), None)
    middle = [k for k in programme[1:-1] if k != slow]
    body: list[str] = []
    room = n - 2 - (1 if slow and n >= 5 else 0)
    pool = list(middle)
    while len(body) < room:
        kind = pool[len(body) % len(pool)]
        # the change of mode happens once
        body.append(kind if kind != "minore" or "minore" not in body else pool[0])
    if "minore" in programme and "minore" not in body and room >= 1:
        body[len(body) // 2] = "minore"
    out = [first] + body + ([slow] if slow and n >= 5 else []) + [last]
    return out[:max(2, n)]


def _variations(prof: Profile, key: Key, bars: int, rng: random.Random, character: str,
                count: int = 5, long_theme: bool = False, **_) -> FormPlan:
    """A theme and variations. The theme is a period — a phrase that pauses
    on the dominant and one that answers it and closes — and every variation
    keeps its phrases, cadences and chords while changing what the ear
    notices first: a figuration that decorates each note of the tune, a
    running accompaniment, the change of mode, the tune in the tenor, a slow
    ornamented variation, a finale; then a coda."""
    tx: dict = {}
    idiom = "romantic" if prof.harmony in ("romantic", "russian", "film", "impressionist") \
        else "baroque" if prof.harmony == "baroque" else "classical"
    romantic = idiom == "romantic"
    half = 8 if long_theme else 4
    n = max(2, min(12, count))
    kinds = _choose_variations(_PROGRAMMES[idiom], n)
    tex = _tex(prof, "theme", rng, tx)
    lang = prof.language if prof.language in _THEME_NAME else "it"
    words = prof.words
    ph: list[PhraseSpec] = [
        _phr(_THEME_NAME[lang], "theme", "antecedent", half, key, "HC", 0.4, tex,
             new_section=True, words=words.get("theme", "")),
        _phr(_THEME_NAME[lang], "theme", "consequent", half, key, "PAC", 0.45, tex),
    ]
    busy = {"classical": "alberti", "baroque": "walking",
            "romantic": "sweep16" if prof.octave_climax else "sweep"}[idiom]
    plain = "block" if tex in ("alberti", "sweep", "sweep16") else tex
    other = parallel_key_of(key)
    scale = 1.0
    used: set[tuple[str, str]] = set()
    spare = [t for ts in prof.textures.values() for t in ts
             if t not in ("tenor", "imitation", "fugato", "final")]
    for v, kind in enumerate(kinds):
        name = f"Var. {_ROMAN[v]}" if v < len(_ROMAN) else f"Var. {v + 1}"
        vkey, variation, texture, energy, wds, role = key, "", tex, 0.5, "", "variation"
        register, tempo_words, new_scale = "", "", 1.0
        if kind == "figural":
            variation, texture, energy = "figural", plain, 0.5
            wds = "leggiero" if romantic else ""
        elif kind == "triplets":
            # chords under running triplets: no three against two
            variation, texture, energy = "figural3", "block" if romantic else plain, 0.55
            wds = "dolce" if romantic else ""
        elif kind == "accomp":
            variation, texture, energy = ("ornament" if prof.ornaments >= 0.2 else ""), busy, 0.55
        elif kind == "walking":
            texture, energy = "walking", 0.55
        elif kind == "minore":
            vkey, variation = other, "minore" if not key.is_minor else "maggiore"
            texture = "repeated" if romantic else ("block" if tex == "alberti" else tex)
            energy = 0.45
            wds = "Minore" if not key.is_minor else "Maggiore"
        elif kind == "tenor":
            variation, register, texture, energy = "tenor", "tenor", "tenor", 0.45
            wds = "cantabile"
        elif kind == "agitato":
            variation, texture, energy, wds = "octaves", busy, 0.8, "agitato"
        elif kind in ("adagio", "lento"):
            variation, energy = "ornament", 0.3
            texture = "nocturne" if romantic else ("alberti" if tex != "alberti" else "repeated")
            new_scale = 0.6
            tempo_words = {"it": "Adagio" if not romantic else "Lento", "de": "Langsam",
                           "fr": "Lent"}[lang]
            wds = "espressivo"
        elif kind == "finale":
            if romantic:
                role, variation, energy = "climax", "octaves", 0.95
                texture = _tex(prof, "climax", rng, tx)
                wds = "maestoso"
            else:
                variation, texture, energy = "figural", "block" if idiom == "classical" \
                    else "walking", 0.8
                new_scale = 1.25
                tempo_words = {"it": "Allegro", "de": "Rasch", "fr": "Vif"}[lang]
        if (kind, texture) in used and register != "tenor":
            # a kind heard before comes back in another dress
            fresh = [t for t in spare if (kind, t) not in used]
            if fresh:
                texture = rng.choice(fresh)
        used.add((kind, texture))
        if new_scale != scale and not tempo_words:
            tempo_words = "Tempo I"
        scale = new_scale
        for j in range(2):
            src = ph[j]
            ph.append(_phr(name, role, src.kind, src.bars, vkey, src.cadence,
                           energy + 0.05 * j, texture, recall=j, variation=variation,
                           new_section=(j == 0), words=wds if j == 0 else "",
                           register=register, tempo_scale=new_scale,
                           tempo_words=tempo_words if j == 0 else ""))
    # the coda: the finale's energy carried home, or — in a Romantic set —
    # the theme remembered quietly
    if romantic:
        ph.append(_phr("Coda", "closing", "closing", 4 if not long_theme else 8, key, "plagal",
                       0.25, _tex(prof, "closing", rng, tx), new_section=True,
                       tempo_scale=1.0, tempo_words="Tempo I" if scale != 1.0 else ""))
    else:
        ph.append(_phr("Coda", "closing", "closing", 4 if not long_theme else 8, key, "PAC",
                       0.85, ph[-1].texture, new_section=True, tempo_scale=scale))
    return FormPlan("variations", ph)


def parallel_key_of(key: Key) -> Key:
    from .variation import parallel_key
    return parallel_key(key)


_TEMPLATES = {
    "continuation": _continuation,
    "concerto": _concerto,
    "prelude": _ternary, "nocturne": _ternary, "waltz": _waltz, "mazurka": _mazurka,
    "sonata": _sonata, "minuet": _minuet, "invention": _invention, "etude": _etude,
    "variations": _variations, "rondo": _rondo,
}
