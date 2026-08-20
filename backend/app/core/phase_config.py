"""Loads and validates the canonical SDLC phase configuration.

`config/sdlc_phase_config.json` is the single source of truth for phase
names, sequence, and required documents. This module only reads it —
nothing here should hardcode phase names or document lists.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Phase:
    name: str
    sequence: int
    required_documents: tuple[str, ...]


class PhaseConfig:
    def __init__(self, phases: list[Phase]):
        self._phases = sorted(phases, key=lambda p: p.sequence)
        self._by_name = {p.name: p for p in self._phases}

        sequences = [p.sequence for p in self._phases]
        if sequences != list(range(1, len(sequences) + 1)):
            raise ValueError(
                f"Phase sequence numbers must be contiguous starting at 1, got {sequences}"
            )

    @property
    def phases(self) -> list[Phase]:
        return list(self._phases)

    def get(self, name: str) -> Phase:
        try:
            return self._by_name[name]
        except KeyError:
            raise ValueError(f"Unknown phase: {name!r}") from None


def load_phase_config(path: Path) -> PhaseConfig:
    data = json.loads(Path(path).read_text())
    phases = [
        Phase(
            name=p["name"],
            sequence=p["sequence"],
            required_documents=tuple(p["required_documents"]),
        )
        for p in data["project_phases"]
    ]
    return PhaseConfig(phases)


@lru_cache(maxsize=1)
def get_phase_config() -> PhaseConfig:
    from app.config import settings

    return load_phase_config(settings.phase_config_path)
