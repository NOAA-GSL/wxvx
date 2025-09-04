from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
from functools import cached_property
from pathlib import Path
from typing import Any, cast

from wxvx.util import LINETYPE, expand, to_datetime, to_timedelta

_DatetimeT = str | datetime
_TimedeltaT = str | int

Source = Enum(
    "Source",
    [
        ("BASELINE", auto()),
        ("FORECAST", auto()),
    ],
)

VxType = Enum(
    "VxType",
    [
        ("GRID", auto()),
        ("POINT", auto()),
    ],
)


@dataclass(frozen=True)
class Baseline:
    compare: bool
    name: str
    url: str
    type: VxType

    def __post_init__(self):
        assert self.type in ["grid", "point"]
        newval = {"grid": VxType.GRID, "point": VxType.POINT}
        _force(self, "type", newval.get(str(self.type), self.type))


class Config:
    def __init__(self, raw: dict):
        paths = raw["paths"]
        grids = paths["grids"]
        self.baseline = Baseline(**raw["baseline"])
        self.cycles = Cycles(raw["cycles"])
        self.forecast = Forecast(**raw["forecast"])
        self.leadtimes = Leadtimes(raw["leadtimes"])
        self.paths = Paths(grids.get("baseline"), grids["forecast"], paths.get("obs"), paths["run"])
        self.regrid = Regrid(**raw.get("regrid", {}))
        self.variables = raw["variables"]

    KEYS = ("baseline", "cycles", "forecast", "leadtimes", "paths", "variables")

    def __eq__(self, other):
        return all(getattr(self, k) == getattr(other, k) for k in self.KEYS)

    def __hash__(self):
        return _hash(self)

    def __repr__(self):
        parts = ["%s=%s" % (x, getattr(self, x)) for x in self.KEYS]
        return "%s(%s)" % (self.__class__.__name__, ", ".join(parts))


@dataclass(frozen=True)
class Coords:
    latitude: str
    level: str
    longitude: str
    time: Time

    KEYS = ("latitude", "level", "longitude", "time")

    def __hash__(self):
        return _hash(self)

    def __post_init__(self):
        if isinstance(self.time, dict):
            _force(self, "time", Time(**self.time))


class Cycles:
    def __init__(self, raw: dict[str, str | int | datetime] | list[str | datetime]):
        self.raw = raw

    def __eq__(self, other):
        return self.values == other.values

    def __hash__(self):
        return hash(tuple(self.values))

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, self.raw)

    @cached_property
    def values(self) -> list[datetime]:
        if isinstance(self.raw, dict):
            dt_start, dt_stop = [
                to_datetime(cast(_DatetimeT, self.raw[x])) for x in ("start", "stop")
            ]
            td_step = to_timedelta(cast(_TimedeltaT, self.raw["step"]))
            return expand(dt_start, td_step, dt_stop)
        return sorted(map(to_datetime, self.raw))


@dataclass(frozen=True)
class Forecast:
    coords: Coords
    name: str
    path: str
    projection: dict
    mask: tuple[tuple[float, float]] | None = None

    KEYS = ("coords", "mask", "name", "path", "projection")

    def __hash__(self):
        return _hash(self)

    def __post_init__(self):
        if isinstance(self.coords, dict):
            coords = Coords(**self.coords)
            _force(self, "coords", coords)
        if self.mask:
            _force(self, "mask", tuple(tuple(x) for x in self.mask))


class Leadtimes:
    def __init__(self, raw: dict[str, str | int] | list[str | int]):
        self.raw = raw

    def __eq__(self, other):
        return self.values == other.values

    def __hash__(self):
        return hash(tuple(self.values))

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, self.raw)

    @cached_property
    def values(self) -> list[timedelta]:
        if isinstance(self.raw, dict):
            td_start, td_step, td_stop = [
                to_timedelta(cast(_TimedeltaT, self.raw[x])) for x in ("start", "step", "stop")
            ]
            return expand(td_start, td_step, td_stop)
        return sorted(map(to_timedelta, self.raw))


@dataclass(frozen=True)
class Paths:
    grids_baseline: Path
    grids_forecast: Path
    obs: Path
    run: Path

    def __post_init__(self):
        for key in ["grids_baseline", "grids_forecast", "obs", "run"]:
            if val := getattr(self, key):
                _force(self, key, Path(val))


@dataclass(frozen=True)
class Regrid:
    method: str = "NEAREST"
    to: str = "forecast"

    # See https://metplus.readthedocs.io/projects/met/en/main_v11.0/Users_Guide/appendixB.html#grids
    # for information on the "GNNN" grid names accepted as regrid-to values.

    def __post_init__(self):
        mapping = {"baseline": "OBS", "forecast": "FCST"}
        if self.to in mapping:
            _force(self, "to", mapping[self.to])


@dataclass(frozen=True)
class Time:
    inittime: str
    leadtime: str | None = None
    validtime: str | None = None

    def __post_init__(self):
        assert self.leadtime is not None or self.validtime is not None


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
        for k, v in vars(self).items():
            match k:
                case "cat_thresh":
                    assert v is None or (v and all(isinstance(x, str) for x in v))
                case "cf_standard_name":
                    assert v
                case "cnt_thresh":
                    assert v is None or (v and all(isinstance(x, str) for x in v))
                case "description":
                    assert v
                case "level_type":
                    assert v in ("atmosphere", "heightAboveGround", "isobaricInhPa", "surface")
                case "met_stats":
                    assert v
                    assert all(x in LINETYPE for x in v)
                case "name":
                    assert v
                case "nbrhd_shape":
                    assert v is None or v in ("CIRCLE", "SQUARE")
                case "nbrhd_width":
                    assert v is None or (v and all(isinstance(x, int) for x in v))
                case "units":
                    assert v


# Helpers


def _force(obj: Any, name: str, val: Any) -> None:
    object.__setattr__(obj, name, val)


def _hash(obj: Any) -> int:
    h = None
    for k in obj.KEYS:
        x = getattr(obj, k)
        try:
            h = hash((h, hash(x)))
        except TypeError:
            h = hash((h, json.dumps(x, sort_keys=True)))
    assert h is not None
    return h
