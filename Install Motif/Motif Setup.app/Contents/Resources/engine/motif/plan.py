"""The composition plan — the contract between understanding a request and
rendering a score.  Everything the agent decides ends up here, which makes a
piece reproducible, inspectable and editable."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from .theory.pitch import Key


@dataclass
class SectionPlan:
    label: str = "A"
    bars: int = 8
    key: str = "C major"                 # absolute; the planner resolves modulations
    energy: float = 0.5                  # 0 calm .. 1 climactic
    dynamic: str = "mf"
    texture_lh: str = "block_chords"
    texture_rh: str = "melody"
    cadence: str = "authentic"
    motif_op: str = "state"              # state|develop|invert|sequence|fragment|augment|recall
    harmonic_rhythm: str = "moderate"
    register: int = 0                    # octave displacement for the right hand
    progression: list[str] = field(default_factory=list)   # explicit romans, optional
    role: str = "theme"                  # theme|transition|development|recap|coda|intro|cadenza
    tempo_scale: float = 1.0
    text: str = ""                       # expressive marking printed at the section head
    repeat: bool = False
    time: tuple[int, int] | None = None
    solo: bool = False                   # concerto: solo vs tutti
    tutti: bool = False

    def resolved_key(self) -> Key:
        return Key.parse(self.key)


@dataclass
class InstrumentPlan:
    name: str = "Piano"
    abbreviation: str = "Pno."
    midi_program: int = 0
    staves: int = 2
    clefs: list[str] = field(default_factory=lambda: ["G", "F"])
    role: str = "solo"                  # solo|melody|harmony|bass|inner|doubling
    range_low: int = 21
    range_high: int = 108
    transpose: int = 0


@dataclass
class CompositionPlan:
    title: str = "Untitled"
    subtitle: str = ""
    style: str = "classical"
    key: str = "C major"
    time: tuple[int, int] = (4, 4)
    tempo: int = 100
    tempo_text: str = ""
    form: str = "ternary"
    sections: list[SectionPlan] = field(default_factory=list)
    instruments: list[InstrumentPlan] = field(default_factory=list)
    seed: int = 0
    prompt: str = ""
    character: str = ""
    ensemble: str = "solo_piano"
    movements: list["CompositionPlan"] = field(default_factory=list)
    notes: str = ""
    use_model: bool = True

    @property
    def total_bars(self) -> int:
        return sum(s.bars for s in self.sections) or sum(
            m.total_bars for m in self.movements)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent, default=str)

    @staticmethod
    def from_dict(d: dict) -> "CompositionPlan":
        secs = [SectionPlan(**{k: v for k, v in s.items()
                               if k in SectionPlan.__dataclass_fields__})
                for s in d.get("sections", [])]
        insts = [InstrumentPlan(**{k: v for k, v in i.items()
                                   if k in InstrumentPlan.__dataclass_fields__})
                 for i in d.get("instruments", [])]
        movs = [CompositionPlan.from_dict(m) for m in d.get("movements", [])]
        base = {k: v for k, v in d.items()
                if k in CompositionPlan.__dataclass_fields__
                and k not in ("sections", "instruments", "movements")}
        if "time" in base and isinstance(base["time"], list):
            base["time"] = tuple(base["time"])
        return CompositionPlan(sections=secs, instruments=insts, movements=movs, **base)
