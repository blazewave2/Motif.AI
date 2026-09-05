# Training the composer

Motif ships with a symbolic engine that knows music theory. It knows the
rules; it does not have taste. A model trained on real scores has heard how
those rules are actually used, which is the part no amount of rule-writing
supplies.

This is how you train it. It costs about $26 of GPU time and takes a few
hours, most of which is unattended.

## What you need

* A [Modal](https://modal.com) account. New accounts include a monthly
  credit that covers this run.
* Python on your own machine, only to launch the job — the work happens on
  Modal's GPUs, not yours.

```
pip install modal
modal setup            # opens a browser once to link your account
```

## Run it

From the project folder:

```
modal run training/modal_app.py --step all --budget 26
```

That does four things in order, and each one can be re-run safely if you
lose your connection — they resume rather than restart:

1. **Downloads the scores.** Public-domain Humdrum and MusicXML editions:
   Bach chorales, Beethoven and Mozart sonatas, Scarlatti, Haydn, Chopin,
   Joplin, and the CC0 OpenScore collections. Nothing is scraped from a
   commercial catalogue.
2. **Tokenises them.** Every piece becomes a token stream, then is
   transposed into all twelve keys — which is exact, and turns a modest
   corpus into something a model can actually learn from.
3. **Trains.** The budget is enforced inside the training loop, not just
   written down: it checkpoints and stops before the spend crosses the cap,
   so an overnight job cannot quietly run past it. Progress prints as it
   goes.
4. **Samples**, so you can see what it learned before you download it.

Then bring the checkpoint down:

```
modal run training/modal_app.py --step download
```

## Install it

Put the downloaded `motif-small.pt` into the Motif folder in your home
directory, renamed to `model.pt`:

* macOS / Linux — `~/.motif/model.pt`
* Windows — `C:\Users\<you>\.motif\model.pt`

Restart Motif (or restart your computer). That is the whole install step:
the engine picks the file up on startup, and from then on the model writes
the notes while the engine keeps every bar full, every chord inside one
hand, and the page properly engraved.

To confirm it is being used, the panel's Preferences shows the engine as
`symbolic+neural`, and generated scores are tagged `neural`.

## Tuning the run

| Flag | Default | Notes |
|---|---|---|
| `--budget` | `26` | Dollars of GPU time. Hard-enforced. |
| `--preset` | `small` | `small` is 25M parameters, sized to this corpus. `base` (90M) is worth it only with a larger corpus folded in. |
| `--gpu` | `A10G` | `L40S` or `A100-40GB` cost more per hour but often more work per dollar. |
| `--transpositions` | `12` | Fewer means less data but a faster prepare step. |
| `--core-only` | off | Skips the large optional collections if bandwidth is short. |

Check `modal run training/modal_app.py` with no arguments for the current
status of the volume — what has been downloaded, prepared and trained.

## Training on your own machine

Only worth it to check the plumbing, not to get a usable model:

```
python training/prepare.py --raw training/data/raw --out training/data/processed
python training/train_local.py --preset tiny --steps 400
```

That trains a deliberately tiny model in about a minute on a laptop CPU. It
writes a checkpoint of exactly the same shape as Modal's, so the whole chain
— corpus, tokens, training, generation, engraving — is genuinely exercised
rather than assumed.

## What the corpus does and does not cover

The public-domain Humdrum editions are strongest on Baroque and Classical
keyboard writing, and on Chopin. They are thin on late Romantic piano —
Rachmaninov and Scriabin are barely represented, because those editions are
mostly still in copyright or not openly encoded.

`training/corpus.py` documents the larger sets worth folding in when you
have the bandwidth and have read their terms — PDMX in particular, which is
a quarter of a million CC0 scores and by far the best single source for
Romantic piano. Point `prepare.py` at any locally downloaded corpus with
`--extra-dir` and every file it can read is used.
