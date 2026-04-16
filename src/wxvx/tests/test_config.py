import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

from pytest import fixture, mark, raises

from wxvx import config, types
from wxvx.strings import MET, S
from wxvx.util import DataFormat, WXVXError


@fixture
def baseline(config_data):
    return config.Baseline(**config_data[S.baseline])


@fixture
def coords(config_data):
    return config.Coords(**config_data[S.forecast][S.coords])


@fixture
def cycles(config_data):
    return config.Cycles(raw=config_data[S.cycles])


@fixture
def forecast(config_data):
    return config.Forecast(**config_data[S.forecast])


@fixture
def leadtimes(config_data):
    return config.Leadtimes(raw=config_data[S.leadtimes])


@fixture
def paths(config_data):
    return config.Paths(
        grids_baseline=Path(config_data[S.paths][S.grids][S.baseline]),
        grids_forecast=Path(config_data[S.paths][S.grids][S.forecast]),
        grids_truth=Path(config_data[S.paths][S.grids][S.truth]),
        obs=Path(config_data[S.paths][S.obs]),
        run=Path(config_data[S.paths][S.run]),
    )


@fixture
def regrid(config_data):
    return config.Regrid(**config_data[S.regrid])


@fixture
def time(config_data):
    return config.Time(**config_data[S.forecast][S.coords][S.time])


@fixture
def truth(config_data):
    return config.Truth(**config_data[S.truth])


def test_config_Baseline(baseline, config_data):
    obj = baseline
    assert obj.name == S.HRRR
    assert obj.url == "https://some.url/{{ yyyymmdd }}/{{ hh }}/{{ '%02d' % fh }}/a.grib2"
    cfg = config_data[S.baseline]
    assert obj == config.Baseline(**cfg)
    assert obj != config.Baseline(**{**cfg, S.name: S.GFS})
    assert obj != config.Baseline(**{**cfg, S.url: "bar"})
    assert config.Baseline(name=S.truth)
    with raises(AssertionError):
        config.Baseline(name=S.truth, url="should-not-be-defined")
    with raises(WXVXError) as e:
        config.Baseline(name="anything-else")
    assert str(e.value).startswith("Set baseline.name to one of:")


@mark.parametrize(S.baseline, [True, False])
def test_config_Config(baseline, config_data, cycles, forecast, leadtimes, paths, regrid, truth):
    if not baseline:
        del config_data[S.baseline]
        del config_data[S.paths][S.grids][S.baseline]
        paths = replace(paths, grids_baseline=None)
    obj = config.Config(raw=config_data)
    assert hash(obj)
    assert obj.cycles == cycles
    assert obj.forecast == forecast
    assert obj.leadtimes == leadtimes
    assert obj.paths == paths
    assert obj.regrid == regrid
    assert obj.truth == truth
    assert obj.variables == config_data[S.variables]
    other = config.Config(raw=config_data)
    assert obj == other
    other.variables = {}
    assert obj != other
    for f in (repr, str):
        assert re.match(r"^Config(.*)$", f(obj))


def test_config_Config__bad_baseline_name_vs_truth_type(config_data):
    del config_data[S.baseline][S.url]
    config_data[S.baseline][S.name] = S.truth
    config_data[S.truth][S.type] = types.TruthType.POINT
    config_data[S.truth][S.name] = S.PREPBUFR
    with raises(WXVXError) as e:
        config.Config(raw=config_data)
    assert str(e.value) == "Values baseline.name 'truth' and truth.type 'point' are incompatible"


def test_config_Config__bad_ncdiffs_vs_truth_type(config_data):
    config_data[S.ncdiffs] = True
    config_data[S.truth][S.type] = types.TruthType.POINT
    config_data[S.truth][S.name] = S.PREPBUFR
    with raises(WXVXError) as e:
        config.Config(raw=config_data)
    assert str(e.value) == "Option ncdiffs must be false (or omitted) when truth.type is 'point'"


def test_config_Config__bad_paths_grids_baseline(config_data):
    config_data[S.baseline][S.name] = S.HRRR
    del config_data[S.paths][S.grids][S.baseline]
    with raises(WXVXError) as e:
        config.Config(raw=config_data)
    assert str(e.value) == "Specify paths.grids.baseline when baseline.name is not 'truth'"


def test_config_Config__bad_paths_grids_truth(config_data):
    config_data[S.truth][S.type] = S.grid
    del config_data[S.paths][S.grids][S.truth]
    with raises(WXVXError) as e:
        config.Config(raw=config_data)
    assert str(e.value) == "Specify paths.grids.truth when truth.type is 'grid'"


def test_config_Config__bad_paths_obs(config_data):
    config_data[S.truth][S.type] = S.point
    config_data[S.truth][S.name] = S.PREPBUFR
    del config_data[S.paths][S.obs]
    with raises(WXVXError) as e:
        config.Config(raw=config_data)
    assert str(e.value) == "Specify paths.obs when truth.type is 'point'"


def test_config_Config__bad_regrid_to(config_data):
    config_data[S.regrid][S.to] = S.truth
    with raises(WXVXError) as e:
        config.Config(raw=config_data)
    assert str(e.value) == "Cannot regrid to observations per regrid.to config value"


@mark.parametrize(
    (S.baseline, S.forecast, S.truth),
    [(S.GFS, S.GFS, S.HRRR), (S.GFS, S.HRRR, S.GFS), (S.HRRR, S.GFS, S.GFS)],
)
def test_config_Config__bad_duplicate_names(baseline, config_data, forecast, truth):
    config_data[S.baseline][S.name] = baseline
    config_data[S.forecast][S.name] = forecast
    config_data[S.truth][S.name] = truth
    with raises(WXVXError) as e:
        config.Config(raw=config_data)
    assert str(e.value) == "Distinct baseline.name (if set), forecast.name, and truth.name required"


@mark.parametrize("ignore", [True, False])
def test_config_Config__paths_grids_baseline_ignored(config_data, ignore, logged):
    config_data[S.baseline][S.name] = S.truth
    del config_data[S.baseline][S.url]
    if ignore:
        config_data[S.paths][S.grids][S.baseline] = "/some/path"
    else:
        del config_data[S.paths][S.grids][S.baseline]
    config.Config(raw=config_data)
    warned = logged("Ignoring paths.grids.baseline when baseline.name is 'truth'")
    assert warned if ignore else not warned


def test_config_Coords(config_data, coords):
    obj = coords
    assert hash(obj)
    assert obj.latitude == "latitude"
    assert obj.level == "level"
    assert obj.longitude == "longitude"
    assert obj.time.inittime == "time"
    assert obj.time.leadtime == "lead_time"
    cfg = config_data[S.forecast][S.coords]
    other1 = config.Coords(**{**cfg, S.time: config.Time(inittime="time", leadtime="lead_time")})
    assert obj == other1
    other2 = config.Coords(**{**cfg, S.latitude: "lat"})
    assert obj != other2


def test_config_Cycles():
    ts1, ts2, ts3, td = "2024-06-04T00", "2024-06-04T06", "2024-06-04T12", "6"
    ts2dt = lambda s: datetime.fromisoformat(s)
    expected = [ts2dt(x) for x in (ts1, ts2, ts3)]
    x1 = config.Cycles(raw=[ts1, ts2, ts3])
    x2 = config.Cycles(raw={S.start: ts1, S.step: td, S.stop: ts3})
    x3 = config.Cycles(raw={S.start: ts1, S.step: int(td), S.stop: ts3})
    assert x1.values == expected
    assert config.Cycles(raw=[ts2, ts3, ts1]).values == expected
    assert config.Cycles(raw=[ts2dt(ts1), ts2dt(ts2), ts2dt(ts3)]).values == expected
    assert config.Cycles(raw=[ts1, ts2dt(ts2), ts3]).values == expected
    assert x2.values == expected
    assert x3.values == expected
    assert x1 == x2 == x3
    assert x1 == config.Cycles(raw=[ts1, ts2, ts3])
    assert x1 != config.Cycles(raw=["1970-01-01T00"])
    assert str(x1) == repr(x1)
    assert repr(x1) == "Cycles(['%s', '%s', '%s'])" % (ts1, ts2, ts3)
    assert repr(x2) == "Cycles({'start': '%s', 'step': '%s', 'stop': '%s'})" % (ts1, td, ts3)
    assert repr(x3) == "Cycles({'start': '%s', 'step': %s, 'stop': '%s'})" % (ts1, td, ts3)


def test_config_Forecast(config_data, forecast):
    obj = forecast
    assert hash(obj)
    assert obj.coords.latitude == "latitude"
    assert obj.coords.level == "level"
    assert obj.coords.longitude == "longitude"
    assert obj.coords.time.inittime == "time"
    assert obj.coords.time.leadtime == "lead_time"
    assert obj.format is None
    assert obj.name == "Forecast Model"
    assert obj.path == "/path/to/forecast-{{ yyyymmdd }}-{{ hh }}-{{ '%03d' % fh }}.nc"
    cfg = config_data[S.forecast]
    other1 = config.Forecast(**cfg)
    assert obj == other1
    other2 = config.Forecast(**{**cfg, S.name: "foo"})
    assert obj != other2
    cfg_no_proj = deepcopy(cfg)
    del cfg_no_proj[S.projection]
    default = config.Forecast(**cfg_no_proj)
    assert default.projection == {S.proj: S.latlon}
    for k, v in {
        "grib": DataFormat.GRIB,
        "netcdf": DataFormat.NETCDF,
        "zarr": DataFormat.ZARR,
        None: None,
    }.items():
        obj = config.Forecast(**{**config_data[S.forecast], "format": k})
        assert obj.format == v


def test_config_Leadtimes():
    lt1, lt2, lt3, td = "3", "6", "9", "3"
    expected = [timedelta(hours=int(x)) for x in (lt1, lt2, lt3)]
    x1 = config.Leadtimes(raw=[lt1, lt2, lt3])
    x2 = config.Leadtimes(raw={S.start: lt1, S.step: td, S.stop: lt3})
    x3 = config.Leadtimes(raw={S.start: int(lt1), S.step: int(td), S.stop: int(lt3)})
    assert x1.values == expected
    assert config.Leadtimes(raw=[lt2, lt3, lt1]).values == expected
    assert config.Leadtimes(raw=[int(lt1), int(lt2), int(lt3)]).values == expected
    assert config.Leadtimes(raw=[lt1, int(lt2), lt3]).values == expected
    assert x2.values == expected
    assert x3.values == expected
    assert x1 == x2 == x3
    assert x1 == config.Leadtimes(raw=[lt1, lt2, lt3])
    assert x1 != config.Leadtimes(raw=[0])
    assert str(x1) == repr(x1)
    assert repr(x1) == "Leadtimes(['%s', '%s', '%s'])" % (lt1, lt2, lt3)
    assert repr(x2) == "Leadtimes({'start': '%s', 'step': '%s', 'stop': '%s'})" % (lt1, td, lt3)
    assert repr(x3) == "Leadtimes({'start': %s, 'step': %s, 'stop': %s})" % (lt1, td, lt3)
    assert config.Leadtimes(raw=["2:60", "5:59:60", "0:0:32400"]).values == expected
    assert config.Leadtimes(raw=["0:360", "0:480:3600", 3]).values == expected


def test_config_Paths(paths, config_data):
    obj = paths
    assert obj.grids_baseline == Path(config_data[S.paths][S.grids][S.baseline])
    assert obj.grids_forecast == Path(config_data[S.paths][S.grids][S.forecast])
    assert obj.grids_truth == Path(config_data[S.paths][S.grids][S.truth])
    assert obj.run == Path(config_data[S.paths][S.run])
    cfg = {
        S.grids_baseline: Path(config_data[S.paths][S.grids][S.baseline]),
        S.grids_forecast: Path(config_data[S.paths][S.grids][S.forecast]),
        S.grids_truth: Path(config_data[S.paths][S.grids][S.truth]),
        S.obs: Path(config_data[S.paths][S.obs]),
        S.run: Path(config_data[S.paths][S.run]),
    }
    other1 = config.Paths(**cfg)
    assert obj == other1
    cfg[S.run] = Path("/other/path")
    other2 = config.Paths(**cfg)
    assert obj != other2


def test_config_Regrid(regrid, config_data):
    obj = regrid
    assert obj.method == MET.NEAREST
    assert str(obj.to) == types.ToGridVal.FCST.name
    cfg = config_data[S.regrid]
    other1 = config.Regrid(**cfg)
    assert obj == other1
    other2 = config.Regrid(**{**cfg, S.to: S.truth})
    assert obj != other2
    assert str(other2.to) == types.ToGridVal.OBS.name


def test_config_Time(config_data, time):
    obj = time
    assert hash(obj)
    assert obj.inittime == "time"
    assert obj.leadtime == "lead_time"
    cfg = config_data[S.forecast][S.coords][S.time]
    other1 = config.Time(**cfg)
    assert obj == other1
    other2 = config.Time(**{**cfg, S.inittime: "foo"})
    assert obj != other2


def test_config_ToGrid():
    for f in [repr, str]:
        f = cast(Callable, f)
        assert f(config.ToGrid(val=S.forecast)) == types.ToGridVal.FCST.name
        assert f(config.ToGrid(val=S.truth)) == types.ToGridVal.OBS.name
        assert f(config.ToGrid(val="G104")) == "G104"
    assert hash(config.ToGrid(val="G104")) == hash(config.ToGrid(val="G104"))
    assert config.ToGrid(val="G104") == config.ToGrid(val="G104")
    assert config.ToGrid(val=S.forecast) != config.ToGrid(val=S.truth)


@mark.parametrize("truth_type", [S.grid, types.TruthType.GRID])
def test_config_Truth(config_data, truth, truth_type):
    obj = truth
    assert obj.name == S.GFS
    assert obj.url == "https://some.url/{{ yyyymmdd }}/{{ hh }}/{{ '%02d' % fh }}/a.grib2"
    cfg = config_data[S.truth]
    cfg[S.type] = truth_type
    other1 = config.Truth(**cfg)
    assert obj == other1
    other2 = config.Truth(**{**cfg, S.name: S.HRRR})
    assert obj != other2


@mark.parametrize(
    ("truth_name", "truth_type"),
    [
        *[(S.GFS, x) for x in (types.TruthType.POINT, S.point)],
        *[(S.PREPBUFR, x) for x in (types.TruthType.GRID, S.grid)],
        ("foo", types.TruthType.GRID),
    ],
)
def test_config_Truth__bad_name(truth_name, truth_type):
    with raises(WXVXError) as e:
        config.Truth(name=truth_name, type=truth_type, url="http://some.url")
    if truth_name == S.GFS:
        msg = "When truth.type is 'point' set truth.name to:"
    elif truth_name == S.PREPBUFR:
        msg = "When truth.type is 'grid' set truth.name to:"
    else:
        msg = "Set truth.name to one of:"
    assert str(e.value).startswith(msg)
