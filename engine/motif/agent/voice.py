"""How Motif talks about what it just wrote.

This is deliberately kept separate from the music engine: composing.py and
its neighbours decide every note, and nothing here ever touches a pitch. All
this module does is describe the result in a way that reads like a person
talking about their own piece, not a form being filled in and handed back —
picking from real variety in phrasing rather than one fixed sentence every
time.

``VoiceModel`` is the extension point for a future upgrade: a small local
text model that rewrites these descriptions with real conversational range.
None is bundled here — there is no such model in this install — but the
hook exists (the same optional-extra shape as ``model/runtime.py``'s neural
composer) so one can be dropped in later without changing anything that
calls into this module.
"""
from __future__ import annotations

import random
from typing import Protocol

from ..plan import CompositionPlan


class VoiceModel(Protocol):
    """A local model that can rewrite a plain description with more range.

    Nothing in this codebase implements this today. A future optional
    extra could load a small on-device model here the same way
    ``model.runtime.NeuralComposer`` loads a trained composing model — kept
    entirely separate from it, since this one only ever touches words.
    """

    def rewrite(self, plain: str, context: dict) -> str | None:
        ...


_FORCES = {"solo_piano": "solo piano", "piano_concerto": "piano and orchestra",
          "string_quartet": "string quartet", "piano_trio": "piano trio",
          "string_orchestra": "string orchestra", "orchestra": "orchestra",
          "violin_piano": "violin and piano", "cello_piano": "cello and piano",
          "voice_piano": "voice and piano", "chamber": "chamber ensemble"}


def _forces(ensemble: str) -> str:
    return _FORCES.get(ensemble, ensemble.replace("_", " "))


def _rng_for(plan: CompositionPlan) -> random.Random:
    # Deterministic per piece (same seed always reads the same way on
    # replay) but genuinely different from one composition to the next.
    return random.Random((plan.seed or 0) ^ 0x766F6963)   # 'voic'


def created_message(plan: CompositionPlan, style, voice: VoiceModel | None = None) -> str:
    rng = _rng_for(plan)
    forces = _forces(plan.ensemble)
    form = plan.form.replace("_", " ")

    opener = rng.choice([
        f"Here's **{plan.title}** — {plan.total_bars} bars of {form} for {forces}, "
        f"in {plan.key}.",
        f"**{plan.title}**: a {form} for {forces} in {plan.key}, {plan.total_bars} bars.",
        f"I've written **{plan.title}**, a {form} for {forces} in {plan.key}.",
        f"**{plan.title}** is done — {form} for {forces}, {plan.total_bars} bars, "
        f"in {plan.key}.",
    ])
    tempo = f"{plan.time[0]}/{plan.time[1]} at ♩ = {plan.tempo}"
    if plan.tempo_text:
        tempo += f" ({plan.tempo_text})"
    tempo_line = rng.choice([
        f" Marked {tempo}, in a {style.display} idiom.",
        f" It moves in {tempo}, written in a {style.display} idiom.",
        f" {tempo.capitalize()}, {style.display} in spirit.",
    ])
    bits = [opener, tempo_line]
    if plan.character:
        bits.append(rng.choice([
            f" The character is {plan.character}.",
            f" I aimed for something {plan.character}.",
        ]))
    labels = " → ".join(s.label for s in plan.sections[:9])
    if labels:
        bits.append(f"\n\nStructure: {labels}.")
    if plan.notes:
        bits.append(f"\n\n_{plan.notes}_")
    plain = "".join(bits)
    return _try_rewrite(voice, plain, {"kind": "create", "plan": plan})


_TEXTURE_WORDS = {
    "nocturne": ["a wide, rippling left hand spread over a tenth and more",
                 "broken chords that ripple up from a deep bass"],
    "sweep": ["sweeping triplet arpeggios in the left hand",
              "left-hand arpeggios that sweep up two octaves and back"],
    "sweep16": ["surging sixteenth-note arpeggios", "a torrent of sixteenth-note arpeggios"],
    "bells": ["tolling bass octaves answered by chords", "bell-like octaves deep in the bass"],
    "block": ["full, sustained chords", "rich chordal writing"],
    "waltz": ["a waltz bass", "the lilt of a waltz accompaniment"],
    "alberti": ["an Alberti bass", "a running Alberti accompaniment"],
    "repeated": ["throbbing repeated chords", "pulsing repeated chords"],
    "walking": ["a walking bass line", "a bass that walks beneath it"],
    "sustained": ["open, pedalled harmonies", "still, open sonorities"],
}
_GENRE_NAMES = {"etude-tableau": "étude-tableau", "etude": "étude", "elegie": "élégie",
                "gymnopedie": "gymnopédie", "lyric piece": "lyric piece",
                "variations": "theme and variations", "variation": "theme and variations",
                "theme_and_variations": "theme and variations"}


#: How the accompaniment sounds when no piano plays it: the inner parts and
#: the bass of a quartet or an orchestra.
_ENSEMBLE_TEXTURE_WORDS = {
    "block": ["sustained harmony in the lower parts", "full chords in the lower parts"],
    "repeated": ["pulsing repeated chords", "throbbing inner parts"],
    "walking": ["a walking bass", "a bass line that walks"],
    "bells": ["tolling octaves in the bass", "deep, tolling basses"],
    "waltz": ["a waltz accompaniment", "the lilt of a waltz"],
    "sustained": ["long-held harmonies", "still, sustained harmonies"],
}
_PIANO_LESS = ("string_quartet", "string_orchestra", "orchestra", "chamber")


def _texture_phrase(tex: str, rng: random.Random, ensemble: str = "") -> str:
    if ensemble in _PIANO_LESS:
        return rng.choice(_ENSEMBLE_TEXTURE_WORDS.get(
            tex, ["flowing inner parts", "inner parts in gentle motion"]))
    return rng.choice(_TEXTURE_WORDS.get(tex, ["a flowing accompaniment"]))


def _bars(a: int, b: int) -> str:
    return f"bar {a}" if a == b else f"bars {a}–{b}"


def composed_message(plan: CompositionPlan, summary: dict,
                     voice: VoiceModel | None = None) -> str:
    """Describe a piece the way its composer would: what it is, how it opens,
    where it goes and how it ends."""
    rng = _rng_for(plan)
    if not summary:
        return f"Here's **{plan.title}**."
    genre = summary.get("genre") or plan.form
    genre = _GENRE_NAMES.get(genre, genre).replace("_", " ")
    forces = _forces(summary.get("ensemble") or plan.ensemble)
    key = summary.get("key", plan.key)
    bars = summary.get("bars", plan.total_bars)
    tempo_text = summary.get("tempo_text") or ""
    num, den = summary.get("time", plan.time)
    tempo = f"{tempo_text}, " if tempo_text else ""
    tempo += f"{num}/{den}"
    style = summary.get("style", "")
    idiom = f" in the manner of {style}" if style and style.lower() not in (
        "romantic", "classical", "cinematic") else ""
    opener = rng.choice([
        f"Here's **{plan.title}** — a {genre}{idiom} for {forces} in {key}, "
        f"{bars} bars ({tempo}).",
        f"I've written **{plan.title}**, a {genre}{idiom} for {forces} in {key}: "
        f"{bars} bars, {tempo}.",
        f"**{plan.title}** is ready: a {genre} for {forces}{idiom}, in {key}, "
        f"{bars} bars ({tempo}).",
    ])
    lines = [opener]
    secs = summary.get("sections", [])
    if summary.get("family") == "variations":
        story = _variations_story(secs, summary, key, rng)
        if story:
            lines.append("\n\n" + " ".join(story))
        if plan.character:
            lines.append(f"\n\nI aimed for something {plan.character}.")
        plain = "".join(lines)
        return _try_rewrite(voice, plain, {"kind": "create", "plan": plan, "summary": summary})
    story = []
    th = summary.get("theme", {})
    shape = th.get("shape", 0)
    shape_word = "rising" if shape > 0 else "falling" if shape < 0 else "arching"
    described: set[str] = set()
    for sec in secs:
        role, a, b = sec["role"], sec["start"], sec["end"]
        if sec["texture"] in described:
            tex = rng.choice(["the same accompaniment", "the accompaniment heard before"])
        else:
            tex = _texture_phrase(sec["texture"], rng, summary.get("ensemble", ""))
            described.add(sec["texture"])
        forces = sec.get("forces", "")
        if role == "intro" and forces == "solo":
            story.append(f"It opens with the piano alone ({_bars(a, b)}) — tolling chords over "
                         f"deep octaves, growing towards the orchestra's entry.")
        elif role == "theme" and forces == "orch_lead":
            story.append(f"The orchestra states the theme ({_bars(a, b)}), violins and cellos "
                         f"an octave apart, while the piano ripples beneath it.")
        elif role == "theme" and forces == "tutti":
            story.append(f"The orchestra opens with the theme ({_bars(a, b)}) before the "
                         f"soloist enters.")
        elif role == "contrast" and forces == "solo_lead":
            story.append(f"The piano sings the second theme in {sec['key']} ({_bars(a, b)}) over "
                         f"quiet strings, and the orchestra takes it up in turn.")
        elif role == "cadenza":
            story.append(f"A cadenza for the piano alone ({_bars(a, b)}) holds on the dominant "
                         f"before everyone returns for the coda.")
        elif role == "climax" and forces == "tutti":
            story.append(f"The theme returns at the climax ({_bars(a, b)}) with the full "
                         f"orchestra and the piano's massive chords together.")
        elif role == "intro":
            story.append(f"It opens with {_bars(a, b)} of accompaniment alone — {tex}.")
        elif role == "theme":
            up = " that leans in from an upbeat" if th.get("upbeat") else ""
            answer = {1: "answered a step higher", -1: "answered a step lower",
                       2: "answered a third higher", -2: "answered a third lower",
                       3: "answered a fourth higher", 4: "answered on the dominant",
                       -3: "answered on the dominant", 0: "restated over new harmony"
                       }.get(th.get("answer"), "developed")
            story.append(f"The theme ({_bars(a, b)}) is a {shape_word} idea{up}, stated, "
                         f"{answer}, then broken down towards its cadence, over {tex}.")
        elif role == "contrast":
            words = f", {sec['words']}," if sec.get("words") else ""
            story.append(f"The middle section{words} moves to {sec['key']} ({_bars(a, b)}) "
                         f"with a new, contrasting theme over {tex}.")
        elif role == "transition":
            if sec["key"] != key:
                story.append(f"A short passage ({_bars(a, b)}) leads to {sec['key']}.")
            else:
                story.append(f"A short passage ({_bars(a, b)}) leads back home.")
        elif role == "development":
            story.append(f"{_bars(a, b).capitalize()} develop the opening idea in sequence "
                         f"through {sec['key']}.")
        elif role == "climax":
            story.append(f"The theme returns at the climax ({_bars(a, b)}), in octaves over "
                         f"{tex}.")
        elif role == "return":
            how = {"ornament": ", ornamented", "octaves": " in octaves"}.get(
                sec.get("variation", ""), "")
            story.append(f"The theme comes back{how} in {_bars(a, b)}.")
        elif role == "closing" and forces == "tutti":
            story.append(f"A coda for everyone ({_bars(a, b)}) brings it home in full voice.")
        elif role == "closing":
            story.append(f"A coda ({_bars(a, b)}) remembers the opening and settles.")
    # merge duplicate sentences for repeated sections
    seen, uniq = set(), []
    for sentence in story:
        k = sentence.split("(")[0]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(sentence)
    if uniq:
        lines.append("\n\n" + " ".join(uniq))
    if plan.character:
        lines.append(rng.choice([f"\n\nI aimed for something {plan.character}.",
                                 f"\n\nThe character throughout is {plan.character}."]))
    plain = "".join(lines)
    return _try_rewrite(voice, plain, {"kind": "create", "plan": plan, "summary": summary})


def _variations_story(secs: list[dict], summary: dict, key: str,
                      rng: random.Random) -> list[str]:
    """A set of variations told section by section: what the theme is and
    what each variation does to it."""
    th = summary.get("theme", {})
    shape = th.get("shape", 0)
    shape_word = "rising" if shape > 0 else "falling" if shape < 0 else "arching"
    out: list[str] = []
    described: set[str] = set()

    def dress(tex: str) -> str:
        if tex in described:
            return rng.choice(["the accompaniment heard before", "the same accompaniment"])
        described.add(tex)
        return _texture_phrase(tex, rng, summary.get("ensemble", ""))

    for sec in secs:
        role, a, b, name = sec["role"], sec["start"], sec["end"], sec["name"]
        var, tex = sec.get("variation", ""), sec["texture"]
        tempo = sec.get("tempo_words", "")
        where = f" ({_bars(a, b)})"
        article = "an" if tempo[:1].lower() in "aeiou" else "a"
        if role == "theme":
            out.append(f"The theme{where} is a simple {shape_word} tune in two phrases — one "
                       f"that pauses on the dominant and one that answers it and closes — "
                       f"over {dress(tex)}.")
            continue
        if role == "closing":
            quiet = sec.get("energy", 0.5) < 0.5
            out.append(f"A coda{where} " + ("remembers the theme quietly and settles."
                                            if quiet else "brings the set to a brilliant close."))
            continue
        if var == "figural" and tempo and tempo != "Tempo I":
            what = f"— {tempo} — breaks every note of the tune into running arpeggios"
        elif var == "figural":
            what = "decorates every note of the tune in running figuration"
        elif var == "figural3":
            what = "carries the tune in flowing triplets"
        elif var == "minore":
            what = f"turns to {sec['key']} — the minore"
        elif var == "maggiore":
            what = f"turns to {sec['key']} — the maggiore"
        elif var == "tenor" or sec.get("register") == "tenor":
            what = "gives the tune to the left hand, cantabile, under soft repeated chords"
        elif var == "ornament" and tempo in ("Più lento", "Langsamer", "Plus lent"):
            what = f"holds back ({tempo}), lingering on the tune's long notes and " \
                   f"decorating them"
        elif var == "ornament" and tempo and tempo != "Tempo I":
            what = f"slows to {article} {tempo}, holding the tune's long notes and " \
                   f"decorating them"
        elif var == "ornament":
            what = f"ornaments the tune over {dress(tex)}"
        elif var == "octaves" and role == "climax":
            what = "brings the theme back in full chords and octaves at its grandest"
        elif var == "octaves":
            what = f"doubles the tune in octaves over {dress(tex)}"
        else:
            what = f"keeps the tune and sets it over {dress(tex)}"
        out.append(f"{name}{where} {what}.")
    return out


def continued_message(plan: CompositionPlan, existing_title: str, bars: int,
                      info, voice: VoiceModel | None = None) -> str:
    rng = _rng_for(plan)
    style_note = " in the same style" if info.style_is_exact else ""
    tempo = f"♩ = {int(plan.tempo)}"
    plain = rng.choice([
        f"Continued **{existing_title}** with {bars} new bars in {plan.key}, "
        f"following the existing {info.time[0]}/{info.time[1]} at {tempo}"
        f"{style_note}. The new material develops the closing idea.",

        f"I picked up where **{existing_title}** left off — {bars} more bars in "
        f"{plan.key}{style_note}, growing out of the idea it closed on.",

        f"**{existing_title}** now continues for {bars} more bars in {plan.key}"
        f"{style_note}, carrying the closing idea forward rather than starting "
        f"something new.",
    ])
    return _try_rewrite(voice, plain, {"kind": "continue", "plan": plan})


def developed_message(plan: CompositionPlan, existing_title: str,
                      voice: VoiceModel | None = None) -> str:
    rng = _rng_for(plan)
    form = plan.form.replace("_", " ")
    plain = rng.choice([
        f"Developed the material from **{existing_title}** into a new {form} of "
        f"{plan.total_bars} bars in {plan.key}.",

        f"I took what **{existing_title}** was built from and grew it into a "
        f"{form}, {plan.total_bars} bars in {plan.key}.",

        f"**{existing_title}**'s material now becomes a {form}: {plan.total_bars} "
        f"bars in {plan.key}, the same ideas taken further.",
    ])
    return _try_rewrite(voice, plain, {"kind": "develop", "plan": plan})


def harmonized_message(plan: CompositionPlan, existing_title: str, bars: int,
                       style, texture: str, voice: VoiceModel | None = None) -> str:
    rng = _rng_for(plan)
    texture_words = texture.replace("_", " ")
    plain = rng.choice([
        f"Harmonised {bars} bars of **{existing_title}** in {plan.key}. Your "
        f"melody is untouched on the upper staff; the accompaniment is a "
        f"{style.display}-style {texture_words} left hand.",

        f"Your melody in **{existing_title}** is exactly as you wrote it — I "
        f"added a {style.display}-style {texture_words} accompaniment "
        f"underneath, {bars} bars in {plan.key}.",

        f"{bars} bars of **{existing_title}**, now with a {texture_words} left "
        f"hand in a {style.display} manner. The tune itself hasn't changed.",
    ])
    return _try_rewrite(voice, plain, {"kind": "harmonize", "plan": plan})


def _try_rewrite(voice: VoiceModel | None, plain: str, context: dict) -> str:
    if voice is None:
        return plain
    try:
        rewritten = voice.rewrite(plain, context)
    except Exception:
        return plain
    return rewritten if isinstance(rewritten, str) and rewritten.strip() else plain
