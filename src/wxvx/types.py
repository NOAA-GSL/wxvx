from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from wxvx.strings import MET, S
from wxvx.util import (
    LINETYPE,
)


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


@dataclass(frozen=True)
class VarMeta:
    cf_standard_name: str
    description: str
    level_type: str
    met_stats: list[str]
    name: str
    units: str
    # Optional:
    cat_thresh: list[str] | None = None
    cnt_thresh: list[str] | None = None
    nbrhd_shape: str | None = None
    nbrhd_width: list[int] | None = None

    def __post_init__(self):
        assert self.cf_standard_name
        assert self.description
        assert self.level_type in (S.atmosphere, S.heightAboveGround, S.isobaricInhPa, S.surface)
        assert self.met_stats
        assert self.name
        assert self.units
        assert all(x in LINETYPE for x in self.met_stats)
        for k, v in vars(self).items():
            match k:
                case MET.cat_thresh:
                    assert v is None or (v and all(isinstance(x, str) for x in v))
                case MET.cnt_thresh:
                    assert v is None or (v and all(isinstance(x, str) for x in v))
                case MET.nbrhd_shape:
                    assert v is None or v in (MET.CIRCLE, MET.SQUARE)
                case MET.nbrhd_width:
                    assert v is None or (v and all(isinstance(x, int) for x in v))
