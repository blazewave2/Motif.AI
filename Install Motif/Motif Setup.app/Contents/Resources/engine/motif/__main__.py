"""CLI entry point: ``python -m motif`` starts the service."""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="motif", description="Motif.ai composing engine")
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("serve", help="run the local service for the MuseScore plugin")
    s.add_argument("--port", type=int, default=None)
    s.add_argument("--host", default="127.0.0.1")

    c = sub.add_parser("compose", help="compose from a prompt and write files")
    c.add_argument("prompt", nargs="+")
    c.add_argument("-o", "--out", default="out")
    c.add_argument("--seed", type=int, default=None)
    c.add_argument("--style", default=None)
    c.add_argument("--ensemble", default=None)
    c.add_argument("--midi", action="store_true", help="also write a MIDI file")
    c.add_argument("--quality", choices=["maximum", "best", "balanced", "sketch"],
                   default=None, help="how much care the composer takes")

    sub.add_parser("styles", help="list the available styles")
    sub.add_parser("token", help="print the local API token")

    args = ap.parse_args(argv)
    cmd = args.cmd or "serve"

    if cmd == "serve":
        from .server.app import serve
        serve(port=args.port, host=args.host)
        return 0

    if cmd == "compose":
        from pathlib import Path
        from .agent.agent import Request
        from .server.app import MotifState, ensure_config
        cfg = ensure_config()
        if args.quality:
            cfg["composer_quality"] = args.quality
        state = MotifState(cfg)
        prompt = " ".join(args.prompt)

        def progress(update):
            text = update if isinstance(update, str) else (
                f"[{int(update.fraction * 100):3d}%] {update.label}"
                + (f" — {update.detail}" if update.detail else ""))
            print(f"  {text[:150]}", file=sys.stderr)

        result = state.agent.run(Request(prompt=prompt, seed=args.seed, style=args.style,
                                         ensemble=args.ensemble),
                                 progress=progress)
        if not result.ok:
            print(f"error: {result.error}", file=sys.stderr)
            return 1
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        name = (result.title or (result.plan.title if result.plan else "")
                or "motif").replace(" ", "-")
        xml = out / f"{name}.musicxml"
        xml.write_text(result.musicxml, encoding="utf-8")
        print(result.message)
        print(f"\n{result.preview}\n")
        print(f"wrote {xml}")
        if args.midi and result.midi:
            mid = out / f"{name}.mid"
            mid.write_bytes(result.midi)
            print(f"wrote {mid}")
        return 0

    if cmd == "styles":
        from .compose.styles import STYLES
        for n, p in sorted(STYLES.items(), key=lambda kv: kv[1].display):
            print(f"  {n:16s} {p.display:22s} {p.era:14s} {', '.join(p.forms[:4])}")
        return 0

    if cmd == "token":
        from .server.app import ensure_config
        print(ensure_config()["token"])
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
