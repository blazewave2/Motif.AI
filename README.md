<div align="center">

<img src="plugin/MotifAI/assets/wordmark.png" width="380" alt="Motif.AI">

**Your AI composing partner, inside MuseScore.**

Describe a piece in your own words. Motif writes it — fully engraved, with
phrasing, pedalling, dynamics and rubato — and opens it in MuseScore.

</div>

---

```
"A Rachmaninoff prelude in C♯ minor."

"A tender Chopin nocturne in E♭, with an agitated middle section."

"A string quartet in D minor, in the style of Tchaikovsky."
```

Each one comes back as a finished piece: a theme that is stated, answered
and developed, a contrasting middle section, a return and a coda — harmonised
in the composer's own idiom, laid out for the hands the way that composer
wrote for the piano, and marked with dynamics, phrasing, pedalling and tempo.
Motif composes it on your computer, with its own composer: no online service,
no language model.

## Getting started

1. Open the **Install Motif** folder and double-click the item for your
   computer.
2. Choose **Install**. It takes a few seconds.
3. Open MuseScore and choose **Motif.AI** from the Plugins menu. In
   MuseScore 4 it is under **Composing/arranging tools**; Setup switches it on
   for you, and if it is ever missing there, turn it on under
   **Home → Plugins**.

That's all of it. Motif starts with your computer from then on, so the panel is
ready whenever MuseScore is. Nothing is typed, and nothing leaves your machine.

To remove it, open Setup again and choose **Remove**.

## What you can ask for

Anything you would ask a composer sitting next to you:

- *"Compose a romantic piano piece in the style of Chopin"*
- *"Write a short film score for a mysterious forest scene"*
- *"A Bach fugue in D minor at 92 bpm"*
- *"Six variations on a theme in the style of Mozart"*
- *"An 8-bar theme in the style of Schubert, no accompaniment"* — or a motif,
  an introduction, a cadenza, a chord progression: just the part you need
- *"Make it darker and slower"* — writes the same piece again in that mood
- *"Continue this piece in a more dramatic way"* — it reads your open score
- *"Continue in the same style"* — matches the composer, key, tempo and
  instruments already on the page, exactly, not a guess
- *"Continue this for a string quartet"* — carries the piece forward with
  different or larger forces, on request
- *"Add a left hand accompaniment"* — keeps your melody, writes underneath it
- *"Arrange this for string quartet"* — keeps your tune, scores it for the
  instruments you name
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

## The composer

Motif composes the way a composer does, from the whole piece down to the
note ([how it works](docs/COMPOSER.md)):

| | |
|---|---|
| **A form, not a stream** | Every piece is laid out before a note is written: an opening, a theme group, a middle section in a related key with its own theme, a passage leading home, the return — at its climax, or ornamented — and a coda. Sonatas, waltzes, mazurkas, minuets, inventions, concertos and sets of variations have their own architectures. |
| **Themes with a shape** | A theme starts as a two-bar idea chosen from many candidates for its character and for the harmony it implies. Phrases state it, answer it at another level, take it in sequence and break it into fragments on the way to the cadence — so the music is always about something. |
| **Harmony in the composer's own language** | Chords are planned by function — tonic, answer, predominant, cadence — and drawn from each composer's vocabulary: Mozart's cadential six-fours and augmented sixths, Chopin's Neapolitans and applied diminished sevenths, Rachmaninoff's added-sixth minor chords, half-diminished supertonics, line clichés and pedal points, Debussy's planing. Where the tune needs it, the chords under it are recoloured. |
| **Melody searched note by note** | Every note is chosen by a search that weighs chord tones and resolutions, leaps and their recovery, one planned climax per phrase, the idea's own contour, the cadence — and what real melodies do, learned from 1,469 public-domain scores. Several versions of every phrase are written and the best kept. |
| **Variations that vary** | A theme and variations keeps the theme's phrases and chords and gives it a new dress each time: running figuration found note by note, flowing triplets, a running accompaniment, the minore, the tune in the left hand, a slow ornamented variation, a finale and a coda — each named, with its own tempo. |
| **Written for the hands** | The accompaniment is laid out in the idiom of the passage — the nocturne left hand, Rachmaninoff's tolling bells, sweeping arpeggios, the waltz bass, the Alberti bass, a walking bass, a two-part invention — with every chord inside one hand's reach and under the melody. |
| **Played, not printed** | Dynamics follow the energy of each phrase, hairpins swell into its high point, slurs follow its breathing, the pedal changes with the harmony; the music holds back before new sections, broadens into the climax, moves on in the middle (*Più mosso*) and returns (*Tempo I*); returns are ornamented; the last chord is held. |

**25 composers** with profiles of their own — Bach, Handel, Scarlatti,
Vivaldi, Mozart, Haydn, Clementi, Beethoven, Schubert, Mendelssohn, Chopin,
Schumann, Liszt, Brahms, Grieg, Tchaikovsky, Rachmaninoff, Scriabin, Debussy,
Ravel, Satie, Einaudi and film idioms — and any other composer by kinship
(Medtner writes like Rachmaninoff, Field like Chopin, Fauré like the
Romantics, Hisaishi like film), with the piece credited to the composer you
named.

**Any ensemble** — solo piano; voice, violin or cello with piano; piano trio;
string quartet; string orchestra; orchestra; organ; harpsichord; guitar.

**Care.** The panel's *Care* setting chooses how many ideas the composer
weighs at every step — from *Sketch* to *Maximum*. Quality always comes
first: every setting goes through every stage.

## Privacy

Everything happens on your computer. Motif listens only to MuseScore, on your
own machine, and your music is never sent anywhere. Asking Motif to continue,
develop or change a piece you already have open writes the result back into
that same file — it never leaves a second copy somewhere you'd have to go
find.

## For developers

The composer is described in **[docs/COMPOSER.md](docs/COMPOSER.md)**, the
engine and plugin in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**, and how
the melodic model is learned from public-domain scores in
**[docs/TRAINING.md](docs/TRAINING.md)**. The engine has no required
dependencies and its test suite runs with `pytest` from `engine/`.

## Licence

MIT. The music you make with Motif is yours.
