from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING
from unittest.mock import Mock

import numpy as np
import xarray as xr
from iotaa import Node
from pytest import fixture

from wxvx import times
from wxvx.strings import NOAA, S
from wxvx.types import Config

if TYPE_CHECKING:
    from collections.abc import Callable

logging.getLogger().setLevel(logging.DEBUG)


@fixture
def check_cf_metadata() -> Callable:
    def check(ds: xr.DataArray, name: str, level: float | None = None):
        assert ds.attrs["Conventions"] == "CF-1.8"
        level_actual = ds.attrs[S.level]
        if level:
            assert level_actual == level
        else:
            assert np.isnan(level_actual)
        da = ds[name]
        for k, v in [("standard_name", "geopotential_height"), ("units", "m")]:
            assert da.attrs[k] == v
        for k, v in [("standard_name", S.latitude), ("units", "degrees_north")]:
            assert da.latitude.attrs[k] == v
        assert da.forecast_reference_time.attrs["standard_name"] == S.forecast_reference_time
        assert da.time.attrs["standard_name"] == S.time

    return check


@fixture
def c(config_data, fakefs, gen_config):
    return gen_config(config_data, fakefs)


@fixture
def c_real_fs(config_data, gen_config, tmp_path):
    return gen_config(config_data, tmp_path)


@fixture
def config_data():
    return {
        S.baseline: {
            S.name: "HRRR",
            S.url: "https://some.url/{{ yyyymmdd }}/{{ hh }}/{{ '%02d' % fh }}/a.grib2",
        },
        S.cycles: {
            S.start: "2024-12-19T18:00:00",
            S.step: "12:00:00",
            S.stop: "2024-12-20T06:00:00",
        },
        S.forecast: {
            S.coords: {
                S.latitude: "latitude",
                S.level: "level",
                S.longitude: "longitude",
                S.time: {
                    S.inittime: "time",
                    S.leadtime: "lead_time",
                },
            },
            S.mask: [
                [52.61564933, 225.90452027],
                [52.61564933, 275.0],
                [21.138123, 275.0],
                [21.138123, 225.90452027],
            ],
            S.name: "Forecast",
            S.path: "/path/to/forecast-{{ yyyymmdd }}-{{ hh }}-{{ '%03d' % fh }}.nc",
            S.projection: {
                "a": 6371229,
                "b": 6371229,
                "lat_0": 38.5,
                "lat_1": 38.5,
                "lat_2": 38.5,
                "lon_0": 262.5,
                S.proj: "lcc",
            },
        },
        S.leadtimes: {
            S.start: "00:00:00",
            S.step: "06:00:00",
            S.stop: "12:00:00",
        },
        S.paths: {
            S.grids: {
                S.baseline: "/path/to/grids/baseline",
                S.forecast: "/path/to/grids/forecast",
                S.truth: "/path/to/grids/truth",
            },
            S.obs: "/path/to/obs",
            S.run: "/path/to/run",
        },
        S.regrid: {
            S.method: "NEAREST",
            S.to: "forecast",
        },
        S.truth: {
            S.name: "GFS",
            S.type: "grid",
            S.url: "https://some.url/{{ yyyymmdd }}/{{ hh }}/{{ '%02d' % fh }}/a.grib2",
        },
        S.variables: {
            NOAA.HGT: {
                S.level_type: "isobaricInhPa",
                S.levels: [900],
                S.name: "gh",
            },
            NOAA.REFC: {
                S.level_type: "atmosphere",
                S.name: "refc",
            },
            NOAA.SPFH: {
                S.level_type: "isobaricInhPa",
                S.levels: [900, 1000],
                S.name: "q",
            },
            NOAA.T2M: {
                S.level_type: "heightAboveGround",
                S.levels: [2],
                S.name: "2t",
            },
        },
    }


@fixture
def da_with_leadtime() -> xr.DataArray:
    one = np.array([1], dtype="float32")
    return xr.DataArray(
        name=NOAA.HGT,
        data=one.reshape((1, 1, 1, 1, 1)),
        dims=["latitude", "longitude", "level", "time", "lead_time"],
        coords=dict(
            latitude=(["latitude", "longitude"], one.reshape((1, 1))),
            longitude=(["latitude", "longitude"], one.reshape((1, 1))),
            level=(["level"], np.array([900], dtype="float32")),
            time=np.array([0], dtype="datetime64[ns]"),
            lead_time=np.array([0], dtype="timedelta64[ns]"),
        ),
    )


@fixture
def da_with_validtime() -> xr.DataArray:
    one = np.array([1], dtype="float32")
    return xr.DataArray(
        name=NOAA.HGT,
        data=one.reshape((1, 1, 1, 1, 1)),
        dims=["latitude", "longitude", "level", "time", "validtime"],
        coords=dict(
            latitude=(["latitude", "longitude"], one.reshape((1, 1))),
            longitude=(["latitude", "longitude"], one.reshape((1, 1))),
            level=(["level"], np.array([900], dtype="float32")),
            time=np.array([0], dtype="datetime64[ns]"),
            validtime=np.array([0], dtype="datetime64[ns]"),
        ),
    )


@fixture
def fakefs(fs):
    return Path(fs.create_dir("/test").path)


@fixture
def gen_config():
    def gen_config(config_data, rootpath) -> Config:
        dirs = (
            f"{S.grids}/{S.baseline}",
            f"{S.grids}/{S.forecast}",
            f"{S.grids}/{S.truth}",
            S.obs,
            S.run,
        )
        grids_baseline, grids_forecast, grids_truth, obs, run = [str(rootpath / x) for x in dirs]
        for x in grids_truth, grids_forecast, obs, run:
            Path(x).mkdir(parents=True)
        return Config(
            {
                **config_data,
                S.paths: {
                    S.grids: {
                        S.baseline: grids_baseline,
                        S.forecast: grids_forecast,
                        S.truth: grids_truth,
                    },
                    S.obs: obs,
                    S.run: run,
                },
            }
        )

    return gen_config


@fixture
def logged(caplog):
    def logged(s: str):
        found = any(re.match(rf"^.*{s}.*$", message) for message in caplog.messages)
        caplog.clear()
        return found

    return logged


@fixture
def node():
    return Mock(ready=True, spec=Node)


@fixture
def tc(da_with_leadtime):
    cycle = datetime.fromtimestamp(int(da_with_leadtime.time.values[0]), tz=timezone.utc)
    leadtime = timedelta(hours=int(da_with_leadtime.lead_time.values[0]))
    return times.TimeCoords(cycle=cycle, leadtime=leadtime)


@fixture
def tidy():
    return lambda text: dedent(text).strip()


@fixture
def utc():
    def utc(*args, **kwargs) -> datetime:
        # See https://github.com/python/mypy/issues/6799
        dt = datetime(*args, **kwargs, tzinfo=timezone.utc)  # type: ignore[misc]
        return dt.replace(tzinfo=None)

    return utc
