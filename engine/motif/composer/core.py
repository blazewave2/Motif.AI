"""The composer: from a plan to a finished, engraved piece.

It works the way a composer works. It invents a theme and weighs it against
other candidates, and a second, contrasting one for the middle of the piece;
lays out the form; for each phrase plans the harmony, writes the melody over
it (trying several and keeping the best) and sets the accompaniment in the
texture the style calls for; brings earlier phrases back, varied, where the
form returns; and finally marks the dynamics, phrasing, pedalling and tempo
a performer needs. How many ideas it tries at each step is the "care" the
musician chooses.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from fractions import Fraction as F

from ..control import Progress, report
from ..notation import parse as parse_msn
from ..notation.to_score import to_score
from ..plan import CompositionPlan
from ..score import Score
from ..theory.pitch import Key, Pitch
from .form import FormPlan, PhraseSpec, choose_metre, detect_genre, genre_family, plan_form
from .harmony import (Harmony, PhraseHarmonySpec, harmony_at, harmony_style, plan_phrase,
                      revise, spell)
from .melody import (MelNote, Motif, MelodyWriter, PhrasePlan, _random_motif, implied_harmony,
                     invent_motif, melody_style, motif_score, respell_line, roles_for)
from .notation import (BarInfo, Mark, Note, Sheet, Voice, bar_length, beat_length,
                       group_tuplets as _group_tuplets)
from .profiles import Profile, choose_tempo, profile
from .texture import TexNote, TextureContext, final_chord, realise
from . import arrange as _arrange


@dataclass(frozen=True)
class Care:
    motifs: int
    harmony_tries: int
    beam: int
    melody_takes: int


CARE = {
    "sketch": Care(8, 4, 6, 1),
    "balanced": Care(16, 8, 10, 2),
    "best": Care(32, 16, 16, 4),
    "maximum": Care(64, 32, 24, 8),
}

_DYNAMICS = ["ppp", "pp", "p", "mp", "mf", "f", "ff", "fff"]

#: How far a sentence's repeat moves its idea, by harmonic style: (scale
#: steps, weight). 4 is the dominant version, 1 a sequence a step higher,
#: -1 a step lower (the subtonic in minor), 0 the same tune reharmonised.
_RESPONSES = {
    "classical": [(4, 7), (1, 2), (0, 1)],
    "baroque": [(4, 5), (1, 3), (-1, 2)],
    "romantic": [(4, 4), (1, 3), (-1, 2), (2, 1), (0, 2)],
    "russian": [(1, 3), (-1, 2), (4, 3), (2, 2), (0, 2)],
    "impressionist": [(1, 2), (-1, 2), (2, 2), (0, 2)],
    "film": [(-2, 2), (3, 2), (1, 2), (0, 2)],
}
_DEBUG_TAKES = False


@dataclass
class Written:
    """One phrase as composed."""

    spec: PhraseSpec
    start: F
    harmony: list[Harmony]
    melody: list[MelNote]
    texture: list[TexNote] = field(default_factory=list)
    upbeat: F = F(0)                 # how far its melody starts before its first bar


class Composer:
    def __init__(self, plan: CompositionPlan, *, quality: str = "best", progress=None,
                 seed: int | None = None, theme=None, form: str | None = None):
        self.plan = plan
        self.theme = theme               # the musician's own theme, when continuing a piece
        self.care = CARE.get(quality, CARE["best"])
        self.progress = progress
        self.rng = random.Random(plan.seed if seed is None else seed)
        self.prof: Profile = profile(plan.style)
        self.key = Key.parse(plan.key)
        self.genre = form or detect_genre(plan.prompt) or plan.form
        self.family = genre_family(self.genre)
        _retitle(plan, self.genre, named=bool(detect_genre(plan.prompt)) and not form)
        if getattr(plan, "time_given", False) or not plan.prompt:
            self.time = tuple(plan.time)
        else:
            self.time = choose_metre(self.family, self.prof, self.rng)
        self.bar = bar_length(self.time)
        self.beat = beat_length(self.time)
        self.notes: list[str] = []
        self.msn = ""
        self.summary: dict = {}
        self.responses: dict[str, int] = {}      # how each theme's repeat was answered
        ens = getattr(plan, "ensemble", None) or "solo_piano"
        self.ensemble = ens if (ens == "solo_piano" or _arrange.supported(ens)) else "solo_piano"
        if getattr(plan, "tempo_given", False):
            self.tempo, self.tempo_text = plan.tempo, plan.tempo_text
        else:
            words, bpm = choose_tempo(self.prof, self.family, plan.character, self.rng)
            if self.beat == F(3, 2):
                bpm = round(bpm * 0.72)
            elif self.beat == F(2):
                bpm = round(bpm * 0.6)
            self.tempo, self.tempo_text = bpm, words
        self._last_dyn: str | None = None
        #: a piece for a learner: plain rhythms, an easy left hand, no ornaments
        self.simple = "simplified" in (plan.notes or "")

    def _say(self, stage: str, label: str, detail: str, fraction: float) -> None:
        report(self.progress, Progress(stage, label, detail, fraction))

    # ------------------------------------------------------------------
    def compose(self) -> Score:
        from . import melody as _melody
        _melody.SIMPLE["on"] = self.simple
        try:
            return self._compose()
        finally:
            _melody.SIMPLE["on"] = False

    def _compose(self) -> Score:
        plan, prof = self.plan, self.prof
        self._say("planning", "Planning the form", "", 0.02)
        target = getattr(plan, "length_bars", 0) or plan.total_bars or 48
        form = plan_form(self.genre, prof, self.key, target, self.rng, plan.character)
        if self.simple:
            form = _simplify(form, prof)
        if self.ensemble != "solo_piano":
            # a tune in the pianist's left hand is a solo-piano idea
            for p in form.phrases:
                if p.register == "tenor" or p.texture == "tenor":
                    p.register = ""
                    p.texture = (prof.textures.get("contrast") or ["block"])[0]
        hstyle = harmony_style(prof.harmony)
        mstyle = melody_style(prof.melody)

        self._say("themes", "Inventing the themes" if self.theme is None else
                  "Listening to your theme", "", 0.06)
        motif = self.theme.motif if self.theme is not None else \
            invent_motif(mstyle, self.time, self.rng, self.care.motifs, plan.character)
        contrast = invent_contrast(mstyle, motif, self.time, self.rng, self.care.motifs)
        writers = {
            "A": MelodyWriter(mstyle, motif, self.rng, beam=self.care.beam, time=self.time),
            "B": MelodyWriter(mstyle, contrast, self.rng, beam=self.care.beam, time=self.time),
        }
        if self.theme is not None:
            writers["A"].theme_bars = [list(b) for b in self.theme.bars]
            writers["A"].theme_key = self.theme.key
        self.notes.append(_describe_motif("Your theme" if self.theme is not None else
                                          "Main theme", motif))
        if any(p.role == "contrast" for p in form.phrases):
            self.notes.append(_describe_motif("Contrasting theme", contrast))
        self.notes.append("Form: " + " → ".join(_sections(form)))
        self.notes.append(f"{self.tempo_text or 'Tempo'} at {self.tempo} to the beat.")

        written: list[Written] = []
        t = F(0)
        n = len(form.phrases)
        last_note: int | None = None
        for i, ps in enumerate(form.phrases):
            frac = 0.1 + 0.8 * i / max(1, n)
            self._say("writing", _label(ps), f"bars {int(t / self.bar) + 1}–"
                      f"{int(t / self.bar) + ps.bars}", frac)
            nxt = form.phrases[i + 1] if i + 1 < n else None
            tail = self._upbeat_of(nxt, written, writers) if nxt is not None else F(0)
            upbeat = self._upbeat_of(ps, written, writers) if written else F(0)
            writer = writers["B"] if ps.role == "contrast" else writers["A"]
            if ps.recall is not None and ps.recall < len(written):
                w = self._recall(written[ps.recall], ps, t, written)
            elif ps.kind == "intro":
                w = self._intro(ps, t, hstyle)
            else:
                w = self._phrase(ps, t, hstyle, mstyle, writer, last_note, written, upbeat,
                                 tail, final=(i == n - 1))
            if ps.kind in ("antecedent", "sentence") and not writer.theme_bars and \
                    ps.recall is None and w.melody:
                writer.theme_bars = _by_bar(w.melody, t, self.bar, ps.bars)
                writer.theme_key = ps.key
            written.append(w)
            if w.melody:
                last_note = w.melody[-1].midi
            t += self.bar * ps.bars

        _tidy_melody(written)
        self.summary = self._summarise(written, form, t, motif, contrast)
        self._say("finishing", "Engraving the score", "", 0.95)
        sheet = self._sheet(written, form, t)
        msn = sheet.to_msn()
        piece = parse_msn(msn)
        score, _issues = to_score(piece)
        score.metadata.update({"style": prof.name, "form": form.genre, "engine": "motif",
                               "seed": plan.seed, "prompt": plan.prompt,
                               "character": plan.character, "ensemble": self.ensemble})
        self.msn = msn
        return score

    def _summarise(self, written: list[Written], form: FormPlan, end: F, motif: Motif,
                   contrast: Motif) -> dict:
        """What was decided, for describing the piece to the musician."""
        sections: list[dict] = []
        for w in written:
            ps = w.spec
            start = int(w.start / self.bar) + 1
            stop = start + ps.bars - 1
            if sections and sections[-1]["name"] == ps.section:
                sec = sections[-1]
                sec["end"] = stop
                sec["energy"] = max(sec["energy"], ps.energy)
                continue
            sections.append({"name": ps.section, "role": ps.role, "start": start, "end": stop,
                             "key": str(ps.key), "texture": ps.texture, "energy": ps.energy,
                             "words": ps.words, "recall": ps.recall is not None,
                             "variation": ps.variation, "forces": ps.forces})
        return {"genre": self.genre, "family": self.family, "bars": int(end / self.bar),
                "key": str(self.key), "time": tuple(self.time), "tempo": self.tempo,
                "tempo_text": self.tempo_text, "ensemble": self.ensemble,
                "style": self.prof.display, "composer": self.prof.name,
                "sections": sections,
                "theme": {"notes": len(motif.rhythm) + len(motif.second),
                          "shape": sum(motif.steps), "upbeat": bool(motif.anacrusis),
                          "answer": self.responses.get("theme"),
                          "own": self.theme is not None},
                "contrast": {"notes": len(contrast.rhythm) + len(contrast.second),
                             "shape": sum(contrast.steps)}}

    # ------------------------------------------------------------------
    def _upbeat_of(self, ps: PhraseSpec, written: list[Written], writers) -> F:
        """How long the upbeat into phrase ``ps`` will be (0 if none)."""
        if ps.recall is not None and ps.recall < len(written):
            return written[ps.recall].upbeat
        if ps.kind == "intro":
            return F(0)
        writer = writers["B"] if ps.role == "contrast" else writers["A"]
        roles = roles_for(ps.kind, ps.bars)
        if roles and roles[0] in ("idea", "recall:0") and writer.motif.anacrusis:
            return sum(writer.motif.anacrusis, F(0))
        return F(0)

    def _intro(self, ps: PhraseSpec, t: F, hstyle) -> Written:
        """The accompaniment alone: the tonic, perhaps coloured, over a pedal —
        or, for a longer opening that leads somewhere, a progression that
        gathers on the dominant."""
        key = ps.key
        tonic = "i" if key.is_minor else "I"
        if ps.bars >= 3:
            mode = "minor" if key.is_minor else "major"
            colour = self.rng.choice([p for _, p in hstyle.tonic[mode]])
            pre = self.rng.choice([p for _, p in hstyle.predominant[mode]])
            labels = ([tonic] + [c for c in colour[1:] if c != tonic][:1] + pre[:1])[:ps.bars - 1]
            while len(labels) < ps.bars - 1:
                labels.append(labels[-1])
            labels.append("V")
            hs = [Harmony(r, key, t + self.bar * k, self.bar) for k, r in enumerate(labels)]
            hs[-1].cadence = "HC"
            return Written(ps, t, hs, [], [])
        if ps.bars == 1:
            labels = [tonic]
        else:
            pool = [p for _, p in hstyle.tonic["minor" if key.is_minor else "major"]
                    if len(p) >= 2]
            pat = self.rng.choice(pool) if pool else [tonic]
            labels = [tonic, pat[1] if len(pat) > 1 else tonic]
        dur = self.bar * ps.bars / len(labels)
        hs = [Harmony(r, key, t + dur * k, dur, pedal=key.tonic_pc if k else None)
              for k, r in enumerate(labels)]
        if len(hs) == 2 and hs[0].roman == hs[1].roman:
            hs = [Harmony(tonic, key, t, self.bar * ps.bars)]
        return Written(ps, t, hs, [], [])

    def _phrase(self, ps: PhraseSpec, t: F, hstyle, mstyle, writer: MelodyWriter,
                last_note: int | None, written: list[Written], upbeat: F, tail: F,
                final: bool) -> Written:
        hkind = {"sentence": "open", "antecedent": "open", "consequent": "open",
                 "continuation": "continuation", "development": "sequence",
                 "closing": "closing", "intro": "open"}.get(ps.kind, "open")
        roles = roles_for(ps.kind, ps.bars)
        presentation = len(roles) >= 4 and roles[2] == "repeat"
        shift = 0
        if presentation:
            opts = _RESPONSES.get(self.prof.harmony, _RESPONSES["romantic"])
            shift = self.rng.choices([o for o, _ in opts], [w for _, w in opts])[0]
            self.responses.setdefault(ps.role, shift)
        prefix, prefix_bars = [], 0
        if ps.kind == "consequent":
            ante = _antecedent_of(ps, written)
            if ante is not None:
                prefix_bars = sum(1 for r in roles if r.startswith("recall:"))
                prefix = _borrow(ante, prefix_bars, self.bar, t)
                if not prefix:
                    prefix_bars = 0
        spec = PhraseHarmonySpec(key=ps.key, start=t, bars=ps.bars, bar_len=self.bar,
                                 cadence=ps.cadence, kind=hkind, beat=self.beat,
                                 pedal=(ps.role == "closing" and prof_pedal(self.prof)),
                                 pedal_pc=((ps.key.tonic_pc + 7) % 12
                                           if ps.role == "transition" and ps.cadence == "HC"
                                           and prof_pedal(self.prof) else None),
                                 presentation=presentation, prefix=prefix,
                                 prefix_bars=prefix_bars,
                                 idea_bar2=writer.motif.bar2 if roles and roles[0] == "idea"
                                 else "", response_shift=shift)
        harmony = plan_phrase(spec, hstyle, self.rng, tries=self.care.harmony_tries)
        imitate = ps.texture == "imitation" and len(roles) > 1 and roles[1] == "idea2"
        if imitate:
            harmony = _answer_harmony(harmony, t, self.bar)
        bass = _bass_line(harmony, self.prof.bass_low)
        low, high, top = mstyle.low, mstyle.high, mstyle.climax_high
        if self.ensemble in _arrange.LEAD_RANGE:
            low, high, top = _arrange.LEAD_RANGE[self.ensemble]
        if ps.register == "tenor" and self.ensemble == "solo_piano":
            low, high, top = 48, 64, 67
        peak = int(round(low + (high - low) * (0.5 + 0.45 * ps.energy)))
        if roles and roles[0] == "idea":
            # room above the idea and its repeat for the phrase to climb past them
            start = low + (high - low) * 0.35
            need = (max(writer.motif.contour) + max(0, shift % 7 if shift % 7 <= 3 else 0)) * 1.75
            peak = max(peak, int(round(start + need + 3)))
        peak = min(peak, high + 2)
        if ps.role == "climax":
            peak = top
        elif ps.role == "closing":
            peak = int(round(low + (high - low) * 0.55))
        prev_h = written[-1].harmony[-1] if written and written[-1].harmony else None
        anacrusis = list(writer.motif.anacrusis) if upbeat and roles and \
            roles[0] in ("idea", "recall:0") else []
        best, best_score = None, -1e18
        for _take in range(self.care.melody_takes):
            peak_at = (0.55 + 0.25 * self.rng.random()) if ps.kind != "closing" else 0.3
            pp = PhrasePlan(start=t, bars=ps.bars, bar_len=self.bar, time=self.time,
                            key=ps.key, harmony=harmony, cadence=ps.cadence, bar_roles=roles,
                            peak_at=peak_at, peak=peak,
                            start_near=last_note if not ps.new_section else None,
                            low=low, high=high, energy=ps.energy, bass=bass, final=final,
                            anacrusis=anacrusis, prev_harmony=prev_h, tail_room=tail,
                            response_shift=shift, imitate=imitate)
            mel = writer.write(pp)
            sc = judge_melody(mel, pp) - 0.12 * writer.last_cost
            if _DEBUG_TAKES:
                print(f"take {_take}: judge {judge_melody(mel, pp):.2f} cost {writer.last_cost:.1f} "
                      f"-> {sc:.2f}: {' '.join(str(n.pitch) for n in mel[:12])}")
            if sc > best_score:
                best, best_score = mel, sc
        up = sum(anacrusis, F(0)) if best and best[0].onset < t else F(0)
        if best:
            # the melody has its say: chords that fight it are recoloured
            body = [n for n in best if n.onset >= t]
            cad = 3 if ps.cadence in ("PAC", "IAC", "HC", "plagal", "DC") else 1
            harmony = revise(harmony, body, hstyle, ps.key, self.beat, protect=cad)
            for n in body:
                n.pitch = spell(n.midi, harmony_at(harmony, n.onset))
            respell_line(body, harmony, ps.key)
        return Written(ps, t, harmony, best or [], [], upbeat=up)

    def _recall(self, src: Written, ps: PhraseSpec, t: F, written: list[Written]) -> Written:
        """An earlier phrase returns: same harmony (in this phrase's key) and
        the same melody, varied as the form asks."""
        shift = t - src.start
        semis = 0
        if src.spec.key != ps.key:
            semis = (ps.key.tonic_pc - src.spec.key.tonic_pc) % 12
            if semis > 6:
                semis -= 12
        harmony = [Harmony(h.roman, ps.key, h.onset + shift, h.dur, pedal=(
            (h.pedal + semis) % 12 if h.pedal is not None else None), cadence=h.cadence)
            for h in src.harmony]
        if ps.cadence != src.spec.cadence and harmony:
            # the return closes where the original only paused
            last = harmony[-1]
            tonic = "I" if not ps.key.is_minor else "i"
            if ps.cadence in ("PAC", "plagal", "DC"):
                arrival = tonic if ps.cadence != "DC" else ("VI" if ps.key.is_minor else "vi")
                harmony[-1] = Harmony(arrival, ps.key, last.onset, last.dur, cadence=ps.cadence)
                if len(harmony) >= 2 and harmony[-2].function != "D":
                    h2 = harmony[-2]
                    harmony[-2] = Harmony("V7", ps.key, h2.onset, h2.dur)
        melody = []
        for m in src.melody:
            melody.append(MelNote(m.onset + shift, m.dur, m.midi + semis, None, m.role,
                                  list(m.marks)))
        if ps.cadence in ("PAC", "plagal", "DC") and melody:
            tonic_pc = ps.key.tonic_pc
            last = melody[-1]
            if last.midi % 12 != tonic_pc:
                cands = [x for x in range(last.midi - 6, last.midi + 7) if x % 12 == tonic_pc]
                last.midi = min(cands, key=lambda x: abs(x - last.midi))
                # the note before steps into it
                if len(melody) >= 2 and abs(melody[-2].midi - last.midi) > 4:
                    before = melody[-2]
                    h = harmony_at(harmony, before.onset)
                    opts = [x for x in range(last.midi - 2, last.midi + 3)
                            if x != last.midi and x % 12 in h.pcs]
                    if opts:
                        before.midi = min(opts, key=lambda x: abs(x - before.midi))
        prev_h = written[-1].harmony[-1] if written and written[-1].harmony else None
        for m in melody:
            h = prev_h if (m.onset < t and prev_h is not None) else harmony_at(harmony, m.onset)
            m.pitch = spell(m.midi, h)
        respell_line([m for m in melody if m.onset >= t], harmony, ps.key)
        if ps.variation == "ornament":
            melody = _ornament(melody, harmony, self.rng, self.prof.ornaments, self.beat,
                               ps.key)
        return Written(ps, t, harmony, melody, [], upbeat=src.upbeat)

    # ------------------------------------------------------------------
    def _sheet(self, written: list[Written], form: FormPlan, end: F) -> Sheet:
        if self.ensemble != "solo_piano":
            return self._ensemble_sheet(written, end)
        plan, prof = self.plan, self.prof
        bars = int(end / self.bar)
        sheet = Sheet(title=plan.title, subtitle=plan.subtitle or "", key=self.key,
                      time=self.time, tempo=self.tempo, tempo_text=self.tempo_text,
                      composer="Motif.AI", bars=bars, parts=[("Pno", "piano", "")])
        rh = Voice("RH")
        rh2 = Voice("RH2", secondary=True)
        lh = Voice("LH")
        final_bar = end - self.bar

        # -- key signatures and section breaks
        self._key_changes(sheet, written)

        # -- the right hand: the melody, doubled or filled out where the music swells
        for wi, w in enumerate(written):
            ps = w.spec
            fill = ""
            if ps.variation == "octaves" and prof.octave_climax:
                fill = "full" if ps.role == "climax" else "octaves"
            elif ps.role == "climax" and prof.octave_climax:
                fill = "octaves"
            elif ps.variation == "planing":
                fill = "planing"
            prev_h = written[wi - 1].harmony[-1] if wi and written[wi - 1].harmony else None
            _melody_to_voice(lh if ps.register == "tenor" else rh, w.melody, fill, w.harmony,
                             w.start, prev_h)
        _group_tuplets(rh.notes)
        # the last melody note becomes a full chord
        _final_rh_chord(rh, written[-1], final_bar)
        # a singing inner voice under the tune, where the left hand leaves room
        for w in written:
            ps = w.spec
            if ps.role in ("theme", "return", "contrast") and ps.texture in _LH_ONLY and \
                    ps.register != "tenor" and \
                    ps.variation != "octaves" and w.melody and \
                    self.rng.random() < prof.inner:
                rh2.notes.extend(_inner_line(w, self.beat, final_bar))

        # -- the accompaniment, kept clear of the right hand
        lh2 = Voice("LH2", secondary=True)
        tenor_lines = Voice("tenor")
        for w in written:
            if w.spec.register == "tenor":
                _melody_to_voice(tenor_lines, w.melody, "", w.harmony, w.start, None)
        ctx = TextureContext(self.time, self.bar, self.beat, self.key,
                             bass_low=prof.bass_low, rng=self.rng, tempo=float(self.tempo),
                             virtuoso=_virtuoso(prof))
        ctx.melody_floor, ctx.melody_top = _rh_extent(rh, self.bar, end)
        if tenor_lines.notes:
            t_low, t_top = _rh_extent(tenor_lines, self.bar, end)
            for k, v in t_low.items():
                ctx.melody_floor.setdefault(k, v)
            for k, v in t_top.items():
                ctx.melody_top.setdefault(k, v)
        for wi, w in enumerate(written):
            ps = w.spec
            ctx.key = ps.key
            ctx.energy = ps.energy
            ctx.melody = w.melody
            span_end = w.start + self.bar * ps.bars
            last = wi == len(written) - 1
            tex = realise(ps.texture, w.harmony, w.start, final_bar if last else span_end, ctx)
            if last:
                h = harmony_at(w.harmony, final_bar)
                tex += final_chord(h, final_bar, self.bar, ctx)
            elif ps.cadence in ("PAC", "HC", "IAC", "plagal") and ps.texture in _FLOWING and \
                    self.rng.random() < 0.45:
                tex = _breathe(tex, w.harmony, span_end, self.bar, self.beat, ctx)
            w.texture = tex
            if ps.register == "tenor":
                # the right hand is free of the tune: its chords are the upper voice
                _texture_to_voices([n for n in tex if n.staff == "RH"], w.harmony, rh, rh)
                _texture_to_voices([n for n in tex if n.staff != "RH"], w.harmony, lh2, lh2)
            else:
                _texture_to_voices(tex, w.harmony, lh, rh2)

        # -- dynamics, words, phrasing and pedalling
        for wi, w in enumerate(written):
            self._mark_phrase(rh, lh, w, first=(wi == 0))
        self._tempo_changes(sheet, rh, written)
        _final_marks(rh, lh, rh2, end, self.bar)
        sheet.bar_info.setdefault(bars, BarInfo()).barline = "final"
        sheet.voices = [rh, rh2, lh] + ([lh2] if lh2.notes else [])
        return sheet

    def _ensemble_sheet(self, written: list[Written], end: F) -> Sheet:
        plan = self.plan
        bars = int(end / self.bar)
        sheet = Sheet(title=plan.title, subtitle=plan.subtitle or "", key=self.key,
                      time=self.time, tempo=self.tempo, tempo_text=self.tempo_text,
                      composer="Motif.AI", bars=bars)
        self._key_changes(sheet, written)
        parts, voices = _arrange.arrange(self, written, end)
        sheet.parts = parts
        lead = voices[0]
        for wi, w in enumerate(written):
            ps = w.spec
            if ps.words and w.melody:
                lead.marks.append(Mark(w.melody[0].onset, "text", ps.words))
            if w.melody and self.prof.harmony != "baroque":
                _slur(w.melody, self.bar, self.beat)
        for v in voices:
            final = [n for n in v.notes if n.pitches]
            if final:
                n = max(final, key=lambda x: x.onset)
                if "fermata" not in n.marks:
                    n.marks = list(n.marks) + ["fermata"]
        lead.marks.append(Mark(end - self.bar * 2, "above", "rit."))
        sheet.bar_info.setdefault(bars, BarInfo()).barline = "final"
        sheet.voices = voices
        return sheet

    def _key_changes(self, sheet: Sheet, written: list[Written]) -> None:
        prof = self.prof
        sig = self.key
        for wi, w in enumerate(written):
            ps = w.spec
            if wi == 0:
                continue
            bar_no = int(w.start / self.bar) + 1
            home = ps.key == self.key
            modern = prof.harmony not in ("classical", "baroque") or ps.section in ("Trio",)
            if ps.key.fifths != sig.fifths and (ps.new_section or home) and \
                    (modern or sig.fifths != self.key.fifths):
                sheet.bar_info.setdefault(bar_no, BarInfo()).key = ps.key
                sheet.bar_info.setdefault(bar_no - 1, BarInfo()).barline = "double"
                sig = ps.key
            elif ps.new_section and ps.section == "coda":
                sheet.bar_info.setdefault(bar_no - 1, BarInfo()).barline = "double"

    def _tempo_changes(self, sheet: Sheet, rh: Voice, written: list[Written]) -> None:
        """Where the tempo breathes: a little held back before each new
        section (broadened before a climax), the middle section of a
        Romantic piece moving on (Più mosso) and the return restoring the
        first tempo (Tempo I)."""
        prof = self.prof
        if prof.rubato < 0.12:
            return
        faster = False
        for wi, w in enumerate(written[:-1]):
            nxt = written[wi + 1]
            if not nxt.spec.new_section or w.spec.kind == "intro":
                continue
            broad = nxt.spec.role == "climax"
            rh.marks.append(Mark(nxt.start - self.bar, "above",
                                 "allargando" if broad else "poco rit."))
            bar_no = int(nxt.start / self.bar) + 1
            info = sheet.bar_info.setdefault(bar_no, BarInfo())
            if nxt.spec.role == "contrast" and nxt.spec.energy >= 0.55 and prof.rubato >= 0.15 \
                    and not faster:
                info.tempo = round(self.tempo * 1.15)
                info.tempo_text = "Più mosso"
                faster = True
            elif faster and nxt.spec.role in ("return", "climax", "closing"):
                info.tempo = self.tempo
                info.tempo_text = "Tempo I"
                faster = False
            elif not broad:
                rh.marks.append(Mark(nxt.start - nxt.upbeat, "above", "a tempo"))

    # ------------------------------------------------------------------
    def _mark_phrase(self, rh: Voice, lh: Voice, w: Written, first: bool) -> None:
        prof = self.prof
        ps = w.spec
        at = w.melody[0].onset if w.melody else w.start
        dyn = _energy_dynamic(prof, ps.energy)
        if ps.role == "closing" and ps.section == "coda":
            dyn = prof.dynamics[0]
        if first or ps.new_section or dyn != self._last_dyn:
            (rh if w.melody else lh).marks.append(Mark(at, "dyn", dyn))
            self._last_dyn = dyn
        if ps.words and ps.words.lower() != (self.tempo_text or "").lower():
            rh.marks.append(Mark(at, "text", ps.words))
        mel = [n for n in w.melody if n.onset >= w.start]
        if ps.role == "transition" and len(mel) >= 2:
            # the passage leading home grows all the way into what comes next
            rh.marks.append(Mark(mel[0].onset, "cresc"))
            rh.marks.append(Mark(mel[-1].onset, "end"))
        # a swell into the phrase's high point and away from it, over a bar or two
        elif len(mel) > 4 and ps.role not in ("closing", "intro"):
            peak = max(mel, key=lambda n: (n.midi, -n.onset))
            rise = [n for n in mel
                    if peak.onset - self.bar * 2 <= n.onset < peak.onset - self.beat]
            if rise:
                rh.marks.append(Mark(rise[0].onset, "cresc"))
                rh.marks.append(Mark(peak.onset, "end"))
            after = [n for n in mel if peak.onset < n.onset <= peak.onset + self.bar * 2]
            if len(after) >= 2:
                rh.marks.append(Mark(after[0].onset, "dim"))
                rh.marks.append(Mark(after[-1].onset, "end"))
        # slurs over each breath of the melody
        if w.melody and prof.harmony != "baroque":
            _slur(w.melody, self.bar, self.beat)
        # pedal with every change of harmony
        if prof.pedal == "harmony":
            for h in w.harmony:
                lh.marks.append(Mark(h.onset, "ped"))
        elif prof.pedal == "sparse" and ps.role in ("closing", "climax"):
            lh.marks.append(Mark(w.harmony[0].onset, "ped"))


# ---------------------------------------------------------------------------
# themes
# ---------------------------------------------------------------------------
def invent_contrast(style, main: Motif, time, rng: random.Random, candidates: int) -> Motif:
    """A second theme that sounds like the same composer but not the same
    tune: another rhythm, another gesture."""
    best, best_score = None, -1e9
    for _ in range(max(4, candidates)):
        m = _random_motif(style, time, rng, lively=True)
        s = motif_score(m, style) + implied_fit(m, time)
        # the middle of a piece moves more than its opening
        s += 0.6 * max(-2, min(4, len(m.rhythm) - len(main.rhythm)))
        if len(m.rhythm) < 3:
            s -= 1.5
        s += 1.0 * len(set(m.rhythm) ^ set(main.rhythm)) / max(1, len(set(m.rhythm)))
        if (sum(m.steps) > 0) != (sum(main.steps) > 0):
            s += 1.0
        if m.rhythm == main.rhythm:
            s -= 4
        if s > best_score:
            best, best_score = m, s
    return best


def implied_fit(m: Motif, time) -> float:
    return implied_harmony(m, time)[0]


def _describe_motif(name: str, m: Motif) -> str:
    shape = "rising" if sum(m.steps) > 0 else "falling" if sum(m.steps) < 0 else "arching"
    up = "with an upbeat, " if m.anacrusis else ""
    return f"{name}: a {len(m.rhythm)}-note idea, {up}{shape}."


# ---------------------------------------------------------------------------
# judging
# ---------------------------------------------------------------------------
def judge_melody(notes: list[MelNote], plan: PhrasePlan) -> float:
    """A whole-phrase verdict: mostly stepwise, one climax, varied rhythm,
    no stagnation, a proper close."""
    if not notes:
        return -1e9
    mids = [n.midi for n in notes]
    steps = [abs(b - a) for a, b in zip(mids, mids[1:])]
    if not steps:
        return 0.0
    stepwise = sum(1 for s in steps if 1 <= s <= 2) / len(steps)
    leaps = sum(1 for s in steps if s >= 5) / len(steps)
    repeats = sum(1 for s in steps if s == 0) / len(steps)
    score = 0.0
    score -= 6 * abs(stepwise - 0.6)
    score -= 4 * max(0.0, leaps - 0.2)
    score -= 3 * max(0.0, repeats - 0.2)
    top = max(mids)
    score -= 1.5 * (mids.count(top) - 1)
    rng = top - min(mids)
    score -= 0.3 * max(0, rng - 17)
    score -= 0.6 * max(0, 9 - rng)
    durs = {n.dur for n in notes}
    score += 0.5 * min(len(durs), 4)
    last = mids[-1]
    deg = (last - plan.key.tonic_pc) % 12
    if plan.cadence == "PAC" and deg != 0:
        score -= 4
    # bars that merely copy the bar before them
    bars: dict[int, list[int]] = {}
    for n in notes:
        bars.setdefault(int((n.onset - plan.start) // plan.bar_len), []).append(n.midi)
    seq = [tuple(v) for _k, v in sorted(bars.items())]
    score -= 1.5 * sum(1 for a, b in zip(seq, seq[1:]) if a == b and len(a) > 1)
    return score


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _virtuoso(prof: Profile) -> bool:
    return prof.octave_climax or prof.name in ("chopin", "liszt", "rachmaninoff", "scriabin")


def prof_pedal(prof: Profile) -> bool:
    return prof.harmony in ("russian", "romantic", "impressionist")


def _label(ps: PhraseSpec) -> str:
    return {"theme": "Writing the theme", "contrast": "Writing the middle section",
            "climax": "Building the climax", "return": "Bringing the theme back",
            "closing": "Writing the coda", "transition": "Leading back",
            "development": "Developing the material", "intro": "Setting the scene"
            }.get(ps.role, "Writing")


def _sections(form: FormPlan) -> list[str]:
    out = []
    for p in form.phrases:
        if not out or out[-1] != p.section:
            out.append(p.section)
    return out


def _by_bar(notes: list[MelNote], start: F, bar: F, bars: int) -> list[list[MelNote]]:
    out: list[list[MelNote]] = [[] for _ in range(bars)]
    for n in notes:
        if n.onset < start:
            continue
        b = int((n.onset - start) / bar)
        if 0 <= b < bars:
            out[b].append(n)
    return out


_EASY_TEXTURES = {"alberti": "alberti", "waltz": "waltz", "block": "block",
                  "sustained": "sustained", "walking": "block"}


def _simplify(form: FormPlan, prof: Profile) -> FormPlan:
    """A piece a learner can play: no introduction, an easy left hand,
    nothing thundering, no octaves or ornaments."""
    phrases = [p for p in form.phrases if p.kind != "intro"]
    shift = len(form.phrases) - len(phrases)
    for p in phrases:
        if p.recall is not None:
            p.recall -= shift
        p.texture = _EASY_TEXTURES.get(p.texture, "block")
        p.energy = min(p.energy, 0.6)
        p.variation = "" if p.variation in ("octaves", "ornament") else p.variation
        if p.role == "climax":
            p.role = "return"
    form.phrases = phrases
    return form


def _answer_harmony(harmony: list[Harmony], start: F, bar: F) -> list[Harmony]:
    """In an invention the answer in the second bar carries the subject's
    own harmony: bar 1's chords, again."""
    first = [h for h in harmony if h.onset < start + bar]
    rest = [h for h in harmony if h.onset >= start + 2 * bar]
    if not first or not rest:
        return harmony
    out = []
    for h in first:
        d = min(h.end, start + bar) - h.onset
        out.append(Harmony(h.roman, h.key, h.onset, d, pedal=h.pedal))
    for h in first:
        d = min(h.end, start + bar) - h.onset
        out.append(Harmony(h.roman, h.key, h.onset + bar, d, pedal=h.pedal))
    return out + rest


def _antecedent_of(ps: PhraseSpec, written: list[Written]) -> Written | None:
    for w in reversed(written):
        if w.spec.section == ps.section and w.spec.kind in ("antecedent", "sentence") \
                and w.spec.recall is None:
            return w
        if w.spec.section != ps.section:
            break
    return None


def _borrow(src: Written, bars: int, bar: F, at: F) -> list[Harmony]:
    """The harmony of the first ``bars`` bars of ``src``, moved to ``at``."""
    limit = src.start + bar * bars
    out = []
    for h in src.harmony:
        if h.onset >= limit:
            break
        dur = min(h.end, limit) - h.onset
        out.append(Harmony(h.roman, h.key, h.onset - src.start + at, dur, pedal=h.pedal))
    return out


def _bass_line(harmony: list[Harmony], low: int) -> list[tuple[F, int]]:
    out, prev = [], None
    for h in harmony:
        pc = h.bass_pc
        cands = [m for m in range(max(low, 28), 55) if m % 12 == pc]
        m = min(cands, key=lambda x: abs(x - (prev if prev is not None else 40)))
        out.append((h.onset, m))
        prev = m
    return out


def _tidy_melody(written: list[Written]) -> None:
    """One line: a note that runs into the next one (an upbeat borrowed from
    the phrase before) is shortened, or dropped if nothing is left of it."""
    allnotes = sorted((n for w in written for n in w.melody), key=lambda n: n.onset)
    drop = set()
    for a, b in zip(allnotes, allnotes[1:]):
        if a.end > b.onset:
            if b.onset <= a.onset:
                drop.add(id(a))
            else:
                a.dur = b.onset - a.onset
    if drop:
        for w in written:
            w.melody = [n for n in w.melody if id(n) not in drop]


def _rh_extent(rh: Voice, bar: F, end: F) -> tuple[dict, dict]:
    """The lowest and highest right-hand notes in each half bar, so the
    accompaniment stays under the melody and inside the hand's reach."""
    lows, highs = {}, {}
    half = bar / 2
    t = F(0)
    while t < end:
        ps = [p.midi for n in rh.notes if n.onset < t + half and n.end > t
              for p in n.pitches]
        if ps:
            lows[(t, t + half)] = min(ps)
            highs[(t, t + half)] = max(ps)
        t += half
    return lows, highs


def _chord_fill(p: Pitch, h: Harmony, octave: bool, inner: bool) -> list[Pitch]:
    """The right hand's notes under a melody note: the octave below, and a
    chord tone between when the music is at its fullest."""
    out = []
    low = p.midi - 12
    if octave:
        out.append(Pitch.build(p.step, p.alter, p.octave - 1))
    if inner and p.midi % 12 in h.pcs:
        lo = low + 3 if octave else p.midi - 9
        mids = [m for m in range(lo, p.midi - 2) if m % 12 in h.pcs and m % 12 != p.midi % 12]
        if mids:
            centre = (p.midi + (low if octave else p.midi - 12)) / 2
            m = min(mids, key=lambda x: abs(x - centre))
            out.append(spell(m, h))
    return out


def _planed(p: Pitch, m: MelNote, h: Harmony) -> list[Pitch]:
    """Debussy's planing: the tune's longer notes carried by a chord of the
    same shape under each — thirds stacked down the scale — so the harmony
    moves in parallel with the melody."""
    from .melody import _transpose_steps
    if m.dur < F(1, 2):
        return [p]
    notes = [m.midi]
    for k in (2, 4, 6):
        notes.append(_transpose_steps(m.midi, -k, h.key))
    notes = [x for x in notes if m.midi - x <= 11]
    out = [spell(x, h) for x in sorted(set(notes)) if x != m.midi] + [p]
    return sorted(out, key=lambda x: x.midi)


def _melody_to_voice(rh: Voice, melody: list[MelNote], fill: str, harmony: list[Harmony],
                     start: F, prev_h: Harmony | None) -> None:
    for m in sorted(melody, key=lambda n: n.onset):
        p = m.pitch or Pitch.build("C", 0, 4)
        pitches = [p]
        if fill == "planing":
            h = prev_h if (m.onset < start and prev_h is not None) else \
                harmony_at(harmony, m.onset)
            pitches = _planed(p, m, h)
        elif fill:
            h = prev_h if (m.onset < start and prev_h is not None) else \
                harmony_at(harmony, m.onset)
            pitches = sorted(_chord_fill(p, h, octave=True,
                                         inner=(fill == "full" and m.dur >= F(1, 2))) + [p],
                             key=lambda x: x.midi)
        rh.add(Note(m.onset, m.dur, pitches, tie=m.tie, marks=list(m.marks),
                    graces=list(m.graces), slur_start=m.slur_start, slur_stop=m.slur_stop))


#: Textures that keep entirely to the left hand, leaving the right hand's
#: second voice free.
_LH_ONLY = ("nocturne", "sweep", "sweep16", "bells", "waltz", "alberti", "repeated", "walking",
            "sustained")


#: Figurations that run on without a break — at a cadence they can stop to
#: let the phrase breathe.
_FLOWING = ("nocturne", "sweep", "sweep16", "alberti", "repeated")


def _breathe(tex: list[TexNote], harmony: list[Harmony], end: F, bar: F, beat: F,
             ctx: TextureContext) -> list[TexNote]:
    """At a cadence the figuration comes to rest: the last half bar of the
    phrase becomes its chord, held — the bass and the harmony above it — so
    the end of the phrase is heard as an end."""
    half = bar / 2 if bar >= 2 * beat else bar
    beats = -(-half // beat)                  # whole beats, rounded up
    cut = end - beat * beats
    # never cut a triplet group in two: stop before any group that crosses
    group_start = None
    for n in sorted(tex, key=lambda x: x.onset):
        if n.tuplet_start:
            group_start = n.onset
        if n.tuplet is not None and group_start is not None and n.onset < cut < n.onset + n.dur:
            cut = group_start
        if n.tuplet_stop:
            if group_start is not None and group_start < cut < n.onset + n.dur:
                cut = group_start
            group_start = None
    kept = [n for n in tex if n.onset < cut]
    for n in kept:
        if n.onset + n.dur > cut:
            n.dur = cut - n.onset
    h = harmony_at(harmony, cut)
    lows = [m for n in tex if n.onset >= cut for m in n.midis]
    if not lows:
        return tex
    b = min(lows)
    top = min(b + 16, max(lows))
    above = sorted({m for m in range(b + 3, top + 1) if m % 12 in h.pcs})
    chord = [b] + [m for i, m in enumerate(above) if i < 2]
    if chord[-1] - chord[0] > 16:
        chord = [b]
    kept.append(TexNote(cut, end - cut, chord, marks=["arp"] if chord[-1] - chord[0] > 10
                        else []))
    return kept


def _inner_line(w: Written, beat: F, stop: F) -> list[Note]:
    """A second voice in the right hand, under the tune: one long note to a
    chord, moving by step where it can, sometimes held into the next chord
    as a suspension that falls to its resolution — always below the melody
    and within the hand's reach of it."""
    mel = sorted((n for n in w.melody if n.onset >= w.start), key=lambda n: n.onset)
    out: list[Note] = []
    prev: int | None = None
    hs = [h for h in w.harmony if h.onset < stop]
    for k, h in enumerate(hs):
        end = min(h.end, stop)
        over = [n.midi for n in mel if n.onset < end and n.end > h.onset]
        if not over:
            prev = None
            continue
        lo, hi = max(over) - 10, min(over) - 3
        cands = [m for m in range(lo, hi + 1) if m % 12 in h.pcs and m >= 55]
        if not cands:
            prev = None
            continue
        target = prev if prev is not None else (lo + hi) // 2
        m = min(cands, key=lambda x: (abs(x - target) if prev is None else
                                      (0 if x == prev else abs(x - prev) + (0 if abs(x - prev) <= 2
                                                                           else 3)), x))
        dur = end - h.onset
        nxt = hs[k + 1] if k + 1 < len(hs) else None
        # a suspension: held over the change and falling a step to a chord tone
        if nxt is not None and m % 12 not in nxt.pcs and dur >= 2 * beat and nxt.end - nxt.onset >= 2 * beat:
            res = [x for x in (m - 1, m - 2) if x % 12 in nxt.pcs]
            nxt_over = [n.midi for n in mel if n.onset < nxt.onset + beat and n.end > nxt.onset]
            if res and nxt_over and max(nxt_over) - res[0] <= 10 and min(nxt_over) - m >= 3:
                out.append(Note(h.onset, dur, [spell(m, h)], tie=True))
                out.append(Note(nxt.onset, beat, [spell(m, h)]))
                out.append(Note(nxt.onset + beat, nxt.end - nxt.onset - beat,
                                [spell(res[0], nxt)]))
                prev = res[0]
                hs[k + 1] = None if False else nxt
                continue
        if out and out[-1].onset + out[-1].dur > h.onset:
            continue                      # this chord's start is covered by a suspension
        out.append(Note(h.onset, dur, [spell(m, h)]))
        prev = m
    # drop anything overlapping (a suspension already covered it)
    clean: list[Note] = []
    for n in sorted(out, key=lambda x: x.onset):
        if clean and n.onset < clean[-1].onset + clean[-1].dur:
            continue
        clean.append(n)
    return clean


def _final_rh_chord(rh: Voice, last: Written, final_bar: F) -> None:
    """The melody's last note, sounding with its chord."""
    if not rh.notes or not last.harmony:
        return
    n = max(rh.notes, key=lambda x: x.onset)
    if n.onset < final_bar:
        return
    h = harmony_at(last.harmony, n.onset)
    top = max(n.pitches, key=lambda p: p.midi)
    if top.midi % 12 not in h.pcs:
        return
    fill = [spell(m, h) for m in range(top.midi - 9, top.midi - 2)
            if m % 12 in h.pcs and m % 12 != top.midi % 12]
    keep = sorted({p.midi: p for p in list(n.pitches) + fill[-2:]}.values(),
                  key=lambda p: p.midi)
    if keep[-1].midi - keep[0].midi <= 12:
        n.pitches = keep


def _texture_to_voices(tex: list[TexNote], harmony: list[Harmony], lh: Voice, rh2: Voice
                       ) -> None:
    for n in tex:
        h = harmony_at(harmony, n.onset)
        pitches = sorted((spell(m, h) for m in n.midis), key=lambda p: p.midi)
        note = Note(n.onset, n.dur, pitches, marks=list(n.marks), tuplet=n.tuplet,
                    tuplet_start=n.tuplet_start, tuplet_stop=n.tuplet_stop)
        (rh2 if n.staff == "RH" else lh).add(note)


def _energy_dynamic(prof: Profile, energy: float) -> str:
    lo = _DYNAMICS.index(prof.dynamics[0])
    hi = _DYNAMICS.index(prof.dynamics[1])
    if energy >= 0.93:
        return prof.climax_dynamic
    idx = lo + round((hi - lo) * max(0.0, min(1.0, (energy - 0.15) / 0.7)))
    return _DYNAMICS[idx]


def _slur(melody: list[MelNote], bar: F, beat: F) -> None:
    """Slurs follow the breathing of the line: a slur closes on a long note
    that ends a bar, or before a wide leap, and never covers fewer than
    three notes."""
    notes = sorted(melody, key=lambda n: n.onset)
    group: list[MelNote] = []
    for i, n in enumerate(notes):
        group.append(n)
        nxt = notes[i + 1] if i + 1 < len(notes) else None
        breath = nxt is None
        if nxt is not None:
            long_end = n.dur >= 2 * beat and (n.end % bar == 0 or n.dur >= bar / 2)
            leap = abs(nxt.midi - n.midi) >= 7
            breath = (long_end or leap) and len(group) >= 3
        if breath:
            if len(group) >= 2:
                group[0].slur_start = 1
                group[-1].slur_stop = 1
            group = []


def _ornament(melody: list[MelNote], harmony: list[Harmony], rng: random.Random,
              amount: float, beat: F, key: Key) -> list[MelNote]:
    """Decorate a returning melody the way Chopin and Field do: grace notes
    and turns on some of its longer notes, and — now and then — a long note
    that dissolves into a quick run (fioritura) sweeping on to the next."""
    from .melody import _transpose_steps
    out: list[MelNote] = []
    last_run = F(-100)
    for i, m in enumerate(melody):
        nxt = melody[i + 1] if i + 1 < len(melody) else None
        if nxt is None:
            out.append(m)
            continue
        h = harmony_at(harmony, m.onset)
        run_room = m.dur >= 2 * beat and beat == 1 and m.onset - last_run >= 8 * beat
        if run_room and rng.random() < amount * 1.4 and abs(nxt.midi - m.midi) <= 7:
            # hold the note, then run to the next one in six quick notes
            hold = m.dur - beat
            out.append(MelNote(m.onset, hold, m.midi, m.pitch, m.role, list(m.marks),
                               slur_start=m.slur_start))
            up = nxt.midi >= m.midi
            start = _transpose_steps(m.midi, 2 if not up else -2, key)
            notes = [start]
            for _k in range(5):
                notes.append(_transpose_steps(notes[-1], -1 if not up else 1, key))
            t = m.onset + hold
            for k, p in enumerate(notes):
                out.append(MelNote(t + F(k, 6), F(1, 6), p, spell(p, h), "NCT"))
            last_run = m.onset
            continue
        graced = bool(out and out[-1].graces)
        if m.dur >= beat and not graced and rng.random() < amount * 0.4:
            upper = m.midi + (2 if (m.midi + 2) % 12 in set(h.key.scale_pcs) else 1)
            m.graces = [spell(upper, h)]
        elif m.dur >= 2 * beat and rng.random() < amount * 0.4:
            m.marks = list(m.marks) + ["turn"]
        out.append(m)
    return out


def _final_marks(rh: Voice, lh: Voice, rh2: Voice, end: F, bar: F) -> None:
    """Slow into the end and hold the last chord."""
    for v in (rh, lh, rh2):
        final = [n for n in v.notes if n.onset < end]
        if final and v is not rh2:
            n = max(final, key=lambda x: x.onset)
            if "fermata" not in n.marks:
                n.marks = list(n.marks) + ["fermata"]
    rh.marks.append(Mark(end - bar * 2, "above", "rit."))
    lh.marks.append(Mark(end, "pedup"))


#: How each kind of piece is named in a title.
_GENRE_TITLES = {
    "consolation": "Consolation", "elegie": "Élégie", "élégie": "Élégie", "elegy": "Elegy",
    "romance": "Romance", "etude-tableau": "Étude-tableau", "étude-tableau": "Étude-tableau",
    "etude tableau": "Étude-tableau", "lyric piece": "Lyric Piece",
    "gymnopedie": "Gymnopédie", "gymnopédie": "Gymnopédie", "gnossienne": "Gnossienne",
    "song without words": "Song without Words", "moment musical": "Moment musical",
    "berceuse": "Berceuse", "barcarolle": "Barcarolle", "reverie": "Rêverie",
    "rêverie": "Rêverie", "liebestraum": "Liebestraum", "arabesque": "Arabesque",
    "fantasy": "Fantasy", "fantasia": "Fantasia", "sonatina": "Sonatina",
    "minuet": "Minuet", "menuet": "Menuet", "gavotte": "Gavotte", "sarabande": "Sarabande",
    "gigue": "Gigue", "toccata": "Toccata", "polonaise": "Polonaise", "valse": "Valse",
    "nocturne": "Nocturne", "prelude": "Prelude", "prélude": "Prélude", "waltz": "Waltz",
    "mazurka": "Mazurka", "etude": "Étude", "étude": "Étude", "study": "Study",
    "sonata": "Sonata", "invention": "Invention", "fugue": "Fugue", "ballade": "Ballade",
    "rhapsody": "Rhapsody", "scherzo": "Scherzo", "intermezzo": "Intermezzo",
    "impromptu": "Impromptu", "concerto": "Concerto",
}
_FORMAL = ("Concerto", "Sonata", "Fugue", "Invention", "Waltz", "Nocturne", "Prelude",
           "Étude", "Rondo", "Mazurka", "Scherzo", "Ballade", "Rhapsody", "Intermezzo",
           "Impromptu", "Variations")


def _retitle(plan: CompositionPlan, genre: str, named: bool = False) -> None:
    """A title that names a different kind of piece from the one being
    written ("Étude in D♭" for a consolation) is corrected, a piece the
    musician asked for by name is called by that name, and keys are written
    with real sharps and flats."""
    import re
    name = _GENRE_TITLES.get((genre or "").lower())
    title = plan.title or ""
    head = title.split(" in ", 1)[0]
    user_titled = bool(re.search(r"\b(called|titled|named)\b", (plan.prompt or "").lower()))
    if name and not user_titled and (
            (head in _FORMAL and head != name and " in " in title) or
            (named and head not in _FORMAL)):
        plan.title = f"{name} in {plan.key}"
    plan.title = re.sub(r"\b([A-G])b\b", "\\1♭", re.sub(r"\b([A-G])#", "\\1♯", plan.title))


def compose_plan(plan: CompositionPlan, *, quality: str = "best", progress=None) -> Score:
    return Composer(plan, quality=quality, progress=progress).compose()
