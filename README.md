<div align="center">

<img src="plugin/MotifAI/assets/wordmark.png" width="380" alt="Motif.AI">

**Your AI composing partner, inside MuseScore.**

Describe a piece in your own words. Motif writes it — fully engraved, with
phrasing, pedalling, dynamics and rubato — and opens it in MuseScore.

</div>

---

```
"Create a simple melody for me to play."

"Make a full Rachmaninoff style piano concerto using a dark E♭ minor melody."

"Write 24 bars in C minor at 92 bpm: begin quietly with a singing melody,
then build to a thunderous climax with bass octaves, finally bring back the
opening theme and fade away."
```

Both work. The first gives you sixteen playable bars almost instantly. The
second gives you a 120-bar concerto for piano and orchestra, with solo and
tutti trading, a cadenza and a coda.

Ordered directions in the third example control the section map, rather than
only the overall mood. They can specify a relative or named key, left-hand
texture, dynamic, climax and return. An explicitly requested bar count and BPM
are treated as constraints. The result is a generated draft for you to judge
and edit: a composer's style profile cannot reproduce that composer's genius
or promise concert-quality music from every request.

## Getting started

1. Open the **Install Motif** folder and double-click the item for your
   computer.
2. Choose **Install**. It takes a few seconds.
3. Open MuseScore and choose **Motif.AI** from the Plugins menu.

That's all of it. Motif starts with your computer from then on, so the panel is
ready whenever MuseScore is. Nothing is typed, and nothing leaves your machine.

To remove it, open Setup again and choose **Remove**.

## What you can ask for

Anything you would ask a composer sitting next to you:

- *"Compose a romantic piano piece in the style of Chopin"*
- *"Write a short film score for a mysterious forest scene"*
- *"A Bach fugue in D minor at 92 bpm"*
- *"Make the middle section darker and slower"*
- *"Continue this piece in a more dramatic way"* — it reads your open score
- *"Continue in the same style"* — matches the composer, key, tempo and
  instruments already on the page, exactly, not a guess
- *"Continue this for a string quartet"* — carries the piece forward with
  different or larger forces, on request
- *"Add a left hand accompaniment"* — keeps your melody, writes underneath it
- *"Transpose it to F♯ minor"*
- *"What key is this in?"*

There is no menu for the composer or the instrumentation — both are read
straight out of what you type, every time, so nothing you could ask for is
ever missing from a list.

**23 composers** — Bach, Handel, Scarlatti, Vivaldi, Mozart, Haydn, Clementi,
Beethoven, Schubert, Chopin, Liszt, Brahms, Mendelssohn, Grieg, Tchaikovsky,
Rachmaninov, Scriabin, Debussy, Ravel, Satie, and contemporary minimal and
cinematic idioms.

**30 forms** — nocturne, sonata, fugue, invention, rondo, variations, waltz,
mazurka, ballade, prelude, étude, intermezzo, concerto and more.

**13 ensembles** — solo piano through full orchestra, string quartet, piano
trio, concerto, duo sonatas, organ, harpsichord, guitar.

## The trained composer

Motif has two brains, and the second one is optional.

The **symbolic engine** knows music theory — spelled pitch, functional
harmony, voice leading, per-composer idiom libraries. It always works, needs
nothing installed, and never writes an unplayable bar. But it knows the
rules without having any taste.

The **trained model** is a transformer taught on real public-domain scores.
It has heard how those rules are actually used, which is the part no amount
of rule-writing supplies. When a checkpoint is present the model writes the
notes and the engine does what a model is bad at and an engraver must be
right about: keeping every bar full, every chord inside one hand, every note
inside the instrument, and the page properly beamed and marked.

Training it costs about $26 of GPU time on Modal and takes an afternoon —
see **[docs/TRAINING.md](docs/TRAINING.md)**. Drop the result into your
Motif folder as `model.pt` and it becomes the composer. Without it, the
symbolic engine carries on exactly as before.

## Why it sounds played rather than printed

The performance layer applies to both brains. It is a music-theory system —
spelled pitch, functional harmony, voice leading, per-composer idiom
libraries — with a performance layer on top of it.

That performance layer is what makes the difference:

| | |
|---|---|
| **The tempo breathes** | Phrases ease into their cadences and press through developments; the piece slows at its close. How freely depends on the composer — Bach holds his pulse, Chopin does not. |
| **The volume moves** | Every note is shaped by where it sits in the phrase, how high it is, and where the beat falls — not stepped between eight printed marks. The melody is voiced above the accompaniment, as a pianist balances the hands. |
| **The rhythm varies** | Accompaniments rest, hold, halve their motion, lean into a dotted lilt or turn over in triplets. Mazurkas lean on the second beat; Brahms writes hemiolas. |
| **The harmony travels** | Sections modulate to real key relationships, coloured with applied dominants, borrowed chords and Neapolitans at rates drawn from each composer. |
| **The melody is actually about something** | The whole line is spun continuously from one small cell — inverted, fragmented, sequenced, taken further — the way a real piece develops a theme, rather than a fresh, unrelated line generated bar by bar. |
| **It engraves like a real page** | Eighth notes and shorter are beamed in proper metrical groups, not printed as isolated flagged notes. |

## Privacy

Everything happens on your computer. Motif listens only to MuseScore, on your
own machine, and your music is never sent anywhere. Asking Motif to continue,
develop or change a piece you already have open writes the result back into
that same file — it never leaves a second copy somewhere you'd have to go
find.

## For developers

Architecture, the engine's design decisions and the optional trained model are
documented in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** and
**[docs/TRAINING.md](docs/TRAINING.md)**. The engine has no required
dependencies and its test suite runs with `pytest` from `engine/`.

## Licence

MIT. The music you make with Motif is yours.
