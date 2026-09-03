"""Standard MIDI File export — pure stdlib, used for preview playback."""
from __future__ import annotations

import struct

from ..score import DIVISIONS, Part, Score, bar_duration

DYN_VELOCITY = {"ppp": 20, "pp": 33, "p": 49, "mp": 64, "mf": 80,
                "f": 96, "ff": 112, "fff": 126}


def _vlq(n: int) -> bytes:
    """MIDI variable-length quantity."""
    n = max(0, int(n))
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


class _Track:
    def __init__(self) -> None:
        self.events: list[tuple[int, int, bytes]] = []   # (tick, order, payload)
        self._order = 0

    def add(self, tick: int, payload: bytes, order: int = 1) -> None:
        self._order += 1
        self.events.append((tick, order * 1000 + self._order, payload))

    def render(self) -> bytes:
        self.events.sort(key=lambda e: (e[0], e[1]))
        out = bytearray()
        last = 0
        for tick, _, payload in self.events:
            out += _vlq(tick - last) + payload
            last = tick
        out += _vlq(0) + b"\xff\x2f\x00"        # end of track
        return b"MTrk" + struct.pack(">I", len(out)) + bytes(out)


def to_midi(score: Score) -> bytes:
    bar_ticks = bar_duration(score.time)
    tracks: list[bytes] = []

    # Conductor track: tempo, metre and key.
    conductor = _Track()
    conductor.add(0, b"\xff\x03" + _len(score.title.encode("utf-8")[:120]), 0)
    for t in sorted(score.tempos, key=lambda x: x.measure) or []:
        us = int(60_000_000 / max(1.0, t.bpm))
        conductor.add((t.measure - 1) * bar_ticks,
                      b"\xff\x51\x03" + struct.pack(">I", us)[1:], 0)
    if not score.tempos:
        us = int(60_000_000 / max(1.0, score.tempo))
        conductor.add(0, b"\xff\x51\x03" + struct.pack(">I", us)[1:], 0)
    num, den = score.time
    denom_pow = max(0, (den.bit_length() - 1))
    conductor.add(0, b"\xff\x58\x04" + bytes([num, denom_pow, 24, 8]), 0)
    conductor.add(0, b"\xff\x59\x02" + bytes([score.key.fifths & 0xFF,
                                              1 if score.key.is_minor else 0]), 0)
    tracks.append(conductor.render())

    for idx, part in enumerate(score.parts):
        channel = idx % 16
        if channel == 9:                       # keep the drum channel clear
            channel = (idx + 1) % 16
        tr = _Track()
        tr.add(0, b"\xff\x03" + _len(part.name.encode("utf-8")[:120]), 0)
        tr.add(0, bytes([0xC0 | channel, part.midi_program & 0x7F]), 0)
        _render_part(tr, part, channel, bar_ticks)
        tracks.append(tr.render())

    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), DIVISIONS)
    return header + b"".join(tracks)


def _render_part(tr: _Track, part: Part, channel: int, bar_ticks: int) -> None:
    velocity = 80
    for m in part.measures:
        base = (m.number - 1) * bar_ticks
        for d in m.directions:
            if d.kind == "dynamics":
                velocity = DYN_VELOCITY.get(d.value, velocity)
        for voice, notes in sorted(m.voices.items()):
            t = base
            pending_ties: dict[int, int] = {}
            for n in notes:
                if n.grace:
                    # Steal a little time before the beat, as a player would.
                    g = max(1, DIVISIONS // 8)
                    for p in n.pitches:
                        tr.add(max(base, t - g),
                               bytes([0x90 | channel, p.midi & 0x7F,
                                      max(1, n.velocity - 15)]))
                        tr.add(t, bytes([0x80 | channel, p.midi & 0x7F, 0]))
                    continue
                if not n.is_rest:
                    vel = n.velocity if n.velocity else velocity
                    vel = max(1, min(127, int(vel * 0.55 + velocity * 0.45)))
                    for p in n.pitches:
                        key = p.midi
                        if n.tie_stop and key in pending_ties:
                            pending_ties[key] = t + n.duration
                            continue
                        tr.add(t, bytes([0x90 | channel, key & 0x7F, vel]))
                        if n.tie_start:
                            pending_ties[key] = t + n.duration
                        else:
                            tr.add(t + max(1, int(n.duration * 0.94)),
                                   bytes([0x80 | channel, key & 0x7F, 0]))
                    # Close any tie chain that has just ended.
                    for key, end in list(pending_ties.items()):
                        if not n.tie_start and key in [p.midi for p in n.pitches]:
                            tr.add(end, bytes([0x80 | channel, key & 0x7F, 0]))
                            pending_ties.pop(key, None)
                t += n.duration
            for key, end in pending_ties.items():
                tr.add(end, bytes([0x80 | channel, key & 0x7F, 0]))


def _len(data: bytes) -> bytes:
    return _vlq(len(data)) + data
