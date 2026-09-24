"""How a long piece of composing reports on itself, and how it is stopped.

Composing properly takes time, so every stage says what it is doing through
a progress callback, and the same callback is where a request to stop is
noticed: it raises :class:`Cancelled`, which unwinds the composer cleanly
without writing anything.
"""
from __future__ import annotations

from dataclasses import dataclass


class Cancelled(RuntimeError):
    """The musician pressed Stop."""


@dataclass
class Progress:
    stage: str                # planning | themes | harmony | writing | reviewing | finishing
    label: str                # what the panel shows, in plain words
    detail: str = ""          # a second, quieter line: the bar or the idea being worked on
    fraction: float = 0.0     # 0..1, for the progress bar


def report(callback, update) -> None:
    """Send ``update`` to ``callback``; a failing display never stops the
    music, but a request to stop always does."""
    if callback is None:
        return
    try:
        callback(update)
    except Cancelled:
        raise
    except Exception:
        pass
