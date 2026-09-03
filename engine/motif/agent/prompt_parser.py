"""Natural-language request -> CompositionPlan, using no external services.

This is the deterministic understanding layer.  It runs first, always; the LLM
planner (when configured) refines its output rather than replacing it, so Motif
still works fully offline.
"""
from __future__ import annotations

import difflib
import random
import re

from ..compose.forms import FORMS
from ..compose.orchestration import ENSEMBLES, build_instruments
from ..compose.styles import STYLES, match_styles, resolve_style
from ..plan import CompositionPlan, InstrumentPlan, SectionPlan
from ..theory.pitch import Key

# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------
_NOTE_RE = re.compile(
    r"\b([a-g])\s?(sharp|flat|#|b|♯|♭)?\s*"
    r"(major|minor|maj|min|dorian|phrygian|lydian|mixolydian|aeolian|locrian)?\b",
    re.I)
_METER_RE = re.compile(r"\b(\d{1,2})\s*/\s*(\d{1,2})\b")
_BPM_RE = re.compile(r"\b(\d{2,3})\s*(?:bpm|beats per minute)\b", re.I)
_BARS_RE = re.compile(r"\b(\d{1,3})\s*(?:bars?|measures?)\b", re.I)
_MINUTES_RE = re.compile(r"\b(\d{1,2})\s*(?:-|\s)?\s*(?:minutes?|mins?)\b", re.I)

MOODS: dict[str, dict] = {
    "dark":        dict(minor=1.0, tempo=-12, energy=0.15, dyn=-1,
                        words=("dark", "darker", "shadowy", "gloomy", "black", "sombre", "somber")),
    "sad":         dict(minor=1.0, tempo=-22, energy=-0.1, dyn=-1,
                        words=("sad", "sorrowful", "mournful", "grief", "tragic", "lament",
                               "melancholy", "melancholic", "wistful", "elegiac", "sorrow")),
    "joyful":      dict(minor=-1.0, tempo=18, energy=0.25, dyn=1,
                        words=("joyful", "joyous", "happy", "cheerful", "uplifting", "bright",
                               "sunny", "merry", "celebratory", "exuberant")),
    "calm":        dict(minor=-0.2, tempo=-25, energy=-0.3, dyn=-2,
                        words=("calm", "peaceful", "gentle", "serene", "tranquil", "still",
                               "quiet", "soothing", "restful", "tender", "soft")),
    "dramatic":    dict(minor=0.7, tempo=8, energy=0.4, dyn=2,
                        words=("dramatic", "intense", "powerful", "epic", "grand", "heroic",
                               "monumental", "thunderous", "titanic")),
    "stormy":      dict(minor=1.0, tempo=25, energy=0.5, dyn=2,
                        words=("stormy", "turbulent", "furious", "raging", "violent", "wild",
                               "agitated", "tempestuous", "frantic")),
    "mysterious":  dict(minor=0.8, tempo=-16, energy=-0.05, dyn=-2,
                        words=("mysterious", "eerie", "haunting", "enigmatic", "ghostly",
                               "uncanny", "shadow", "spooky", "unsettling", "ominous")),
    "romantic":    dict(minor=0.15, tempo=-8, energy=0.05, dyn=0,
                        words=("romantic", "lyrical", "tender", "passionate", "yearning",
                               "singing", "cantabile", "amorous", "loving")),
    "playful":     dict(minor=-0.8, tempo=20, energy=0.2, dyn=0,
                        words=("playful", "witty", "light", "dancing", "sprightly", "jaunty",
                               "whimsical", "capricious", "bouncy")),
    "triumphant":  dict(minor=-0.9, tempo=12, energy=0.5, dyn=2,
                        words=("triumphant", "victorious", "majestic", "regal", "noble",
                               "glorious", "fanfare")),
    "nostalgic":   dict(minor=0.4, tempo=-14, energy=-0.15, dyn=-1,
                        words=("nostalgic", "longing", "bittersweet", "reflective",
                               "contemplative", "pensive", "distant", "memory")),
    "hopeful":     dict(minor=-0.6, tempo=4, energy=0.15, dyn=0,
                        words=("hopeful", "warm", "optimistic", "tender", "sweet", "sincere")),
}

TEMPO_WORDS: list[tuple[tuple[str, ...], int]] = [
    (("grave",), 44), (("largo", "very slow"), 50), (("lento",), 56),
    (("adagio", "slow"), 64), (("larghetto",), 66), (("andante", "walking"), 82),
    (("andantino",), 92), (("moderato", "moderate", "medium"), 104),
    (("allegretto",), 116), (("allegro", "fast", "quick", "lively", "brisk"), 132),
    (("vivace", "vivo"), 152), (("presto", "very fast", "rapid"), 172),
    (("prestissimo", "blazing", "furious tempo"), 192),
]

SCOPE_WORDS: list[tuple[tuple[str, ...], int]] = [
    (("motif", "fragment", "idea", "sketch", "a few bars", "tiny"), 8),
    (("short", "brief", "simple", "small", "quick", "little", "easy", "beginner"), 16),
    (("phrase", "melody", "tune", "theme"), 16),
    (("piece", "study", "prelude", "song", "waltz", "nocturne"), 40),
    (("movement", "long", "extended", "substantial", "full"), 80),
    (("concerto", "symphony", "sonata", "complete", "grand", "large-scale",
      "large scale", "epic"), 120),
]

ENSEMBLE_WORDS: dict[str, tuple[str, ...]] = {
    "piano_concerto": ("piano concerto", "concerto for piano", "piano and orchestra"),
    "orchestra": ("orchestra", "orchestral", "symphony", "symphonic", "full orchestra"),
    "string_quartet": ("string quartet", "quartet"),
    "string_orchestra": ("string orchestra", "strings", "string ensemble"),
    "piano_trio": ("piano trio", "trio"),
    "violin_piano": ("violin and piano", "violin sonata", "for violin"),
    "cello_piano": ("cello and piano", "cello sonata", "for cello"),
    "voice_piano": ("voice and piano", "song for voice", "lied", "art song"),
    "chamber": ("chamber", "ensemble"),
    "organ": ("organ",),
    "harpsichord": ("harpsichord",),
    "guitar": ("guitar",),
    "solo_piano": ("solo piano", "piano solo", "for piano", "piano piece", "keyboard"),
}

FORM_WORDS: dict[str, tuple[str, ...]] = {
    "concerto": ("concerto",),
    "nocturne": ("nocturne",),
    "fugue": ("fugue", "fugal"),
    "invention": ("invention", "two-part", "two part"),
    "sonata": ("sonata", "sonata form", "sonata-allegro"),
    "rondo": ("rondo",),
    "theme_and_variations": ("variations", "theme and variations"),
    "waltz": ("waltz", "valse"),
    "prelude": ("prelude",),
    "etude": ("etude", "étude", "study"),
    "mazurka": ("mazurka",),
    "scherzo": ("scherzo",),
    "minuet": ("minuet", "menuetto"),
    "ballade": ("ballade",),
    "rhapsody": ("rhapsody", "rapsody"),
    "impromptu": ("impromptu",),
    "intermezzo": ("intermezzo",),
    "arabesque": ("arabesque",),
    "gymnopedie": ("gymnopedie", "gymnopédie"),
    "chorale": ("chorale", "hymn"),
    "period": ("period", "antecedent"),
    "ternary": ("ternary", "aba"),
    "binary": ("binary",),
    "through_composed": ("through-composed", "through composed", "fantasy", "fantasia"),
    "ostinato_form": ("ostinato", "minimalist", "loop"),
}

# Words that mean "keep it playable by a human beginner".
SIMPLE_WORDS = ("simple", "easy", "beginner", "basic", "for me to play", "playable",
                "elementary", "straightforward", "beginner-friendly", "one hand",
                "right hand only", "melody only", "just a melody", "single line")


def _canon(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _fuzzy_style(text: str) -> str | None:
    """Catch misspelled composer names — 'Rachmanninoff', 'Chopan', 'Debusy'."""
    words = re.findall(r"[a-zA-Zé']{4,}", text.lower())
    best, best_ratio = None, 0.0
    targets = {n: n for n in STYLES}
    targets.update({"rachmaninov": "rachmaninoff", "beethovan": "beethoven",
                    "tchaikovski": "tchaikovsky", "debussey": "debussy"})
    for w in words:
        for t, canonical in targets.items():
            r = difflib.SequenceMatcher(None, w, t).ratio()
            if r > best_ratio and r >= 0.78:
                best, best_ratio = canonical, r
    return best


def parse_key(text: str) -> tuple[str | None, str | None]:
    """Find an explicit key.  Returns (tonic, mode), either possibly None.

    The letter alone is never enough: "in a more dramatic way" must not be read
    as the key of A.  A match needs an accidental, a mode word, or "key of".
    """
    t = text.replace("\u266f", "#").replace("\u266d", "b")
    modes = "major|minor|maj|min|dorian|phrygian|lydian|mixolydian|aeolian|locrian"

    # "in a minor key" asks for the mode, not for the key of A.
    generic = re.search(r"\b(?:in|into|to)\s+(?:a|the|some|any)\s+(major|minor)\s+key\b", t)
    if generic:
        return None, generic.group(1)

    # "key of Eb", "key of D minor" — the phrase itself disambiguates.
    m = re.search(r"\bkey of\s+([A-Ga-g])\s?(sharp|flat|#|b)?[\s-]*(" + modes + r")?\b",
                  t, re.I)
    if not m:
        # Otherwise require an accidental word/symbol, a mode word, or both.
        m = re.search(r"\b([A-Ga-g])[\s-]?(sharp|flat|#|b)[\s-]*(" + modes + r")?\b", t)
        if not m:
            m = re.search(r"\b([A-Ga-g])[\s-]?(sharp|flat|#|b)?[\s-]*(" + modes + r")\b", t)
    if not m:
        return None, None

    letter_raw, acc_raw, mode_raw = m.group(1), (m.group(2) or ""), (m.group(3) or "")
    acc, mode = acc_raw.lower(), mode_raw.lower()

    # A lone lowercase "a"/"b" with no accidental is the article or a bare note
    # name; only accept it when a mode word makes the intent explicit.
    if letter_raw.islower() and not acc and not mode:
        return None, None
    # "b" as an accidental only counts when it directly abuts the letter, so
    # "B minor" stays the key of B rather than becoming B-flat.
    if acc == "b" and m.start(2) != m.end(1):
        acc = ""

    letter = letter_raw.upper()
    if acc in ("sharp", "#"):
        letter += "#"
    elif acc in ("flat", "b"):
        letter += "b"
    mode = {"maj": "major", "min": "minor", "": ""}.get(mode, mode)
    return letter, (mode or None)


def _mood_scores(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for name, spec in MOODS.items():
        hits = sum(1 for w in spec["words"] if w in text)
        if hits:
            out[name] = float(hits)
    return out


def _detect(text: str, table: dict[str, tuple[str, ...]]) -> str | None:
    best, best_len = None, 0
    for name, words in table.items():
        for w in words:
            if w in text and len(w) > best_len:
                best, best_len = name, len(w)
    return best


def parse_prompt(prompt: str, *, seed: int | None = None,
                 previous: CompositionPlan | None = None) -> CompositionPlan:
    """Build a complete plan from a free-text request."""
    text = _canon(prompt)
    rng = random.Random(seed if seed is not None else abs(hash(text)) % (2 ** 31))

    # -- style ------------------------------------------------------------
    matches = match_styles(text)
    style_name = matches[0][0] if matches else None
    if not style_name:
        style_name = _fuzzy_style(text)
    style = resolve_style(style_name)

    # -- mood -------------------------------------------------------------
    moods = _mood_scores(text)
    minor_pull = sum(MOODS[m]["minor"] * w for m, w in moods.items())
    tempo_shift = sum(MOODS[m]["tempo"] * w for m, w in moods.items()) / max(1, len(moods))
    energy_shift = sum(MOODS[m]["energy"] * w for m, w in moods.items()) / max(1, len(moods))
    dyn_shift = sum(MOODS[m]["dyn"] * w for m, w in moods.items()) / max(1, len(moods))
    character = ", ".join(sorted(moods, key=lambda m: -moods[m])[:2])

    # -- key --------------------------------------------------------------
    tonic, mode = parse_key(text)
    if mode is None:
        if minor_pull > 0.2:
            mode = "minor"
        elif minor_pull < -0.2:
            mode = "major"
        else:
            mode = "minor" if rng.random() < 0.42 else "major"
    if tonic is None:
        pool_minor = ["A", "D", "E", "C", "G", "B", "F#", "C#", "Bb", "Eb", "F"]
        pool_major = ["C", "G", "D", "F", "Bb", "Eb", "A", "Ab", "E", "Db"]
        tonic = rng.choice(pool_minor if mode == "minor" else pool_major)
    key = Key(tonic, mode)

    # -- ensemble & form ---------------------------------------------------
    ensemble = _detect(text, ENSEMBLE_WORDS) or "solo_piano"
    form = _detect(text, FORM_WORDS)
    if form is None:
        form = "concerto" if ensemble == "piano_concerto" else rng.choice(list(style.forms))
    if form not in FORMS:
        form = "ternary"
    if ensemble == "piano_concerto" and form not in ("concerto", "sonata", "rondo"):
        form = "concerto"

    # -- scope -------------------------------------------------------------
    simple = any(w in text for w in SIMPLE_WORDS)
    bars = None
    mb = _BARS_RE.search(text)
    if mb:
        bars = max(2, min(400, int(mb.group(1))))
    mm = _MINUTES_RE.search(text)
    if bars is None and mm:
        bars = max(8, min(400, int(mm.group(1)) * 30))
    if bars is None:
        bars = 32
        for words, n in SCOPE_WORDS:
            if any(w in text for w in words):
                bars = n
        if simple:
            bars = min(bars, 16)
    if ensemble == "piano_concerto" and not mb:
        bars = max(bars, 96)

    # -- metre -------------------------------------------------------------
    met = _METER_RE.search(text)
    if met:
        time = (int(met.group(1)), int(met.group(2)))
    elif form in ("waltz", "mazurka", "minuet") or "waltz" in text:
        time = (3, 4)
    elif "march" in text:
        time = (4, 4)
    else:
        # The first metres a style lists are its usual ones; 5/4 should stay rare.
        metres = list(style.meters)
        time = rng.choices(metres, weights=[1.0 / (i + 1) ** 1.5
                                            for i in range(len(metres))], k=1)[0]
    if time[1] not in (1, 2, 4, 8, 16) or not (1 <= time[0] <= 32):
        time = (4, 4)

    # -- tempo -------------------------------------------------------------
    bpm = None
    mb2 = _BPM_RE.search(text)
    if mb2:
        bpm = max(30, min(240, int(mb2.group(1))))
    tempo_text = ""
    if bpm is None:
        for words, v in TEMPO_WORDS:
            if any(w in text for w in words):
                bpm = v
                tempo_text = words[0].title()
                break
    if bpm is None:
        lo, hi = style.tempo_range
        bpm = int(lo + (hi - lo) * (0.35 + rng.random() * 0.3))
    bpm = int(max(32, min(220, bpm + tempo_shift)))
    if not tempo_text:
        tempo_text = rng.choice(style.tempo_terms) if style.tempo_terms else ""

    # -- sections ----------------------------------------------------------
    from ..compose.forms import build_sections
    sections = build_sections(form, key, style, rng, bars)
    for s in sections:
        s.energy = max(0.05, min(1.0, s.energy + energy_shift * 0.5))
        s.dynamic = _shift(s.dynamic or "mf", int(round(dyn_shift)))
    if simple:
        sections = _simplify(sections, style)

    instruments = build_instruments(ensemble)
    if simple and ensemble == "solo_piano":
        instruments = [InstrumentPlan(name="Piano", abbreviation="Pno.",
                                      staves=2, clefs=["G", "F"], role="solo")]

    plan = CompositionPlan(
        title=_title(text, key, form, style.display, rng, moods),
        subtitle=_subtitle(ensemble, style),
        style=style.name, key=str(key), time=time, tempo=bpm, tempo_text=tempo_text,
        form=form, sections=sections, instruments=instruments,
        seed=rng.randint(1, 2 ** 30), prompt=prompt, character=character,
        ensemble=ensemble)
    if simple:
        plan.notes = "simplified: reduced texture and range for playability"
    return plan


def _shift(dyn: str, step: int) -> str:
    scale = ["ppp", "pp", "p", "mp", "mf", "f", "ff", "fff"]
    try:
        i = scale.index(dyn)
    except ValueError:
        i = 4
    return scale[max(0, min(len(scale) - 1, i + step))]


def _simplify(sections: list[SectionPlan], style) -> list[SectionPlan]:
    """Reduce a plan to something a learner can actually play."""
    easy_lh = {"block_chords", "waltz", "alberti", "sustained", "walking_bass",
               "arpeggio", "ostinato", "march"}
    out: list[SectionPlan] = []
    for s in sections:
        if s.role in ("cadenza",):
            continue
        s.texture_lh = s.texture_lh if s.texture_lh in easy_lh else "block_chords"
        s.texture_rh = "melody"
        s.register = 0
        s.energy = min(s.energy, 0.6)
        s.harmonic_rhythm = "slow" if s.harmonic_rhythm == "very_fast" else s.harmonic_rhythm
        out.append(s)
    return out or sections


#: Title words grouped by affect, so a joyful piece never comes back "Threnody".
_TITLE_NOUNS: dict[str, list[str]] = {
    "bright": ["Daybreak", "Aurora", "Cascade", "Bluebell", "Skylark", "Meadow",
               "Sunlit", "Carillon", "Festival", "Garland", "Zephyr"],
    "dark": ["Blizzard", "Nightfall", "Threnody", "Solitude", "Ember", "Eclipse",
             "Silhouette", "Winterlight", "Undertow", "Vigil", "Ashfall"],
    "calm": ["Reverie", "Stillness", "Meditation", "Lullaby", "Nocturne",
             "Driftwood", "Quietude", "Evensong", "Hush"],
    "neutral": ["Prelude", "Interlude", "Passage", "Sketch", "Vision", "Fantasy",
                "Arabesque", "Impromptu", "Mirage", "Elegy"],
}


def _title_bucket(moods: dict[str, float], key: Key) -> str:
    bright = sum(moods.get(m, 0) for m in ("joyful", "playful", "triumphant", "hopeful"))
    dark = sum(moods.get(m, 0) for m in ("dark", "sad", "stormy", "dramatic", "mysterious"))
    calm = sum(moods.get(m, 0) for m in ("calm", "nostalgic", "romantic"))
    top = max((bright, "bright"), (dark, "dark"), (calm, "calm"), key=lambda t: t[0])
    if top[0] == 0:
        return "dark" if key.is_minor else "neutral"
    return top[1]


def _title(text: str, key: Key, form: str, style_display: str, rng: random.Random,
           moods: dict[str, float] | None = None) -> str:
    quoted = re.search(r"(?:called|titled|named)\s+[\"']?([\w \-']{2,40})[\"']?", text)
    if quoted:
        return quoted.group(1).strip().title()
    formal = {"concerto": "Concerto", "sonata": "Sonata", "fugue": "Fugue",
              "invention": "Invention", "waltz": "Waltz", "nocturne": "Nocturne",
              "prelude": "Prelude", "etude": "\u00c9tude", "rondo": "Rondo",
              "mazurka": "Mazurka", "scherzo": "Scherzo", "ballade": "Ballade",
              "rhapsody": "Rhapsody", "intermezzo": "Intermezzo",
              "impromptu": "Impromptu", "theme_and_variations": "Variations"}
    if form in formal:
        return f"{formal[form]} in {key}"
    for image in ("blizzard", "storm", "forest", "ocean", "rain", "winter", "night",
                  "dawn", "autumn", "spring", "summer", "moon", "star", "river",
                  "snow", "fire", "dream", "sea"):
        if image in text:
            return image.title()
    return rng.choice(_TITLE_NOUNS[_title_bucket(moods or {}, key)])


def _subtitle(ensemble: str, style) -> str:
    pretty = {"solo_piano": "Solo Piano", "piano_concerto": "Piano and Orchestra",
              "string_quartet": "String Quartet", "orchestra": "Orchestra",
              "piano_trio": "Piano Trio", "string_orchestra": "String Orchestra",
              "violin_piano": "Violin and Piano", "cello_piano": "Cello and Piano",
              "voice_piano": "Voice and Piano", "chamber": "Chamber Ensemble",
              "organ": "Organ", "harpsichord": "Harpsichord", "guitar": "Guitar"}
    return pretty.get(ensemble, "Solo Piano")
