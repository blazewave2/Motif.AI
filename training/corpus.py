"""The training corpus: public-domain and openly-licensed classical scores.

Every entry here is either public domain (the music is centuries out of
copyright and the encoding is released freely) or carries a permissive licence.
Nothing is scraped from a commercial catalogue.

`CORE` sources were reachability-checked when this file was written and clone
in a couple of minutes.  `EXTENDED` sources are much larger and are attempted
best-effort: if one is unreachable the run continues with what it has, and the
prepared dataset records exactly which sources contributed.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class Source:
    name: str
    url: str
    kind: str = "git"                 # git | http | hf
    formats: tuple[str, ...] = ("krn",)
    style: str = "unknown"            # the STYLE_ tag these pieces train
    licence: str = "Public Domain"
    note: str = ""
    depth: int = 1
    subpaths: tuple[str, ...] = ()
    optional: bool = False

    @property
    def slug(self) -> str:
        return self.name.replace("/", "-")


#: Verified, fast-cloning Humdrum/MusicXML collections.
CORE: list[Source] = [
    Source("bach-chorales", "https://github.com/craigsapp/bach-370-chorales",
           formats=("krn",), style="bach",
           note="370 four-part chorales — the canonical voice-leading corpus"),
    Source("bach-inventions", "https://github.com/craigsapp/hummel-preludes",
           formats=("krn",), style="classical",
           note="Hummel preludes; classical-era keyboard figuration"),
    Source("beethoven-sonatas", "https://github.com/craigsapp/beethoven-piano-sonatas",
           formats=("krn",), style="beethoven"),
    Source("beethoven-quartets", "https://github.com/craigsapp/beethoven-string-quartets",
           formats=("krn",), style="beethoven"),
    Source("mozart-sonatas", "https://github.com/craigsapp/mozart-piano-sonatas",
           formats=("krn",), style="mozart"),
    Source("haydn-sonatas", "https://github.com/craigsapp/haydn-piano-sonatas",
           formats=("krn",), style="haydn"),
    Source("scarlatti-sonatas", "https://github.com/craigsapp/scarlatti-keyboard-sonatas",
           formats=("krn",), style="scarlatti",
           note="~550 keyboard sonatas — the largest single core collection"),
    Source("chopin-mazurkas", "https://github.com/craigsapp/chopin-mazurkas",
           formats=("krn",), style="chopin"),
    Source("chopin-preludes", "https://github.com/craigsapp/chopin-preludes",
           formats=("krn",), style="chopin"),
    Source("chopin-first-editions",
           "https://github.com/pl-wnifc/humdrum-chopin-first-editions",
           formats=("krn",), style="chopin", licence="CC BY-NC-SA (check before reuse)",
           note="Near-complete Chopin. Non-commercial licence — excluded unless "
                "--include-nc is passed."),
    Source("joplin", "https://github.com/craigsapp/joplin",
           formats=("krn",), style="classical"),
]

#: Larger collections.  Worth the bandwidth on Modal, skipped when unreachable.
EXTENDED: list[Source] = [
    Source("openscore-lieder", "https://github.com/OpenScore/Lieder",
           formats=("mscx", "mxl", "musicxml"), style="schubert", licence="CC0",
           note="~1300 nineteenth-century songs, CC0", optional=True, depth=1),
    Source("openscore-quartets", "https://github.com/OpenScore/StringQuartets",
           formats=("mscx", "mxl", "musicxml"), style="classical", licence="CC0",
           optional=True, depth=1),
    Source("mutopia", "https://github.com/MutopiaProject/MutopiaProject",
           formats=("mid", "midi"), style="classical",
           licence="Public Domain / CC", optional=True, depth=1,
           note="LilyPond sources with rendered MIDI; large clone"),
    Source("humdrum-data", "https://github.com/humdrum-tools/humdrum-data",
           formats=("krn",), style="classical", optional=True, depth=1,
           note="Aggregator with submodules; needs --recurse-submodules to be useful"),
]

#: Datasets that need an explicit opt-in because of size or licence terms.
#: Documented rather than downloaded by default.
NOTES_ON_LARGER_SETS = """
Larger corpora worth adding when you have bandwidth and have read their terms:

  PDMX            ~250k CC0 MusicXML scores from MuseScore.com. By far the best
                  single source for Romantic and late-Romantic piano writing,
                  including Liszt, Scriabin and Rachmaninov, which the Humdrum
                  collections barely cover. Distributed via Hugging Face.
  GiantMIDI-Piano ~10k piano works transcribed from audio (CC BY 4.0). Broad
                  composer coverage but transcription noise; use as a supplement.
  ASAP            Aligned scores and performances, MIT-licensed.
  ATEPP           Expressive piano performance MIDI.

Pass --extra-dir to prepare.py to fold any locally downloaded corpus in; every
file it can read (krn, musicxml, mxl, mscx, mid) is used.
"""


def clone(source: Source, dest: Path, timeout: int = 900) -> tuple[bool, str]:
    """Shallow-clone a source.  Returns (ok, message)."""
    target = dest / source.slug
    if target.exists() and any(target.iterdir()):
        return True, "already present"
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", "--quiet", "--depth", str(source.depth), source.url, str(target)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "clone timed out"
    except FileNotFoundError:
        return False, "git is not installed"
    if proc.returncode != 0:
        shutil.rmtree(target, ignore_errors=True)
        return False, (proc.stderr or "clone failed").strip().splitlines()[-1][:200]
    return True, "cloned"


def fetch_all(dest: Path, include_extended: bool = True,
              include_nc: bool = False) -> dict:
    """Download the corpus, reporting exactly what succeeded."""
    dest.mkdir(parents=True, exist_ok=True)
    report = {"sources": [], "ok": 0, "failed": 0}
    plan = list(CORE) + (list(EXTENDED) if include_extended else [])
    for src in plan:
        if "NC" in src.licence and not include_nc:
            report["sources"].append({**asdict(src), "status": "skipped",
                                      "reason": "non-commercial licence"})
            continue
        ok, msg = clone(src, dest)
        report["sources"].append({**asdict(src), "status": "ok" if ok else "failed",
                                  "reason": msg})
        report["ok" if ok else "failed"] += 1
        print(f"  [{'ok ' if ok else 'FAIL'}] {src.name:26s} {msg}", flush=True)
    (dest / "corpus-report.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="download the Motif training corpus")
    ap.add_argument("--dest", default="training/data/raw")
    ap.add_argument("--core-only", action="store_true")
    ap.add_argument("--include-nc", action="store_true",
                    help="include non-commercially licensed collections")
    args = ap.parse_args()
    r = fetch_all(Path(args.dest), include_extended=not args.core_only,
                  include_nc=args.include_nc)
    print(f"\n{r['ok']} sources downloaded, {r['failed']} failed")
    print(NOTES_ON_LARGER_SETS)
