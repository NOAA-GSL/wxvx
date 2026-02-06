from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
from functools import cached_property
from pathlib import Path
from typing import Any, Protocol, cast

from uwtools.api.config import YAMLConfig, validate

from wxvx.strings import MET, S
from wxvx.util import LINETYPE, WXVXError, expand, resource_path, to_datetime, to_timedelta

_TRUTH_NAMES_GRID = (S.GFS, S.HRRR)
_TRUTH_NAMES_POINT = (S.PREPBUFR,)
_TRUTH_NAMES = tuple(sorted([*_TRUTH_NAMES_GRID, *_TRUTH_NAMES_POINT]))

_DatetimeT = str | datetime
_TimedeltaT = str | int


class Named(Protocol):
    name: str


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


def validated_config(yc: YAMLConfig) -> Config:
    if not validate(schema_file=resource_path("config.jsonschema"), config_data=yc.data):
        msg = "Config failed schema validation"
        raise WXVXError(msg)
    return Config(yc.data)


# Below, assert statements relate to config requirements that should have been enforced by a prior
# schema check. If an assertion is triggered, it's a wxvx bug, not a user issue.


@dataclass(frozen=True)
class Baseline:
    name: str | None
    url: str | None = None

    def __post_init__(self):
        # Handle 'name':
        names = [*_TRUTH_NAMES_GRID, S.truth, None]
        if self.name not in names:
            strnames = [str(name) for name in names]
            raise WXVXError("Set baseline.name to one of: %s" % ", ".join(strnames))
        # Handle combination of 'name' and 'url':
        if self.name == S.truth:
            assert self.url is None
        elif self.name is not None:
            assert self.url is not None


class Config:
    def __init__(self, raw: dict):
        baseline = raw.get(S.baseline, {S.name: None})
        paths = raw[S.paths]
        grids = paths[S.grids]
        self.baseline = Baseline(**baseline)
        self.cycles = Cycles(raw[S.cycles])
        self.forecast = Forecast(**raw[S.forecast])
        self.leadtimes = Leadtimes(raw[S.leadtimes])
        self.ncdiffs: bool = raw.get(S.ncdiffs, False)
        self.paths = Paths(
            grids.get(S.baseline),
            grids.get(S.forecast),
            grids.get(S.truth),
            paths.get(S.obs),
            paths[S.run],
        )
        self.raw = raw
        self.regrid = Regrid(**raw.get(S.regrid, {}))
        self.truth = Truth(**raw[S.truth])
        self.variables = raw[S.variables]
        self._validate()

    KEYS = (S.baseline, S.cycles, S.forecast, S.leadtimes, S.paths, S.truth, S.variables)

    def __eq__(self, other):
        return all(getattr(self, k) == getattr(other, k) for k in self.KEYS)

    def __hash__(self):
        return _hash(self)

    def __repr__(self):
        parts = ["%s=%s" % (x, getattr(self, x)) for x in self.KEYS]
        return "%s(%s)" % (self.__class__.__name__, ", ".join(parts))

    def _validate(self) -> None:
        # Validation tests that span disparate config subtrees are awkward to express in
        # JSON Schema (or yield poor user-facing feedback) and are instead enforced here
        # with explicit checks.

        names = (self.baseline.name, self.forecast.name, self.truth.name)
        if len(set(names)) != len(names):
            msg = "Distinct %s.%s (if set), %s.%s, and %s.%s required" % (
                S.baseline,
                S.name,
                S.forecast,
                S.name,
                S.truth,
                S.name,
            )
            raise WXVXError(msg)
        if self.baseline.name == S.truth:
            if self.truth.type is TruthType.POINT:
                msg = "Values %s.%s '%s' and %s.%s '%s' are incompatible" % (
                    S.baseline,
                    S.name,
                    self.baseline.name,
                    S.truth,
                    S.type,
                    self.truth.type.name.lower(),
                )
                raise WXVXError(msg)
            if self.paths.grids_baseline is not None:
                logging.warning(
                    "Ignoring %s.%s.%s when %s.%s is '%s'",
                    S.paths,
                    S.grids,
                    S.baseline,
                    S.baseline,
                    S.name,
                    S.truth,
                )
        elif self.baseline.name is not None and not self.paths.grids_baseline:
            msg = "Specify %s.%s.%s when %s.%s is not '%s'" % (
                S.paths,
                S.grids,
                S.baseline,
                S.baseline,
                S.name,
                S.truth,
            )
            raise WXVXError(msg)
        if self.regrid.to == S.OBS:
            msg = "Cannot regrid to observations per %s.%s config value" % (S.regrid, S.to)
            raise WXVXError(msg)
        if self.truth.type == TruthType.GRID and not self.paths.grids_truth:
            msg = "Specify %s.%s.%s when %s.%s is '%s'" % (
                S.paths,
                S.grids,
                S.truth,
                S.truth,
                S.type,
                TruthType.GRID.name.lower(),
            )
            raise WXVXError(msg)
        if self.truth.type == TruthType.POINT:
            name = TruthType.POINT.name.lower()
            if self.ncdiffs:
                msg = "Option %s must be false (or omitted) when %s.%s is '%s'" % (
                    S.ncdiffs,
                    S.truth,
                    S.type,
                    name,
                )
                raise WXVXError(msg)
            if not self.paths.obs:
                msg = "Specify %s.%s when %s.%s is '%s'" % (S.paths, S.obs, S.truth, S.type, name)
                raise WXVXError(msg)


@dataclass(frozen=True)
class Coords:
    latitude: str
    level: str
    longitude: str
    time: Time

    KEYS = (S.latitude, S.level, S.longitude, S.time)

    def __hash__(self):
        return _hash(self)

    def __post_init__(self):
        if isinstance(self.time, dict):
            _force(self, S.time, Time(**self.time))


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
                to_datetime(cast(_DatetimeT, self.raw[x])) for x in (S.start, S.stop)
            ]
            td_step = to_timedelta(cast(_TimedeltaT, self.raw[S.step]))
            return expand(dt_start, td_step, dt_stop)
        return sorted(map(to_datetime, self.raw))


class Forecast:
    KEYS = (
        S.coords,
        S.mask,
        S.name,
        S.path,
        "_projection",  # use '_projection' (not 'projection') to avoid triggering the property.
    )

    def __init__(
        self,
        name: str,
        path: str,
        coords: Coords | dict | None = None,
        mask: list[list[float]] | None = None,
        projection: dict | None = None,
    ):
        self._name = name
        self._path = path
        self._coords = coords
        self._mask = mask
        self._projection = projection

    def __eq__(self, other):
        return all(getattr(self, k) == getattr(other, k) for k in self.KEYS)

    def __hash__(self):
        return _hash(self)

    def __repr__(self):
        parts = ["%s=%s" % (x, getattr(self, x)) for x in self.KEYS]
        return "%s(%s)" % (self.__class__.__name__, ", ".join(parts))

    @property
    def name(self) -> str:
        return self._name

    @property
    def path(self) -> str:
        return self._path

    @property
    def coords(self) -> Coords | None:
        if isinstance(self._coords, dict):
            self._coords = Coords(**self._coords)
        return self._coords

    @property
    def mask(self) -> list[list[float]] | None:
        return self._mask

    @property
    def projection(self) -> dict:
        if self._projection is None:
            logging.info("No forecast projection specified, defaulting to latlon")
            self._projection = {S.proj: S.latlon}
        return self._projection


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
                to_timedelta(cast(_TimedeltaT, self.raw[x])) for x in (S.start, S.step, S.stop)
            ]
            return expand(td_start, td_step, td_stop)
        return sorted(map(to_timedelta, self.raw))


@dataclass(frozen=True)
class Paths:
    grids_baseline: Path
    grids_forecast: Path
    grids_truth: Path
    obs: Path
    run: Path

    def __post_init__(self):
        for key in [S.grids_baseline, S.grids_forecast, S.grids_truth, S.obs, S.run]:
            if val := getattr(self, key):
                _force(self, key, Path(val))


@dataclass(frozen=True)
class Regrid:
    # See https://metplus.readthedocs.io/projects/met/en/main_v11.0/Users_Guide/appendixB.html#grids
    # for information on the "GNNN" grid names accepted as regrid-to values.

    method: str = MET.NEAREST
    to: ToGrid | None = None

    def __post_init__(self):
        _force(self, S.to, ToGrid(S.forecast if self.to is None else str(self.to)))
        assert self.to is not None


@dataclass(frozen=True)
class Time:
    inittime: str
    leadtime: str | None = None
    validtime: str | None = None

    def __post_init__(self):
        assert self.leadtime is not None or self.validtime is not None


class ToGrid:
    def __init__(self, val: str):
        self.val: str | ToGridVal = val
        mapping = {S.forecast: ToGridVal.FCST, S.truth: ToGridVal.OBS}
        self.val = mapping.get(val, val)

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(str(self))

    def __repr__(self):
        if isinstance(self.val, ToGridVal):
            return self.val.name
        return self.val


@dataclass(frozen=True)
class Truth:
    name: str
    type: TruthType
    url: str

    def __post_init__(self):
        # Handle 'type': Check validity and normalize values:
        types = dict(
            zip(
                [TruthType.GRID.name.lower(), TruthType.POINT.name.lower()],
                [TruthType.GRID, TruthType.POINT],
                strict=True,
            )
        )
        if isinstance(self.type, str):
            assert self.type in types
        _force(self, S.type, types.get(str(self.type), self.type))
        # Handle 'name':
        if self.name not in _TRUTH_NAMES:
            raise WXVXError("Set truth.name to one of: %s" % ", ".join(_TRUTH_NAMES))
        if self.type is TruthType.GRID and self.name not in _TRUTH_NAMES_GRID:
            raise WXVXError(
                "When truth.type is '%s' set truth.name to: %s"
                % (self.type.name.lower(), ", ".join(_TRUTH_NAMES_GRID))
            )
        if self.type is TruthType.POINT and self.name not in _TRUTH_NAMES_POINT:
            raise WXVXError(
                "When truth.type is '%s' set truth.name to: %s"
                % (self.type.name.lower(), ", ".join(_TRUTH_NAMES_POINT))
            )


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
