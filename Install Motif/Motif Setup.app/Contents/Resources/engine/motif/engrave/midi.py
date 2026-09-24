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


def _measure_starts(score: Score) -> list[int]:
    """Absolute tick of every bar, from what is actually written in each.

    Counting bars as ``(number - 1) * bar_length`` breaks on a pickup bar
    (numbered 0) and on any change of metre; summing real bar lengths doesn't.
    """
    if not score.parts:
        return []
    starts, t = [], 0
    time = tuple(score.time)
    for m in score.parts[0].measures:
        if m.time:
            time = tuple(m.time)
        starts.append(t)
        written = max((sum(n.duration for n in notes if not n.grace)
                       for notes in m.voices.values()), default=0)
        full = bar_duration(time)
        t += written if (m.implicit and 0 < written < full) else full
    return starts


def to_midi(score: Score) -> bytes:
    tracks: list[bytes] = []
    starts = _measure_starts(score)
    index = {}
    if score.parts:
        for i, m in enumerate(score.parts[0].measures):
            index.setdefault(m.number, i)

    def at(measure: int, offset: int = 0) -> int:
        i = index.get(measure)
        if i is None or i >= len(starts):
            return max(0, (measure - 1) * bar_duration(score.time)) + offset
        return starts[i] + offset

    # Conductor track: tempo, metre and key.
    conductor = _Track()
    conductor.add(0, b"\xff\x03" + _len(score.title.encode("utf-8")[:120]), 0)
    tempos = sorted(score.tempos, key=lambda x: (at(x.measure, getattr(x, "offset", 0))))
    for t in tempos:
        qbpm = t.quarter_bpm if hasattr(t, "quarter_bpm") else t.bpm
        us = int(60_000_000 / max(1.0, qbpm))
        conductor.add(at(t.measure, getattr(t, "offset", 0)),
                      b"\xff\x51\x03" + struct.pack(">I", us)[1:], 0)
    if not tempos:
        us = int(60_000_000 / max(1.0, score.tempo))
        conductor.add(0, b"\xff\x51\x03" + struct.pack(">I", us)[1:], 0)
    num, den = score.time
    denom_pow = max(0, (den.bit_length() - 1))
    conductor.add(0, b"\xff\x58\x04" + bytes([num, denom_pow, 24, 8]), 0)
    conductor.add(0, b"\xff\x59\x02" + bytes([score.key.fifths & 0xFF,
                                              1 if score.key.is_minor else 0]), 0)
    if score.parts:
        for i, m in enumerate(score.parts[0].measures):
            if m.time and i > 0 and i < len(starts):
                n, d = m.time
                conductor.add(starts[i], b"\xff\x58\x04" +
                              bytes([n, max(0, d.bit_length() - 1), 24, 8]), 0)
    tracks.append(conductor.render())

    for idx, part in enumerate(score.parts):
        channel = idx % 16
        if channel == 9:                       # keep the drum channel clear
            channel = (idx + 1) % 16
        tr = _Track()
        tr.add(0, b"\xff\x03" + _len(part.name.encode("utf-8")[:120]), 0)
        tr.add(0, bytes([0xC0 | channel, part.midi_program & 0x7F]), 0)
        shift = 0
        if part.transpose:
            diatonic, chromatic, octave = part.transpose
            shift = chromatic + 12 * octave
        _render_part(tr, part, channel, starts, shift)
        tracks.append(tr.render())

    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), DIVISIONS)
    return header + b"".join(tracks)


def _render_part(tr: _Track, part: Part, channel: int, starts: list[int],
                 shift: int = 0) -> None:
    velocity = 80
    # Ties are followed per voice and per pitch, across bar lines.
    held: dict[tuple[int, int], int] = {}          # (voice, midi) -> note-off tick
    for mi, m in enumerate(part.measures):
        base = starts[mi] if mi < len(starts) else 0
        for d in m.directions:
            if d.kind == "dynamics":
                velocity = DYN_VELOCITY.get(d.value, velocity)
        for voice, notes in sorted(m.voices.items()):
            t = base
            for n in notes:
                if n.grace:
                    # Steal a little time before the beat, as a player would.
                    g = max(1, DIVISIONS // 8)
                    for p in n.pitches:
                        key = max(0, min(127, p.midi + shift))
                        tr.add(max(base, t - g),
                               bytes([0x90 | channel, key, max(1, n.velocity - 15)]))
                        tr.add(t, bytes([0x80 | channel, key, 0]))
                    continue
                if not n.is_rest:
                    vel = n.velocity if n.velocity else velocity
                    vel = max(1, min(127, int(vel * 0.55 + velocity * 0.45)))
                    starts_tie = (set(n.tie_start_pitches) if n.tie_start_pitches is not None
                                  else {p.midi for p in n.pitches} if n.tie_start else set())
                    stops_tie = (set(n.tie_stop_pitches) if n.tie_stop_pitches is not None
                                 else {p.midi for p in n.pitches} if n.tie_stop else set())
                    for p in n.pitches:
                        key = max(0, min(127, p.midi + shift))
                        continuing = p.midi in stops_tie and (voice, key) in held
                        if not continuing:
                            tr.add(t, bytes([0x90 | channel, key, vel]))
                        if p.midi in starts_tie:
                            held[(voice, key)] = t + n.duration
                        else:
                            held.pop((voice, key), None)
                            tr.add(t + max(1, int(n.duration * 0.94)),
                                   bytes([0x80 | channel, key, 0]))
                t += n.duration
    for (voice, key), end in held.items():
        tr.add(end, bytes([0x80 | channel, key, 0]))


def _len(data: bytes) -> bytes:
    return _vlq(len(data)) + data
