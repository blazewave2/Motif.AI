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
              rng: random.Random, character: str = "") -> FormPlan:
    """Lay out a piece of about ``target_bars`` bars in ``genre``."""
    genre = (genre or "").lower()
    fn = _TEMPLATES.get(_genre_family(genre), _ternary)
    plan = fn(prof, key, max(8, target_bars), rng, character)
    plan.genre = genre or plan.genre
    _add_intro(plan, prof, target_bars, rng)
    return plan


#: Textures that can set the scene on their own before the tune comes in.
_INTRO_TEXTURES = ("nocturne", "sweep", "sweep16", "bells", "repeated", "waltz", "sustained")


def _add_intro(plan: FormPlan, prof: Profile, target_bars: int, rng: random.Random) -> None:
    """A bar or two of accompaniment alone, as so many Romantic pieces begin."""
    if not plan.phrases:
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
    "lyric piece", "gymnopédie", "gymnopedie", "gnossienne", "liebestraum", "consolation",
    "nocturne", "prelude", "prélude", "waltz", "valse", "mazurka", "polonaise", "sonatina",
    "sonata", "minuet", "menuet", "gavotte", "sarabande", "gigue", "invention", "fugue",
    "toccata", "etude", "étude", "study", "romance", "elegie", "élégie", "elegy", "berceuse",
    "barcarolle", "reverie", "rêverie", "intermezzo", "impromptu", "ballade", "rhapsody",
    "fantasy", "fantasia", "scherzo", "arabesque", "lied", "song",
)


def detect_genre(text: str) -> str | None:
    """The kind of piece a request names, if it names one."""
    t = (text or "").lower()
    for w in GENRE_WORDS:
        if w in t:
            return w
    return None


#: Usual metres for each family of pieces, with how often each is chosen.
_METRES = {
    "waltz": [((3, 4), 1)], "mazurka": [((3, 4), 1)], "minuet": [((3, 4), 1)],
    "nocturne": [((4, 4), 5), ((12, 8), 2), ((6, 8), 2), ((3, 4), 2)],
    "prelude": [((4, 4), 6), ((3, 4), 3), ((6, 8), 1)],
    "etude": [((4, 4), 6), ((2, 4), 2), ((6, 8), 1)],
    "sonata": [((4, 4), 6), ((3, 4), 2), ((2, 4), 1)],
    "invention": [((4, 4), 6), ((3, 4), 2)],
}


def choose_metre(family: str, prof: Profile, rng: random.Random) -> tuple[int, int]:
    if prof.name == "satie":
        return (3, 4)
    opts = _METRES.get(family, _METRES["prelude"])
    if prof.melody in ("classical", "baroque"):
        opts = [o for o in opts if o[0][1] == 4] or opts
    metres, weights = zip(*opts)
    return rng.choices(metres, weights)[0]


def _genre_family(genre: str) -> str:
    for fam, words in (
        ("waltz", ("waltz", "valse", "ländler")),
        ("mazurka", ("mazurka", "polonaise")),
        ("sonata", ("sonata", "sonatina", "first movement")),
        ("minuet", ("minuet", "menuet", "gavotte", "bourrée", "sarabande", "gigue")),
        ("invention", ("invention", "fugue", "toccata", "partita", "sinfonia")),
        ("etude", ("etude", "étude", "study", "toccata", "etude-tableau")),
        ("nocturne", ("nocturne", "romance", "song", "elegie", "élégie", "elegy", "lied",
                      "berceuse", "barcarolle", "reverie", "rêverie", "consolation",
                      "liebestraum", "lyric", "intermezzo", "impromptu", "moment")),
        ("prelude", ("prelude", "prélude", "ballade", "rhapsody", "fantasy", "fantasia",
                     "scherzo", "piece", "")),
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


def _ternary(prof: Profile, key: Key, bars: int, rng: random.Random, character: str
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
    phrases: list[PhraseSpec] = []
    words = prof.words
    # A: a period (antecedent + consequent) or a sentence
    phrases += _theme_group("A", "theme", key, a_bars, prof, rng, tx, energy=0.45,
                            words=words.get("theme", ""))
    # B: contrasting key, more motion, building to the climax

    n_b = max(1, b_bars // 8) if b_bars >= 8 else 1
    for i in range(n_b):
        last = i == n_b - 1
        phrases.append(_phr("B", "contrast", "continuation" if i else "sentence",
                            8 if b_bars >= 8 else b_bars, b_key,
                            "HC" if last else "PAC", 0.55 + 0.2 * i / n_b,
                            _tex(prof, "contrast", rng, tx), new_section=(i == 0),
                            words=words.get("contrast", "") if i == 0 else ""))
    # retransition back to the tonic
    phrases.append(_phr("B", "transition", "development", 4, key, "HC", 0.85,
                        _tex(prof, "contrast", rng, tx)))
    # A': the theme returns — at its climax for Rachmaninoff and Liszt,
    # ornamented and tender for Chopin
    grand = prof.octave_climax
    theme_idx = [i for i, p in enumerate(phrases) if p.section == "A"]
    for j, src in enumerate(theme_idx[:max(1, r_bars // 8)]):
        p = phrases[src]
        last = j == max(1, r_bars // 8) - 1
        phrases.append(_phr("A'", "return" if not grand else "climax",
                            p.kind, p.bars, key, "PAC" if last else p.cadence,
                            0.95 if grand else 0.5,
                            _tex(prof, "climax" if grand else "return", rng, tx),
                            recall=src, variation="octaves" if grand else "ornament",
                            new_section=(j == 0),
                            words=words.get("climax" if grand else "return", "")))
    phrases.append(_phr("coda", "closing", "closing", coda, key, "plagal" if
                        prof.harmony in ("russian", "romantic") else "PAC", 0.25,
                        _tex(prof, "closing", rng, tx), new_section=True))
    return FormPlan("ternary", phrases)


def _theme_group(section: str, role: str, key: Key, bars: int, prof: Profile,
                 rng: random.Random, tx: dict, energy: float, words: str = ""
                 ) -> list[PhraseSpec]:
    out: list[PhraseSpec] = []
    tex = _tex(prof, role, rng, tx)
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


def _waltz(prof: Profile, key: Key, bars: int, rng: random.Random, character: str
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


def _mazurka(prof: Profile, key: Key, bars: int, rng: random.Random, character: str
             ) -> FormPlan:
    plan = _waltz(prof, key, bars, rng, character)
    plan.genre = "mazurka"
    return plan


def _sonata(prof: Profile, key: Key, bars: int, rng: random.Random, character: str
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


def _minuet(prof: Profile, key: Key, bars: int, rng: random.Random, character: str
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


def _invention(prof: Profile, key: Key, bars: int, rng: random.Random, character: str
               ) -> FormPlan:
    tx: dict = {}
    tex = _tex(prof, "theme", rng, tx)
    other = _related(key, "dominant" if not key.is_minor else "relative")
    ph = [
        _phr("A", "theme", "sentence", 8, key, "HC", 0.5, tex, new_section=True),
        _phr("A", "development", "continuation", 8, other, "PAC", 0.6, tex),
        _phr("B", "development", "development", 8, _related(key, "submediant"), "PAC", 0.7, tex),
        _phr("A'", "return", "sentence", 8, key, "PAC", 0.6, tex, recall=0),
    ]
    return FormPlan("invention", ph)


def _etude(prof: Profile, key: Key, bars: int, rng: random.Random, character: str
           ) -> FormPlan:
    plan = _ternary(prof, key, bars, rng, character)
    for p in plan.phrases:
        if p.role in ("theme", "return", "contrast", "climax", "transition"):
            p.texture = "sweep16" if prof.name not in ("bach",) else p.texture
            p.energy = min(1.0, p.energy + 0.15)
    plan.genre = "etude"
    return plan


_TEMPLATES = {
    "prelude": _ternary, "nocturne": _ternary, "waltz": _waltz, "mazurka": _mazurka,
    "sonata": _sonata, "minuet": _minuet, "invention": _invention, "etude": _etude,
}
