"""Checks a composer's draft must pass before it becomes a score.

Errors are the things that make a page wrong — a bar that doesn't add up,
a note no instrument can reach, a chord no hand can span. They go back to
the composer to fix. Warnings are things a composer might mean but usually
doesn't, and are shown to the composer's critic rather than enforced.
"""
from __future__ import annotations

from fractions import Fraction

from .msn import Issue, MsnPiece, bar_length, pitch_text

#: Instruments that play one note at a time.
MONOPHONIC = {"flute", "piccolo", "oboe", "english_horn", "clarinet", "bass_clarinet",
              "bassoon", "contrabassoon", "soprano_sax", "alto_sax", "tenor_sax",
              "recorder", "horn", "trumpet", "trumpet_c", "trombone", "bass_trombone",
              "tuba", "soprano", "mezzo", "alto", "tenor", "baritone", "bass", "voice"}
BOWED = {"violin", "viola", "cello", "double_bass"}


def validate(piece: MsnPiece, *, expect: tuple[int, int] | None = None,
             hand_span: int = 16, time_at_start: tuple[int, int] | None = None
             ) -> list[Issue]:
    """Every problem in ``piece``, errors first. Parse problems are included."""
    issues: list[Issue] = list(piece.issues)
    _numbering(piece, expect, issues)
    _durations(piece, issues, time_at_start)
    _coverage(piece, issues)
    _ranges(piece, issues)
    _hands(piece, issues, hand_span)
    _lines(piece, issues)
    _tuplets(piece, issues)
    issues.sort(key=lambda i: (i.severity != "error", i.measure if i.measure is not None else -1))
    return issues


def errors_only(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == "error"]


def describe(issues: list[Issue], limit: int = 40) -> str:
    """Issues as a list the composer can act on, one per line."""
    lines = [f"- {i}" for i in issues[:limit]]
    if len(issues) > limit:
        lines.append(f"- … and {len(issues) - limit} more of the same kind")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
def _numbering(piece: MsnPiece, expect, issues: list[Issue]) -> None:
    nums = piece.numbers
    if not nums:
        issues.append(Issue("error", "no bars were written (each bar starts with a line "
                            "like 'm1')", code="numbering"))
        return
    for a, b in zip(nums, nums[1:]):
        if b != a + 1:
            issues.append(Issue("error", f"bar numbers jump from m{a} to m{b}; number bars "
                                "consecutively", b, code="numbering"))
    if 0 in nums and nums[0] != 0:
        issues.append(Issue("error", "m0 (a pickup bar) can only be the first bar", 0,
                            code="numbering"))
    if expect is not None:
        lo, hi = expect
        missing = [n for n in range(lo, hi + 1) if n not in nums]
        extra = [n for n in nums if n < lo or n > hi]
        if missing:
            issues.append(Issue("error", "missing bars: " + _ranges_text(missing),
                                missing[0], code="numbering"))
        if extra:
            issues.append(Issue("error", "bars outside the requested range "
                                f"m{lo}–m{hi}: " + _ranges_text(extra), extra[0],
                                code="numbering"))


def _durations(piece: MsnPiece, issues: list[Issue], time_at_start) -> None:
    time = tuple(time_at_start or piece.time)
    for i, m in enumerate(piece.measures):
        if m.time:
            time = tuple(m.time)
        want = bar_length(time)
        pickup = m.number == 0 and i == 0
        lengths = {vl.label: vl.duration for vl in m.voices if not vl.has_bar_rest}
        if pickup:
            if lengths:
                longest = max(lengths.values())
                for label, got in lengths.items():
                    if got != longest and got != 0:
                        issues.append(Issue("error", f"pickup voices disagree: {_q(got)} here, "
                                            f"{_q(longest)} elsewhere", m.number, label,
                                            "duration"))
                if longest >= want:
                    issues.append(Issue("error", f"a pickup bar (m0) must be shorter than a "
                                        f"full bar of {time[0]}/{time[1]}", m.number,
                                        code="duration"))
            continue
        for vl in m.voices:
            if vl.has_bar_rest:
                continue
            got = vl.duration
            if got != want:
                issues.append(Issue(
                    "error", f"{_q(got)} written but {time[0]}/{time[1]} needs {_q(want)}"
                    f" ({_beats(want - got)})", m.number, vl.label, "duration"))


def _coverage(piece: MsnPiece, issues: list[Issue]) -> None:
    """A staff with no line in a bar will simply rest — usually an oversight."""
    for m in piece.measures:
        present = {(v.part, v.staff) for v in m.voices}
        for p in piece.parts:
            for staff in range(1, p.staves + 1):
                if (p.id, staff) not in present:
                    from .msn import label_for
                    label = label_for(piece, p.id, staff, 1)
                    issues.append(Issue("warning", f"{label} has no line (it will rest; "
                                        f"write 'R' to say so)", m.number, label, "coverage"))


def _ranges(piece: MsnPiece, issues: list[Issue]) -> None:
    for m in piece.measures:
        for vl in m.voices:
            part = piece.part(vl.part)
            if part is None:
                continue
            inst = part.instrument
            lo, hi = inst.low, inst.high
            if inst.staves >= 2 and inst.keyboard:
                lo, hi = inst.low, inst.high
            reported = False
            for ev in vl.events:
                for p in ev.pitches + [p for g in ev.graces for p in g.pitches]:
                    if p.midi < lo or p.midi > hi:
                        if not reported:
                            issues.append(Issue(
                                "error", f"{pitch_text(p)} is outside the {inst.name}'s "
                                f"range ({_name(lo)}–{_name(hi)})", m.number, vl.label, "range"))
                            reported = True


def _hands(piece: MsnPiece, issues: list[Issue], hand_span: int) -> None:
    """Each hand plays what starts together on its staff; it must fit the hand."""
    for m in piece.measures:
        for part in piece.parts:
            if not part.instrument.keyboard or part.instrument.key == "harp":
                continue
            for staff in range(1, part.staves + 1):
                if part.instrument.key == "organ" and staff == 3:
                    continue
                onsets: dict[Fraction, list] = {}
                arp_at: set[Fraction] = set()
                for vl in m.voices:
                    if vl.part != part.id or vl.staff != staff:
                        continue
                    for ev in vl.events:
                        if ev.pitches and ev.kind == "note":
                            onsets.setdefault(ev.offset, []).extend(ev.pitches)
                            if "arp" in ev.marks:
                                arp_at.add(ev.offset)
                for at, pitches in sorted(onsets.items()):
                    midis = sorted({p.midi for p in pitches})
                    span = midis[-1] - midis[0]
                    limit = 24 if at in arp_at else hand_span
                    from .msn import label_for
                    label = label_for(piece, part.id, staff, 1)
                    if span > limit:
                        issues.append(Issue(
                            "error", f"at beat {_beat(at, m)} one hand is asked to span "
                            f"{_interval_name(span)} ({pitch_text(min(pitches, key=lambda p: p.midi))}"
                            f"–{pitch_text(max(pitches, key=lambda p: p.midi))}); keep a hand "
                            f"within a tenth, or roll it with +arp, or give notes to the "
                            f"other hand", m.number, label, "span"))
                    elif len(midis) > 5:
                        issues.append(Issue(
                            "error", f"at beat {_beat(at, m)} one hand has {len(midis)} "
                            "notes; five is the most a hand can play", m.number, label, "span"))


def _lines(piece: MsnPiece, issues: list[Issue]) -> None:
    for m in piece.measures:
        for vl in m.voices:
            part = piece.part(vl.part)
            if part is None:
                continue
            key = part.instrument.key
            for ev in vl.events:
                if len(ev.pitches) < 2:
                    continue
                if key in MONOPHONIC:
                    issues.append(Issue(
                        "error", f"the {part.instrument.name} plays one note at a time; "
                        f"a chord was written", m.number, vl.label, "chord"))
                    break
                if key in BOWED and len(ev.pitches) > 4:
                    issues.append(Issue(
                        "error", "a string player can stop at most four notes",
                        m.number, vl.label, "chord"))
                    break
                if key in BOWED and len(ev.pitches) >= 3 and ev.duration > Fraction(1):
                    issues.append(Issue(
                        "warning", "a triple or quadruple stop can't be sustained; "
                        "it will be rolled", m.number, vl.label, "chord"))


def _tuplets(piece: MsnPiece, issues: list[Issue]) -> None:
    for m in piece.measures:
        for vl in m.voices:
            group = []
            for ev in vl.events:
                if ev.tuplet and ev.tuplet_start:
                    group = [ev]
                elif ev.tuplet and group:
                    group.append(ev)
                if ev.tuplet and ev.tuplet_stop and group:
                    actual, normal = group[0].tuplet
                    unit = min(e.base for e in group)
                    written = sum((e.written for e in group), Fraction(0))
                    if written != unit * actual:
                        issues.append(Issue(
                            "warning", f"a {actual}-tuplet holds {float(written / unit):g} of its "
                            f"{actual} notes", m.number, vl.label, "tuplet"))
                    group = []


# ---------------------------------------------------------------------------
def _q(value: Fraction) -> str:
    """A length in quarter notes, as plainly as possible."""
    if value == 0:
        return "nothing"
    if value.denominator == 1:
        n = int(value)
        return f"{n} quarter" + ("" if n == 1 else "s")
    return f"{float(value):.4g} quarters"


def _beats(diff: Fraction) -> str:
    if diff > 0:
        return f"{_q(diff)} short"
    return f"{_q(-diff)} too long"


def _beat(at: Fraction, m) -> str:
    return f"{float(at + 1):g}"


def _interval_name(semis: int) -> str:
    names = {12: "an octave", 13: "a minor ninth", 14: "a ninth", 15: "a minor tenth",
             16: "a tenth", 17: "an eleventh", 18: "an augmented eleventh",
             19: "a twelfth", 24: "two octaves"}
    return names.get(semis, f"{semis} semitones")


_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def _name(midi: int) -> str:
    return f"{_NAMES[midi % 12]}{midi // 12 - 1}"


def _ranges_text(nums: list[int]) -> str:
    out, start, prev = [], None, None
    for n in nums:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(f"m{start}" if start == prev else f"m{start}–m{prev}")
            start = prev = n
    if start is not None:
        out.append(f"m{start}" if start == prev else f"m{start}–m{prev}")
    return ", ".join(out)
