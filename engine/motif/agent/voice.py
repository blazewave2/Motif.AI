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
