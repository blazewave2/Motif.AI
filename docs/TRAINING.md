# Training Motif's neural model on a $30 budget

Motif works fully without a trained model. This document covers the optional
neural component, what it adds, and how to train one on Modal for roughly the
price of a couple of coffees.

## What the model actually does

It supplies **the seed motif** — the short melodic cell every section of a
piece is built from. That is where a learned musical voice matters most and
where it can do least damage: harmony, form, voice leading and engraving stay
with the theory engine, so a rough sample cannot derail a piece's structure.

Sampling is grammar-constrained: after a `PITCH` token only a `DUR` is legal,
after `DUR` only a `VEL`, and so on. A small model will otherwise emit
syntactically impossible sequences, and masking them costs nothing.

## The honest picture on data

The music of every composer Motif imitates is out of copyright. **Freely
licensed symbolic encodings of it are not evenly distributed**, and this is
the real constraint:

| Well covered | Thin |
|---|---|
| Bach, Mozart, Haydn, Beethoven, Scarlatti, Chopin, Joplin, Schubert (Lieder) | **Liszt, Rachmaninov, Scriabin, Debussy, Ravel** |

The Humdrum/KernScores collections are excellent and genuinely public domain,
but they are centred on the Baroque and Classical repertoire. For the
late-Romantic composers you most likely want, the best free source is **PDMX**
(~250k CC0 MusicXML scores from MuseScore.com), which is large enough to need
its own download step and is therefore opt-in rather than default.

**What this means in practice:** Motif's Rachmaninoff and Liszt idioms come
primarily from the encoded style profiles — the textures, harmonic vocabulary,
registers and hand spans in `engine/motif/compose/styles.py` — not from
training data. The neural model sharpens the melodic voice for the composers
the corpus covers well. Do not expect a checkpoint trained only on the default
corpus to have learned Scriabin.

### Default sources

All cloned by `--step corpus`. Every one was reachability-checked.

| Source | Content | Licence |
|---|---|---|
| `craigsapp/bach-370-chorales` | 370 four-part chorales | Public domain |
| `craigsapp/beethoven-piano-sonatas` | The 32 sonatas | Public domain |
| `craigsapp/beethoven-string-quartets` | The quartets | Public domain |
| `craigsapp/mozart-piano-sonatas` | The sonatas | Public domain |
| `craigsapp/haydn-piano-sonatas` | The sonatas | Public domain |
| `craigsapp/scarlatti-keyboard-sonatas` | ~550 sonatas | Public domain |
| `craigsapp/chopin-mazurkas`, `-preludes` | Mazurkas, Op. 28 | Public domain |
| `craigsapp/joplin`, `craigsapp/hummel-preludes` | Rags, preludes | Public domain |
| `OpenScore/Lieder` | ~1300 songs | CC0 |
| `OpenScore/StringQuartets` | Quartets | CC0 |
| `MutopiaProject` | Mixed repertoire | Public domain / CC |

`pl-wnifc/humdrum-chopin-first-editions` (near-complete Chopin) is **excluded
by default** because it is non-commercially licensed. Add it with
`--include-nc` only if that suits your use.

### Adding PDMX or another corpus

Download it however its publisher intends, then:

```bash
modal run training/modal_app.py --step prepare --extra-dir /data/raw/pdmx
```

Any `.krn`, `.musicxml`, `.mxl`, `.mid` or `.abc` file under that directory is
picked up. With PDMX folded in, switch to `--preset base` (86M parameters);
without it, `small` (25M) is the honest choice for the data volume.

## Representation

A bar-relative REMI-style vocabulary of **424 tokens**:

```
<bos> STYLE_chopin KEY_-6_min TS_4_4 TEMPO_6
BAR POS_0 TRACK_0 PITCH_68 DUR_12 VEL_5 PITCH_71 DUR_12 VEL_5 …
```

Positions are quantised to a twelfth of a quarter note, which represents both
duple subdivisions and triplets exactly. Conditioning tokens for style, key,
metre and tempo mean the model is steered by the same plan the symbolic engine
follows.

**Augmentation** is applied at the token level: shifting every `PITCH` and the
`KEY` token gives twelve musically valid transpositions of each piece. The
default corpus yields roughly 15M raw tokens, which becomes ~150M augmented —
the difference between a model that overfits in an hour and one worth training.

## Running it

```bash
pip install modal && modal setup

modal run training/modal_app.py --step corpus       # ~10 min, CPU, cents
modal run training/modal_app.py --step prepare      # ~1–2 h, CPU, ~$1
modal run training/modal_app.py --step train --budget 22
modal run training/modal_app.py --step sample --style chopin --key "Eb minor"
modal run training/modal_app.py --step download
```

Then set `model_path` in `~/.motif/config.json` to the checkpoint, or start
the engine with `MOTIF_MODEL` pointing at it. Motif picks it up on its next
start; the panel keeps working exactly as before if it fails to load.

### Budget

The cap is enforced in the training loop. Each iteration estimates spend as
elapsed GPU seconds × the hourly rate; when it approaches the cap the run
writes a checkpoint and stops. Resuming carries the already-spent amount
forward, so `--budget 22` means $22 total across restarts, not per run.

| GPU | ~$/hour | Hours for $22 |
|---|---|---|
| T4 | 0.59 | 37 |
| L4 | 0.80 | 27 |
| A10G *(default)* | 1.10 | 20 |
| A100-40GB | 2.10 | 10 |

Rates are approximate and used only for the guard. Modal's published pricing
is authoritative — pass `--gpu-hourly` if it has moved.

A realistic $30 plan: ~$1 preparing data, ~$20 training, ~$1 sampling, leaving
headroom for a restart. That buys several epochs over the augmented corpus for
the `small` preset, which is where the loss curve flattens anyway.

### Presets

| Preset | Layers | Width | Params | Use when |
|---|---|---|---|---|
| `small` | 8 | 512 | ~25M | Default corpus (~150M tokens) |
| `base` | 12 | 768 | ~86M | With PDMX or similar (>400M tokens) |
| `large` | 16 | 1024 | ~200M | More data and budget than this doc assumes |

## Checking it worked

```bash
modal run training/modal_app.py --step sample --style chopin --key "Eb minor" --bars 16
```

Validation loss under ~1.2 nats/token on this vocabulary generally means the
model has learned the grammar and something of the idiom. Below ~0.8 on a
corpus this size, suspect memorisation and check `--step status` for how many
distinct pieces actually made it in.
