# How Motif composes

Motif's composer is its own: it runs entirely on your computer, uses no
language model and no online service, and needs nothing installed beyond
Python. It lives in `engine/motif/composer/`. This page explains how it
thinks, because it thinks the way a composer does — from the shape of the
whole piece down to the note — and every stage can be read, tested and
improved on its own.

```
request ─▶ profile + genre + key + metre + tempo
             │
             ▼
          form ─────────────── intro · A (theme) · B (contrast) · A′ · coda
             │                  every phrase: bars, key, cadence, energy, texture
             ▼
          themes ───────────── the main idea and a contrasting one, each the best
             │                  of many candidates, with the harmony it implies
             ▼
   ┌──── for each phrase ────────────────────────────────────────────┐
   │  harmony  ── functional plan (tonic · answer · predominant ·     │
   │              cadence) in the composer's own chord vocabulary     │
   │  melody   ── beam search over every note, several takes, best    │
   │              kept; repeats and sequences move the idea as a whole│
   │  revision ── chords that fight the tune are recoloured           │
   └──────────────────────────────────────────────────────────────────┘
             │
             ▼
          texture ──────────── the left hand (and inner voices) in the idiom
             │                  of the composer, kept inside the hand
             ▼
          performance ──────── dynamics, hairpins, slurs, pedalling, rubato,
             │                  tempo changes, ornaments, the final chord
             ▼
          notation ─────────── Motif Score Notation → validated → MusicXML
```

## Profiles (`profiles.py`)

Each composer is a profile: a harmonic idiom, a melodic style, the piano
textures used for each kind of passage (theme, middle section, climax,
return, coda), pedalling, dynamic range, rubato, ornamentation, whether the
climax doubles the tune in octaves, how often the accompaniment starts alone,
the language of its tempo words and the character it leans to. Twenty-five
composers have their own profile; any other composer maps to the nearest one
(Medtner to Rachmaninoff, Fauré to the Romantic profile, Field to Chopin).

## Form (`form.py`)

A genre is laid out as phrases of four and eight bars. A prelude, nocturne,
romance or élégie is ternary: a theme group (a period or sentence pair), a
middle section in a related key with its own theme and more motion, a short
passage leading home, the theme returning — at its climax in octaves over
tolling bells for Rachmaninoff and Liszt, ornamented for Chopin — and a coda
that remembers the opening. Waltzes and mazurkas are chains of sixteen-bar
strains; sonatas have two key areas, a development and a recapitulation;
minuets have a trio; inventions state their subject and answer it. The genre
and metre come from the request when it names them.

## Themes (`melody.py`)

A theme starts as a two-bar idea: a rhythm drawn from the style's rhythm
cells and a contour in scale steps. Many candidates are invented and scored
for character — a long note and a short one, a leap filled in by steps the
other way, one high point that is held rather than passed through, a range of
about a fifth, no trilling back and forth — for the mood asked for (drama
rises by arpeggio in dotted rhythm, calm moves by step, play skips in short
notes), and for the harmony they imply: each candidate is tried starting on
the tonic, third and fifth, with its second bar over the tonic, subdominant
or dominant, and kept only if its long and accented notes are chord tones.
At higher care the best few are then *auditioned*: each is written out as
the piece's opening phrase, and the theme whose phrase turns out best is
the one the piece is built on. The middle section gets its own theme,
chosen to differ in rhythm and gesture.

## Phrases

A phrase is a grammar of bar roles. A sentence states its idea (bars 1–2),
repeats it at another level (3–4), takes the first bar in sequence (5),
breaks it into half-bar fragments (6), runs freely (7) and cadences (8). A
consequent restates its antecedent's opening over the same chords and closes
differently. A coda recalls the opening bars and settles.

**Harmony** (`harmony.py`) is planned per phrase in functional stages — the
tonic, the answer to the idea, the predominant, the cadence arrival on the
last downbeat — with each stage filled from the style's own vocabulary: the
cadential six-four and augmented sixths of Mozart, the Neapolitans and
applied diminished sevenths of Chopin, the added-sixth minor chords,
half-diminished supertonics, descending line clichés and pedal points of
Rachmaninoff, the modal planing of Debussy. When a sentence repeats its idea
a number of scale steps away, the chords move the same distance, so a
sequence is a real sequence. Applied chords must reach their targets and
augmented sixths must open onto the dominant. Many candidate progressions are
scored for bass motion, variety and cadence, and the best is kept.

**Melody** is written note by note by a beam search against a musical cost:
chord tones on strong beats unless the note is an appoggiatura that resolves
by step; passing and neighbour notes approached and left by step; long
dissonances avoided; leaps recovered in the other direction; a contour that
climbs to one planned high point and falls to the cadence; the idea's own
steps where it is stated; the right degree at every cadence; no parallel
fifths or octaves against the bass. Repeats, sequences and fragments are
*imitation units*: each hypothesis in the beam chooses how far to move the
idea and is then held to that transposition note by note, so the idea is
recognisably the same wherever it appears. The search keeps a beam of the
best partial lines and runs several takes; the take that is best by the
search's own cost and by a whole-phrase judgement (stepwise motion, one
climax, rhythmic variety, no bar merely copying the last) is kept.

**What real melodies do** (`style_model.py`, `data/melody.json`) is added to
those rules as a learned cost: statistics of which interval follows which,
which scale degree follows which in major and minor, and which degrees fall
on beats, learned by `training/learn_style.py` from 1,469 public-domain
scores (the OpenScore Lieder and String Quartet corpora, both CC0). The rules
say what a line must do; the statistics say what lines usually do.

**Revision.** After the melody is written, any chord that fights it — a long
or accented melody note that is not in the chord and does not resolve like a
passing note — is recoloured (a seventh, an added sixth) or replaced by a
chord doing the same job, without touching the cadence or the phrase's
opening chord.

## Texture (`texture.py`)

The accompaniment is laid out chord by chord in the idiom of the passage:
the nocturne left hand spread over a tenth and more; Rachmaninoff's bells —
a deep octave tolling on the beat, answered by the chord in the tenor; wide
triplet and sixteenth-note arpeggios; the waltz bass; Mozart's Alberti bass
(in eighths at an Allegro, sixteenths when slower); repeated chords; a
walking bass; open pedalled sonorities; and, for inventions, the subject
answered in the left hand an octave lower while the right hand plays a
countersubject that is kept consonant with it. Every realiser voice-leads
from the chord before, keeps under the melody, and keeps each hand inside
its reach.

## The shape of the whole

The passage leading back to the theme sits on a dominant pedal and grows in
one long crescendo into the climax; in Romantic pieces the returning theme's
cadence is sometimes evaded — a deceptive cadence — and a short extension
finds its way home before the coda. At cadences a flowing left hand may come
to rest on a held chord so the phrase is heard to end. Some middle sections
move the tune into the left hand, *sotto voce*, under soft repeated chords.
Where the left hand leaves room, a lyrical phrase may gain a second, singing
voice in the right hand — one long note to a chord, moving by step, with
suspensions that fall to their resolutions.

## Performance

Dynamics follow each phrase's energy; hairpins swell into the phrase's high
point and away from it over a bar or two; slurs follow the breathing of the
line (a two-bar gesture in Classical music, a whole line in Romantic); at a
quick Classical tempo notes that leap or repeat are detached and the note
before a full close takes a trill; the pedal changes with the harmony.
Romantic pieces hold back before each new section, broaden into the climax,
move on in the middle section (*Più mosso*) and return to *Tempo I*. Returns
in Chopin and Field are ornamented with grace notes, turns and the
occasional sextuplet run; Debussy's are carried in parallel chords. The last
bar is a held, rolled chord under a fermata.

## Ensembles (`arrange.py`)

For anything other than solo piano, the same composed material is arranged:
the tune goes to the voice, violin, cello or first violins, composed in that
instrument's range; the inner parts are real voices led smoothly under the
tune and above the bass, held in calm music, on the beat as it moves, pulsing
when it presses; the bass sings its own line; in an orchestra the winds
double the strings as the music grows, and trumpets and timpani join only at
its height. A piano accompanying a soloist keeps its left hand and gains
chords in the right.

## Concertos

A piano concerto is a first movement in which every phrase knows who plays
it. In the Romantic concerto the piano opens alone with tolling chords; the
strings state the theme, violins and cellos an octave apart, while the piano
ripples beneath; the piano sings the second theme over quiet strings and the
orchestra takes it up; the development trades phrases; the theme returns at
the climax with the whole orchestra and the piano's massive chords; a
cadenza for the piano alone holds on the dominant; a coda brings everyone
home. A Classical concerto opens with the orchestra's ritornello.

## Working with the musician's own music

*Continue* reads the opening of the tune already on the page (`listen.py`)
and makes it the theme: the continuation develops it away from home, leads
back, restates it and closes, in the page's own key, metre and tempo.
*Develop* builds a new piece on it. *Harmonise* (`harmonize.py`) keeps the
tune note for note and chooses a chord for every half bar by dynamic
programming over the composer's vocabulary — fit to the tune, natural
motion from chord to chord, a pause on the dominant every fourth bar and a
close on the tonic — then lays out the accompaniment in the composer's
idiom.

## Notation (`notation.py`)

The composer writes Motif Score Notation, bar by bar, the way an engraver
would: values split to show the metre, ties across bar lines, triplets and
sextuplets grouped, hidden rests in secondary voices, markings where they
happen. The text is parsed and validated by `motif.notation` — every bar the
right length, every chord inside one hand, every note inside its instrument
— and turned into MusicXML and MIDI.

## Care

How many ideas the composer weighs is the *care* the musician chooses in the
panel: how many candidate themes, how many harmonic plans per phrase, how
wide the melody search and how many takes. *Sketch* is quick; *Maximum*
weighs the most. Quality always comes first: even Sketch goes through every
stage above.

## Testing

`engine/tests/test_composer.py` composes every style and ensemble and checks
the result is valid, complete and reproducible, that stopping works, and that
each stage does what it claims (sentences, sequences, consequents borrowing
their antecedent's harmony, the learned model's tendencies). The evaluation
script used during development renders pieces with MuseScore itself.
