"""The MSN reference.

MSN (Motif Score Notation) is the plain-text notation Motif uses to write
music down outside a score: test fixtures, hand-written examples, and the
last piece of each conversation. Kept beside the parser so the two cannot
drift apart: every construct described here is one ``msn.py`` reads, and the
examples are parsed in the test suite.
"""
from __future__ import annotations

SPEC = r"""
# MSN — Motif Score Notation

MSN is plain text, one bar at a time, with no hidden state: every note
states its own pitch and its own duration.

## Header (only when writing a whole piece)

    title: Nocturne in C-sharp minor
    key: C# minor
    time: 4/4
    tempo: 54 "Lento con gran espressione"
    part: Pno piano

- `key:` e.g. `C# minor`, `Eb major`, `D dorian`. It sets the key signature only.
- `time:` e.g. `4/4`, `3/4`, `6/8`, `2/2`, `5/4`.
- `tempo:` beats per minute of the notated beat — the quarter note in 2/4,
  3/4, 4/4; the dotted quarter in 6/8, 9/8, 12/8; the half note in 2/2 —
  then an optional quoted tempo marking.
- `part: <id> <instrument> ["Name"]` declares each part. Ids are short
  (Pno, Vn1, Vn2, Vla, Vc, Fl, Cl, Hn). With no part lines, the piece is for
  solo piano.

## Bars

Each bar starts with `m<number>` on its own line, then one line per voice:

    m12
      RH: E5:q D#5:e E5:e G#5:h
      LH: C#3:e G#3:e E4:e G#3:e A2:e E3:e C#4:e E3:e

- Keyboard parts (piano, harpsichord, organ, celesta, harp) have staves `RH`
  and `LH` (organ also `Ped`). A second independent voice on a staff is
  `RH2` / `LH2` (up to RH4/LH4). In a piece with two keyboard parts, prefix
  the part id: `Pno.RH`.
- Every other part has one line, labelled with its id: `Vn1: ...`. Double
  stops and divisi are chords.
- Omit RH2/LH2 in bars where there is no second voice. Write `R` for a
  whole-bar rest (the only item on that line). Do not omit RH or LH.
- Bars are numbered consecutively. A pickup (anacrusis) is `m0` and is
  shorter than a full bar; the next bar is `m1`.
- Bar attributes go after the number, only when something changes:
  `m17 key="E major"`, `m25 time=3/4`, `m33 tempo=72 "Più mosso"`,
  `m33 tempo="Tempo I"`, `mark="B"` (rehearsal letter), `text="con fuoco"`,
  `clef.LH=treble`, `barline=double`, `barline=final`, `repeat=start`,
  `repeat=end`, `ending=1`.

## Notes, chords, rests

    C#4:q      pitch then ':' then duration. Middle C is C4. B3 is just below it.
    Bb2:h.     dotted half            F##5:e    double sharp
    Ebb4:s     double flat            [C3 G3 E4]:w   chord (any order)
    r:q        rest                   R          whole-bar rest
    s:h        invisible rest — use in RH2/LH2 to hold the voice's place

Durations: `w` whole, `h` half, `q` quarter, `e` eighth, `s` sixteenth,
`t` 32nd, `x` 64th. Dots follow directly: `q.` `e..`.

**Accidentals are always written in full on every note.** The key signature
never supplies them: in D major every F sharp is written `F#`. Spell notes
as a musician would in context — the leading tone of G# minor is `F##`, not
`G`; a flat sixth in C is `Ab`, not `G#`.

**Every voice line in a bar must add up exactly to the bar**: four quarter
notes' worth in 4/4, three in 3/4, three eighths per dotted-quarter beat in
6/8. Count every bar. Tuplets count at their real length.

## Ties, slurs, marks

    G4:h~ G4:e ...        ~ ties into the next note of the same pitch in this
                          voice, across the bar line if needed
    [E4~ G4 C5~]:h        tie only some notes of a chord
    (C5:e D5:e E5:q)      slur: '(' before the first note, ')' after the last;
                          may span bars; may nest one level
    C5:q+stacc            marks follow '+', several allowed: E5:e+stacc+accent

Marks: `stacc` `stacciss` `accent` `marc` `ten` `port` `fermata` `tr` (trill)
`mord` `prall` (upper mordent) `turn` `invturn` `arp` (roll the chord) `trem`
(tremolo strokes: `trem1` `trem2` `trem3`) `upbow` `downbow` `harm` `pizz`
`arco` `f1`–`f5` (fingering) and dynamic accents `+sf` `+sfz` `+fz`.

## Tuplets and grace notes

    {3 C5:e D5:e E5:e}         three eighths in the time of two
    {3 C5:q D5:q E5:q}         three quarters in the time of two (a half note)
    {5 C5:s D5:s E5:s F5:s G5:s}   five sixteenths in the time of four
    {6 ...}  {7 ...}           six/seven in the time of four
    {2 C5:e D5:e}              duplet in compound time (two in the time of three)
    {7:8 ...}                  explicit ratio when it isn't the usual one
    {acc D5:s} C5:q            acciaccatura (slashed grace note) before C5
    {app D5:e} C5:q            appoggiatura (unslashed)
    {g E5:t D5:t} C5:q         several grace notes

Write the notes inside a tuplet at their written value; the ratio does the
rest. Grace notes take no time in the bar.

## Dynamics, hairpins, pedal, words

Directions start with `!` and apply at the point where they stand:

    !pp !p !mp !mf !f !ff !fff !sfz !fp      dynamics
    !cresc ... !end      crescendo hairpin (<) from here to !end
    !dim ... !end        diminuendo hairpin (>)
    !ped                 press the sustain pedal (again = change pedal)
    !pedup               release it
    "dolce"              expression text at this point; ^"rit." forces above,
                         _"sotto voce" below. rit., rall., accel., a tempo,
                         stringendo etc. are heard as well as printed.

Put dynamics, hairpins and pedalling in the voice line where they belong: a
piano's dynamics usually in RH (they print between the staves and govern
both hands), pedal marks in LH.

## Lyrics and harmony

    C5:q@"Ah"  D5:q@"lo-" E5:h@"ve"      a syllable ending in '-' continues
    H: i:h V7:q V7/iv:q                  optional: the harmony you intend,
                                         with durations; not printed, but it
                                         keeps you honest and helps review

## A complete example

    title: Minuet
    key: G major
    time: 3/4
    tempo: 120 "Allegretto"

    m1
      RH: !mf (D5:q G4:e A4:e B4:e C5:e)
      LH: [G3 B3]:h A3:q
      H: I:h.
    m2
      RH: D5:q+stacc G4:q+stacc G4:q+stacc
      LH: B3:h.
    m3
      RH: !cresc (E5:q C5:e D5:e E5:e F#5:e)
      LH: C4:h.
      H: IV:h.
    m4
      RH: G5:q !end G4:q+stacc G4:q+stacc
      LH: B3:h.
"""
