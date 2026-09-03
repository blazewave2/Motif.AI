<div align="center">

# Motif.AI

**Your AI composing partner — a generative, agentic composer for MuseScore.**

Describe a piece in plain English. Motif plans it, writes it, and opens it in
MuseScore as fully engraved notation — slurs, pedalling, dynamics and all.

</div>

---

```
"Create a simple melody for me to play."

"Make a full Rachmaninoff style piano concerto using a dark Eb minor melody."
```

Both work. The first returns sixteen playable bars in a couple of hundred
milliseconds; the second returns a 120-bar concerto for piano and orchestra
with real solo/tutti alternation, a cadenza and a coda, in about a second.

## What it is

A dockable panel inside MuseScore Studio backed by a local composing engine.
The engine is the interesting part: it is not a language model writing note
names. It is a music-theory system — spelled pitch, functional harmony, voice
leading, formal templates, per-composer idiom libraries — driven by an agent
that turns your sentence into a structured plan.

That design is deliberate. A neural model trained on a public-domain corpus
gives you a plausible melodic voice; it does not give you a piece that
modulates to the relative major, develops its opening motif, and cadences
properly forty bars later. Motif splits the job:

| Layer | Owns | Why |
|---|---|---|
| **Prompt parser** | style, key, metre, tempo, form, mood, scope | Deterministic, instant, works offline |
| **Planner** *(optional Claude)* | section map, dramatic arc, key scheme | Where a language model genuinely helps |
| **Neural model** *(optional)* | the seed motif — the melodic voice | Learned from real scores |
| **Theory engine** | harmony, voice leading, texture, form | Guarantees it is *correct* music |
| **Engraver** | MusicXML / MIDI | Guarantees it is *readable* music |

Every layer above the theory engine is optional. With none of them installed
Motif still composes — it just leans entirely on its own musicianship.

## Install

Requires **Python 3.10+** and **MuseScore 4** (MuseScore 3 also works). There
are no Python packages to install: the engine runs on the standard library.

```bash
git clone https://github.com/blazewave2/Motif.AI
cd Motif.AI
python3 install.py
```

Then start the engine and enable the plugin:

```bash
./scripts/motif-serve          # Windows: scripts\motif-serve.bat
```

In MuseScore: **Plugins ▸ Manage plugins…** → enable **Motif.AI** →
**Plugins ▸ Motif.AI**. The panel finds the engine by itself.

### Without MuseScore

```bash
./scripts/motif-serve compose "a Chopin nocturne in Eb minor" -o out --midi
```

## How it composes

Ask for a Rachmaninoff concerto and this happens:

1. **Parse** — `rachmaninoff`, `Eb minor`, `piano_concerto`, `concerto` form,
   ~120 bars, character `dark`. The misspelling in "Rachmanninoff" is matched
   by edit distance.
2. **Plan** — the concerto template lays out Tutti I → Solo I → Transition →
   Solo II → Tutti II → Development → Cadenza → Recap → Coda, with a key
   scheme, an energy curve peaking at the cadenza, and a texture per section.
3. **Invent a motif** — a short cell of scale-degree steps plus a rhythm. Every
   later section is a transformation of it: inverted, sequenced, fragmented,
   augmented, recalled.
4. **Harmonise** — functional progressions coloured with applied dominants,
   borrowed chords and Neapolitans at rates drawn from the style profile, each
   section landing on a real cadence.
5. **Write the melody** — a structural skeleton of chord tones traces a
   registral contour; the gaps are filled by a scored search that prefers
   stepwise motion, resolves leaps, and treats dissonance the way a musician
   does.
6. **Orchestrate** — the same material is handed to ten instruments by role,
   with solo sections properly resting the orchestra.
7. **Engrave** — MusicXML with tied notes split at beat boundaries, slurs,
   hairpins, pedalling, articulations and grace notes.

## What you can ask for

Anything in this shape, and a great deal that is not:

- *"Compose a romantic piano piece in the style of Chopin"*
- *"Write a short film score for a mysterious forest scene"*
- *"A Bach fugue in D minor at 92 bpm, 24 bars"*
- *"Continue this piece in a more dramatic way"* — reads your open score
- *"Add a left hand accompaniment"* — keeps your melody, writes under it
- *"Transpose it to F# minor and make it slower"*
- *"What key is this in?"*

**23 composer styles** — Bach, Handel, Scarlatti, Vivaldi, Mozart, Haydn,
Clementi, Beethoven, Schubert, Chopin, Liszt, Brahms, Mendelssohn, Grieg,
Tchaikovsky, Rachmaninoff, Scriabin, Debussy, Ravel, Satie, and contemporary
minimal / cinematic idioms.

**30 forms** — nocturne, sonata, fugue, invention, rondo, variations, waltz,
mazurka, ballade, prelude, étude, intermezzo, concerto, and more.

**13 ensembles** — solo piano through full orchestra, string quartet, piano
trio, concerto, duo sonatas, organ, harpsichord, guitar.

## Training your own model

Motif ships without a checkpoint and works fully without one. To train the
optional neural model on Modal inside a **$30 budget**, see
**[docs/TRAINING.md](docs/TRAINING.md)**. Short version:

```bash
modal run training/modal_app.py --step corpus     # public-domain scores
modal run training/modal_app.py --step prepare    # tokenize + augment
modal run training/modal_app.py --step train --budget 22
modal run training/modal_app.py --step download
```

The budget is enforced inside the training loop, not just documented: the run
checkpoints and stops before the estimated spend crosses your cap.

## Privacy

The engine binds to `127.0.0.1` only, authenticates with a token written to
`~/.motif/config.json`, and rejects any request carrying an `Origin` header so
a web page cannot reach it. Your music never leaves your machine unless you
configure the optional Claude planner, which receives your prompt and the
draft plan — never your score.

## Development

```bash
pip install pytest music21          # for the test suite and data prep
cd engine && python -m pytest       # 182 tests
```

Docs: **[Architecture](docs/ARCHITECTURE.md)** · **[Training](docs/TRAINING.md)**

## Licence

MIT. Generated music is yours. Training corpora are separately licensed — see
[docs/TRAINING.md](docs/TRAINING.md).
