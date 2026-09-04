# Architecture

```
  MuseScore                                Local machine only
 ┌───────────────────────┐                ┌──────────────────────────────┐
 │  Motif.AI panel (QML) │  HTTP/JSON     │  Motif engine (Python)       │
 │  ─────────────────────│───────────────▶│  ──────────────────────────  │
 │  prompt, examples,    │  127.0.0.1     │  agent → plan → score        │
 │  conversation         │◀───────────────│  MusicXML + MIDI             │
 └───────────────────────┘   MusicXML     └──────────────────────────────┘
            │                                            │
            └── readScore() opens it in a new tab        └── optional:
                                                            torch checkpoint
                                                            Claude planner
```

## Why MusicXML rather than the cursor API

A plugin can add notes through MuseScore's cursor API, but slurs, pedalling,
hairpins, tuplets, grace notes and multi-voice piano writing are all awkward or
impossible that way. Generating MusicXML and calling `readScore()` gets every
one of them into the score intact, and it makes the engine independently
testable — the same output can be validated without MuseScore running at all.

## Engine layers

### `theory/`

`pitch.py` carries **spelled** pitches (step, alteration, octave), not MIDI
numbers. This is not pedantry: a diatonic step below E♭ in E♭ minor is D♭, and
a system that stores pitch class 1 has already lost the information needed to
write that. Accidentals are chosen from the key signature, so E♭ minor comes
out with C♭ and B major with A♯.

`harmony.py` stores chords as **(diatonic step, semitone) pairs**. A semitone
count alone cannot distinguish ♯4 from ♭5, which is why a naive engine writes
a diminished seventh as D–F–G♯–B instead of D–F–A♭–C♭.

### `compose/`

| Module | Responsibility |
|---|---|
| `styles.py` | 23 composer profiles: textures, chromaticism rates, dynamic range, registers, hand span, ornaments, and the scale collections a style colours with — whole-tone and pentatonic for Debussy, octatonic for Scriabin |
| `forms.py` | 30 formal templates producing a section map — bars, key, energy, texture, cadence, motif operation |
| `material.py` | Motifs as scale-degree steps, with inversion, retrograde, augmentation, fragmentation, sequence |
| `progression.py` | Functional progressions coloured with applied dominants, borrowed chords, extensions |
| `voicing.py` | Voicing search scored for parallels, spacing, doubling and tendency-tone resolution |
| `melody.py` | Structural skeleton over a registral contour, then a scored fill |
| `textures.py` | 20 accompaniment idioms, each constrained to a playable hand span |
| `orchestration.py` | Role-based distribution across 13 ensembles |
| `composer.py` | Assembles all of it, adds pedalling, slurs, articulation |
| `expression.py` | The performance layer: tempo map, per-note velocity, phrase hairpins |

### `agent/`

`prompt_parser.py` is the deterministic understanding layer — style, key,
metre, tempo, form, mood, scope and ensemble from free text. It runs first,
always. `llm_planner.py` optionally hands the draft plan to Claude for
revision, and **validates every field it gets back** against the allowed sets;
anything unrecognised falls back to the draft. `agent.py` routes six intents:
create, continue, develop, harmonize, edit, analyze.

### `model/`

`tokenizer.py` is stdlib-only and shared with training. `runtime.py` imports
torch lazily and degrades to `None` on any failure, so a missing or broken
checkpoint never stops the engine composing.

## The performance layer

Notes alone play back like a typewriter. `expression.py` runs after the music
exists and shapes three things a performer shapes:

**Tempo.** Phrases ease into their cadences, developments press forward, and
the piece slows at its close, written as real marks — *poco rit.*, *a tempo*,
*stringendo*, *rall.* How much give a style takes is a per-composer constant:
Bach 0.03, Chopin 0.20, Liszt 0.22. A Rachmaninov concerto ends up with a
tempo change roughly every five bars, ranging from 52 to 92; a Bach fugue gets
its opening tempo and a closing *rit.*, and nothing else.

**Volume.** Every note's velocity comes from where it sits in its phrase, how
high it is, where the beat falls, how long it is, and what is marked on it,
plus a little unevenness. Stepping between eight printed marks is what makes
playback sound typed. The melody is voiced above the accompaniment by a fixed
offset, which is how a pianist balances the hands.

**Rhythm.** Accompaniment figures vary bar to bar — resting on the last beat,
holding through, halving their motion, taking a dotted lilt, grouping 3+3+2,
or turning over in triplets. Before this, one Rachmaninov prelude used the
same bar-rhythm thirty-eight times out of forty.

Phrases are detected from slur ends, but *merged* into period-length spans:
shaping every slur would put a hairpin under every bar, which is the opposite
of phrasing.

## Design decisions worth knowing

**The engine has no required dependencies.** A musician installing a MuseScore
plugin should not have to create a virtualenv. Everything in `engine/` runs on
the standard library, including the HTTP server. torch and the Claude planner
are strictly optional.

**Bars are guaranteed complete.** `layout.place_voice` splits notes at bar
lines and at beat boundaries, tying the pieces, then every voice is padded to
the bar. The test suite asserts this across every style, form and ensemble —
an incomplete bar is the one error that makes a score unusable.

**Ranges are clamped last.** Octave doubling and register shifts compound, so a
final pass folds any note outside the instrument's range back into it.

**Seeds are reproducible.** The same prompt and seed produce a byte-identical
score; a different seed produces different music. "Try again" in the panel is
simply a new seed.

## Setup and lifetime

Setup is a small window (`setup/motif_setup.py`), wrapped per platform by the
launchers in `Install Motif/`: a real `.app` bundle on macOS, a windowless
`.pyw` on Windows, a desktop entry on Linux. It installs the panel into
MuseScore, registers a per-user login item so the engine starts with the
computer, and starts it immediately.

Login items are user-scoped and reversible: a LaunchAgent on macOS, a
Startup-folder VBScript on Windows, an autostart desktop entry on Linux.
Nothing is written outside the home folder and nothing needs administrator
rights.

The panel discovers the engine from `~/.motif/config.json`, so no address or
key is ever shown to the musician, and it retries quietly while the engine
comes up rather than telling anyone to start something.

## Security

- The server binds `127.0.0.1` only.
- Requests need a token from `~/.motif/config.json` (mode 0600), which the
  panel reads for itself.
- Any request carrying an `Origin` header is rejected, so a web page in a
  browser cannot reach the engine even if it guesses the port.
- Request bodies are capped; malformed JSON and oversized scores are refused
  rather than parsed.
