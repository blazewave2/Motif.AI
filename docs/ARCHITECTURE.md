# Architecture

```
  MuseScore                                Local machine only
 ┌───────────────────────┐                ┌──────────────────────────────────┐
 │  Motif.AI panel (QML) │  HTTP/JSON     │  Motif engine (Python, stdlib)   │
 │  ─────────────────────│───────────────▶│  ──────────────────────────────  │
 │  prompt, conversation,│  127.0.0.1     │  agent → composer → notation     │
 │  progress, Stop, Care │◀───────────────│  MusicXML + MIDI                 │
 └───────────────────────┘   MusicXML     └──────────────────────────────────┘
            │
            ├── MuseScore 3: readScore() opens it (or reloads the score it changed)
            └── MuseScore 4: the engine opens it in a new MuseScore window
```

Nothing leaves the computer. The composer is Motif's own — rules of harmony,
voice leading, form and idiom, plus a small statistical model of melody
learned from public-domain scores — and needs no network, no language model
and no packages beyond Python itself.

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

### `composer/` — Motif's composer

| Module | Responsibility |
|---|---|
| `profiles.py` | One profile per composer: harmonic and melodic idiom, textures per kind of passage, pedalling, dynamics, rubato, ornament, tempo words |
| `form.py` | The piece as phrases: sections, keys, cadences, energy, texture, returns; genre and metre from the request |
| `harmony.py` | Functional phrase harmony in each style's vocabulary; sequences that move with the tune; revision of chords that fight the melody |
| `melody.py` | Theme invention (rhythm, contour, implied harmony) and the beam search that writes every phrase, with repeats and sequences as imitation units |
| `style_model.py` | The learned statistics of real melodies (`data/melody.json`) as search costs |
| `texture.py` | Accompaniment idioms, voice-led and inside the hand |
| `arrange.py` | The same material scored for any ensemble |
| `notation.py` | Writing it all down as Motif Score Notation |
| `core.py` | The composer itself: form → themes → phrases → texture → performance marks, with progress and Stop |

How it composes is described in **[COMPOSER.md](COMPOSER.md)**.

### `notation/`

Motif Score Notation (MSN) is a plain-text score format with no hidden
state: every note carries its own pitch and duration, every bar is numbered,
every voice is on its own labelled line. `msn.py` parses it and reports every
problem with its bar and voice; `validate.py` checks bar lengths, hand spans
and instrument ranges; `to_score.py` turns it into the engine's `Score`,
including the performance layer in `perform.py` (per-note velocities shaped
by phrase, register and beat; tempo marks that rit. and accel. are heard);
`from_score.py` goes the other way.

### `engrave/`

`musicxml.py` writes MusicXML 3.1 that validates against the schema and opens
cleanly in MuseScore 3 and 4; `musicxml_reader.py` reads a score back from the
panel; `beaming.py` groups eighths and shorter by the metre; `midi.py` writes
the MIDI file.

### `agent/`

`prompt_parser.py` is the deterministic understanding layer — style, key,
metre, tempo, form, mood, scope and ensemble from free text, noting which of
them the musician actually named. `agent.py` routes six intents: create,
continue, develop, harmonize, edit, analyze. New pieces, continuations and
developments are written by the composer; the reply describing the piece is
built from what the composer decided (`voice.py`). `session.py` keeps each
conversation.

Neither the composer nor the instrumentation is ever a stored setting — both
come from the prompt on every request. "Continue in the same style" is
resolved two ways, in order: the exact style, ensemble and instrumentation
Motif itself recorded when it wrote the score (see "Provenance survives the
round trip" below) when that survives, and a note-based heuristic (chromaticism,
polyphony, ornament rate, register, tempo) when it does not.

### `server/`

A stdlib HTTP server on 127.0.0.1. Composing runs as a background job
(`jobs.py`): the panel starts it, polls its progress (stage, label, fraction)
and can stop it at any point — the composer checks for Stop at every stage
and nothing is written if it is stopped. The *Care* setting
(`composer_quality`: sketch, balanced, best, maximum) chooses how many ideas
the composer weighs.

### `compose/` and `model/` — the earlier engine

The engine Motif used before its own composer still supplies the vocabulary
the request parser reads, writes piano concertos, and harmonises a melody the
musician has written. `model/` loads an optional transformer checkpoint for
it. Neither is used for anything the new composer writes.

## Design decisions worth knowing

**The engine has no required dependencies.** A musician installing a MuseScore
plugin should not have to create a virtualenv. Everything in `engine/` runs on
the standard library, including the HTTP server and the composer.

**Bars are guaranteed complete.** The composer writes its notes as MSN, which
is validated bar by bar before anything is engraved; a bar of the wrong
length, a chord no hand can span or a note outside an instrument is reported
as an error, and the test suite composes every style and ensemble and asserts
there are none.

**Ranges are clamped last.** Octave doubling and register shifts compound, so a
final pass folds any note outside the instrument's range back into it.

**Beaming is computed, never trusted from the source.** `engrave/beaming.py`
groups eighth notes and shorter within each metrical beat, breaking at rests
and beat boundaries and hooking a lone shorter note against a longer
neighbour. It is re-run over an entire score after a continuation merges in
new material, because `musicxml_reader.py` does not restore `<beam>` from a
reopened file — recomputing is cheap and keeps both halves looking like one
piece.

**A continuation edits the file you already have open.** When a request
changes a piece that is already open — continuing, developing, harmonising,
editing — the server writes the result back to that score's own path rather
than a new file under `~/.motif/scores`; the panel is told this happened
(`same_file` in the `/compose` response) and reloads that same path
regardless of the "open automatically" preference, since leaving a stale
version on screen while the file underneath it changed risks the next save
overwriting Motif's work. A genuinely new, unrelated piece — even while a
score happens to be open — always gets its own file.

**MuseScore 4 opens the score through the engine.** MuseScore 4's plugin
API has no working `readScore()`, so there the panel posts the finished
file's path to `/open` together with the path of the program it is running
in (`Qt.application.arguments[0]`). `server/opener.py` starts that MuseScore
with the file, which opens it in a window of its own. The route only opens
files in Motif's own scores folder, and only with a program named as a
MuseScore. An AppImage's inner program cannot start outside its image, so
the image itself is started (read from the running MuseScore's
`$APPIMAGE`), and the new window borrows the running MuseScore's display
settings in case the engine was started outside the desktop session. A
MuseScore that fails to start within a moment hands the file to the
system's own opener. Setup also switches the panel on in MuseScore 4.4 and
later (its `extensions/config.json`), which would otherwise list it
switched off.

**Seeds are reproducible.** The same prompt and seed produce a byte-identical
score; a different seed produces different music. "Try again" in the panel is
simply a new seed.

**Provenance survives the round trip.** `musicxml.py` writes the composer,
form, ensemble, seed and character Motif used as plain
`<miscellaneous-field>` entries under `<identification>` — standard MusicXML
that any reader, MuseScore included, is free to ignore. `musicxml_reader.py`
reads them back into `Score.metadata`, and `analysis.py` prefers them outright
over its own note-based guess. This is what makes "continue in the same
style" exact rather than approximate, for as long as the metadata survives
whatever the score passed through; the heuristic in `detect_style` is the
fallback for everything else — a score never touched by Motif, or one edited
enough that guessing again is worth it.

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
