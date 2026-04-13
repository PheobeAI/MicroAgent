# core/loop/types.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Step:
    tool: str
    args: dict
    reason: str


@dataclass
class Observation:
    step: Step
    result: str
    ok: bool
    error: str | None


@dataclass
class SynthContext:
    task: str
    observations: list[Observation]
    round: int = 0
