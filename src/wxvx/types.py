from __future__ import annotations

from enum import Enum, auto


class Source(Enum):
    BASELINE = auto()
    FORECAST = auto()
    TRUTH = auto()


class ToGridVal(Enum):
    FCST = auto()
    OBS = auto()


class TruthType(Enum):
    GRID = auto()
    POINT = auto()
