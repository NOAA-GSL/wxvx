import re
from datetime import datetime, timedelta
from pathlib import Path

from pytest import fixture, raises

from wxvx import types

# Fixtures


@fixture
def baseline(config_data):
    return types.Baseline(**config_data["baseline"])


@fixture
def coords(config_data):
    return types.Coords(**config_data["forecast"]["coords"])


@fixture
def cycles(config_data):
    return types.Cycles(raw=config_data["cycles"])


@fixture
def forecast(config_data):
    return types.Forecast(**config_data["forecast"])


@fixture
def leadtimes(config_data):
    return types.Leadtimes(raw=config_data["leadtimes"])


@fixture
def paths(config_data):
    return types.Paths(
        grids_baseline=Path(config_data["paths"]["grids"]["baseline"]),
        grids_forecast=Path(config_data["paths"]["grids"]["forecast"]),
        obs=Path(config_data["paths"]["obs"]),
        run=Path(config_data["paths"]["run"]),
    )


@fixture
def regrid(config_data):
    return types.Regrid(**config_data["regrid"])


@fixture
def time(config_data):
    return types.Time(**config_data["forecast"]["coords"]["time"])


# Tests


def test_types_Baseline(baseline, config_data):
    obj = baseline
    assert obj.name == "GFS"
    assert obj.url == "https://some.url/{{ yyyymmdd }}/{{ hh }}/{{ '%02d' % fh }}/a.grib2"
    cfg = config_data["baseline"]
    other1 = types.Baseline(**cfg)
    assert obj == other1
    other2 = types.Baseline(**{**cfg, "name": "foo"})
    assert obj != other2


def test_types_Config(baseline, config_data, cycles, forecast, leadtimes, paths, regrid):
    obj = types.Config(raw=config_data)
    assert hash(obj)
    assert obj.baseline == baseline
    assert obj.cycles == cycles
    assert obj.forecast == forecast
    assert obj.leadtimes == leadtimes
    assert obj.paths == paths
    assert obj.regrid == regrid
    assert obj.variables == config_data["variables"]
    other = types.Config(raw=config_data)
    assert obj == other
    other.variables = {}
    assert obj != other
    for f in (repr, str):
        assert re.match(r"^Config(.*)$", f(obj))


def test_types_Coords(config_data, coords):
    obj = coords
    assert hash(obj)
    assert obj.latitude == "latitude"
    assert obj.level == "level"
    assert obj.longitude == "longitude"
    assert obj.time.inittime == "time"
    assert obj.time.leadtime == "lead_time"
    cfg = config_data["forecast"]["coords"]
    other1 = types.Coords(**cfg)
    assert obj == other1
    other2 = types.Coords(**{**cfg, "latitude": "lat"})
    assert obj != other2


def test_types_Cycles():
    ts1, ts2, ts3, td = "2024-06-04T00", "2024-06-04T06", "2024-06-04T12", "6"
    ts2dt = lambda s: datetime.fromisoformat(s)
    expected = [ts2dt(x) for x in (ts1, ts2, ts3)]
    x1 = types.Cycles(raw=[ts1, ts2, ts3])
    x2 = types.Cycles(raw={"start": ts1, "step": td, "stop": ts3})
    x3 = types.Cycles(raw={"start": ts1, "step": int(td), "stop": ts3})
    assert x1.values == expected
    assert types.Cycles(raw=[ts2, ts3, ts1]).values == expected  # order invariant
    assert types.Cycles(raw=[ts2dt(ts1), ts2dt(ts2), ts2dt(ts3)]).values == expected
    assert types.Cycles(raw=[ts1, ts2dt(ts2), ts3]).values == expected  # mixed types ok
    assert x2.values == expected
    assert x3.values == expected
    assert x1 == x2 == x3
    assert x1 == types.Cycles(raw=[ts1, ts2, ts3])
    assert x1 != types.Cycles(raw=["1970-01-01T00"])
    assert str(x1) == repr(x1)
    assert repr(x1) == "Cycles(['%s', '%s', '%s'])" % (ts1, ts2, ts3)
    assert repr(x2) == "Cycles({'start': '%s', 'step': '%s', 'stop': '%s'})" % (ts1, td, ts3)
    assert repr(x3) == "Cycles({'start': '%s', 'step': %s, 'stop': '%s'})" % (ts1, td, ts3)


def test_types_Forecast(config_data, forecast):
    obj = forecast
    assert hash(obj)
    assert obj.coords.latitude == "latitude"
    assert obj.coords.level == "level"
    assert obj.coords.longitude == "longitude"
    assert obj.coords.time.inittime == "time"
    assert obj.coords.time.leadtime == "lead_time"
    assert obj.name == "Forecast"
    assert obj.path == "/path/to/forecast-{{ yyyymmdd }}-{{ hh }}-{{ '%03d' % fh }}.nc"
    cfg = config_data["forecast"]
    other1 = types.Forecast(**cfg)
    assert obj == other1
    other2 = types.Forecast(**{**cfg, "name": "foo"})
    assert obj != other2
    cfg_no_proj = deepcopy(cfg)
    del cfg_no_proj.pop["projection"]
    default = types.Forecast(**cfg_no_proj)
    assert default.projection == {"proj": "latlon"}


def test_types_Leadtimes():
    lt1, lt2, lt3, td = "3", "6", "9", "3"
    expected = [timedelta(hours=int(x)) for x in (lt1, lt2, lt3)]
    x1 = types.Leadtimes(raw=[lt1, lt2, lt3])
    x2 = types.Leadtimes(raw={"start": lt1, "step": td, "stop": lt3})
    x3 = types.Leadtimes(raw={"start": int(lt1), "step": int(td), "stop": int(lt3)})
    assert x1.values == expected
    assert types.Leadtimes(raw=[lt2, lt3, lt1]).values == expected  # order invariant
    assert types.Leadtimes(raw=[int(lt1), int(lt2), int(lt3)]).values == expected
    assert types.Leadtimes(raw=[lt1, int(lt2), lt3]).values == expected  # mixed types ok
    assert x2.values == expected
    assert x3.values == expected
    assert x1 == x2 == x3
    assert x1 == types.Leadtimes(raw=[lt1, lt2, lt3])
    assert x1 != types.Leadtimes(raw=[0])
    assert str(x1) == repr(x1)
    assert repr(x1) == "Leadtimes(['%s', '%s', '%s'])" % (lt1, lt2, lt3)
    assert repr(x2) == "Leadtimes({'start': '%s', 'step': '%s', 'stop': '%s'})" % (lt1, td, lt3)
    assert repr(x3) == "Leadtimes({'start': %s, 'step': %s, 'stop': %s})" % (lt1, td, lt3)
    assert (
        types.Leadtimes(raw=["2:60", "5:59:60", "0:0:32400"]).values == expected
    )  # but why would you?
    assert types.Leadtimes(raw=["0:360", "0:480:3600", 3]).values == expected  # order invariant


def test_types_Paths(paths, config_data):
    obj = paths
    assert obj.grids_baseline == Path(config_data["paths"]["grids"]["baseline"])
    assert obj.grids_forecast == Path(config_data["paths"]["grids"]["forecast"])
    assert obj.run == Path(config_data["paths"]["run"])
    cfg = {
        "grids_baseline": Path(config_data["paths"]["grids"]["baseline"]),
        "grids_forecast": Path(config_data["paths"]["grids"]["forecast"]),
        "obs": Path(config_data["paths"]["obs"]),
        "run": Path(config_data["paths"]["run"]),
    }
    other1 = types.Paths(**cfg)
    assert obj == other1
    cfg["run"] = Path("/other/path")
    other2 = types.Paths(**cfg)
    assert obj != other2


def test_types_Regrid(regrid, config_data):
    obj = regrid
    assert obj.method == "NEAREST"
    assert obj.to == "FCST"
    cfg = config_data["regrid"]
    other1 = types.Regrid(**cfg)
    assert obj == other1
    other2 = types.Regrid(**{**cfg, "to": "baseline"})
    assert obj != other2
    assert other2.to == "OBS"


def test_types_Time(config_data, time):
    obj = time
    assert hash(obj)
    assert obj.inittime == "time"
    assert obj.leadtime == "lead_time"
    cfg = config_data["forecast"]["coords"]["time"]
    other1 = types.Time(**cfg)
    assert obj == other1
    other2 = types.Time(**{**cfg, "inittime": "foo"})
    assert obj != other2


def test_types_VarMeta():
    def fails(k, v):
        with raises(AssertionError):
            types.VarMeta(**{**kwargs, k: type(v)()})

    kwargs: dict = dict(
        cat_thresh=[">=20", ">=30", ">=40"],
        cf_standard_name="unknown",
        cnt_thresh=[">15"],
        description="Composite Reflectivity",
        level_type="atmosphere",
        met_stats=["FSS", "PODY"],
        name="refc",
        nbrhd_shape="CIRCLE",
        nbrhd_width=[3, 5, 11],
        units="dBZ",
    )
    x = types.VarMeta(**kwargs)
    for k, v in kwargs.items():
        assert getattr(x, k) == v
    # Must not be empty:
    for k, v in kwargs.items():
        fails(k, type(v)())
    # Must not have None values:
    for k in ["cf_standard_name", "description", "level_type", "met_stats", "name", "units"]:
        fails(k, None)
    # Must not have unrecognized values:
    for k, v in [
        ("level_type", "intergalactic"),
        ("met_stats", ["XYZ"]),
        ("nbrhd_shape", "TRIANGLE"),
    ]:
        fails(k, v)
