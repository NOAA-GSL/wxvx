from __future__ import annotations

from enum import Enum, auto


class ToGridVal(Enum):
    FCST = auto()
    OBS = auto()


class TruthType(Enum):
    GRID = auto()
    POINT = auto()
