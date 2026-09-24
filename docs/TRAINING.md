# Teaching the composer from real scores

Motif's composer (see [COMPOSER.md](COMPOSER.md)) writes by musical rules —
harmony, voice leading, phrase structure, the idioms of each composer — and
by what it has learned from real music: how melodies actually move. That
learned part is a small statistical model, shipped with Motif as
`engine/motif/composer/data/melody.json` (about 8 KB). The composer reads it
at start-up; nothing else is needed at run time.

## What it learns

For every score it reads, `training/learn_style.py` takes the tune (the
first part with a single staff — the voice of a song, the first violin of a
quartet), splits it into phrases at rests, finds its key, and counts:

* which interval follows which (in semitones, up to an octave either way),
  and which interval a phrase starts with;
* which scale degree follows which, separately in major and in minor;
* which scale degrees fall on beats;
* which note value follows which.

A singer repeats a note for each syllable of the words where an instrument
would simply hold it, so repeated notes in songs are merged before counting.
The counts are smoothed into log-probabilities. In the melody search each is
turned into a cost relative to the most likely choice in its context — the
most usual continuation costs nothing — and weighed against the composer's
own rules.

## Rebuilding it

You need a folder of MusicXML files whose names start with the collection
they came from (`lieder__…`, `quartets__…`). Then, from the project folder:

```
python training/learn_style.py path/to/musicxml
```

It reads every file (about three minutes for 1,500 scores on a laptop) and
writes `engine/motif/composer/data/melody.json`. `--only` chooses which
collections are learned from; `--out` writes somewhere else.

## Which scores may be used

Only scores whose licence allows any use, including commercial use, go into
the shipped model:

| Collection | Licence | Used |
|---|---|---|
| OpenScore Lieder (≈1,350 songs) | CC0 | yes |
| OpenScore String Quartets | CC0 | yes |
| DCML annotated corpora (Mozart, Beethoven, Chopin, Liszt, Rachmaninoff …) | CC BY-NC-SA | for evaluation only |
| Craig Sapp's Humdrum editions (Bach chorales, Mozart, Haydn, Scarlatti, Joplin …) | CC BY-NC-SA | for evaluation only |

The non-commercial collections are useful for checking the composer's output
against the real composers' statistics during development, but nothing
learned from them is shipped. The model file records which collections it
was learned from.

To turn the OpenScore MuseScore files into MusicXML, MuseScore itself does
the conversion: `mscore -o out.musicxml in.mscx` (or a batch job with
`mscore -j jobs.json`).

## The older transformer tooling

`training/modal_app.py`, `prepare.py`, `model.py` and `train_local.py` train
the token-level transformer used by earlier versions of Motif. The current
composer does not use it; the engine still loads a checkpoint at
`~/.motif/model.pt` only for the one kind of piece Motif's own composer does
not yet write (piano concertos).
