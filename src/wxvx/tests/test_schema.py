"""
Granular tests of config.schema.
"""

import json
from collections.abc import Callable
from typing import Any

from pyfakefs.fake_filesystem import FakeFilesystem
from uwtools.api.config import validate

from wxvx.strings import S
from wxvx.tests.support import with_del, with_set
from wxvx.util import resource_path

# Tests


def test_schema(logged, config_data, fs):
    ok = validator(fs)
    config = config_data
    # Basic correctness:
    assert ok(config)
    # Certain top-level keys are required:
    for key in [
        S.cycles,
        S.forecast,
        S.leadtimes,
        S.paths,
        S.truth,
        S.variables,
    ]:
        assert not ok(with_del(config, key))
        assert logged(f"'{key}' is a required property")
    # Additional keys are not allowed:
    assert not ok(with_set(config, 42, "n"))
    assert logged("'n' was unexpected")
    # Some keys have object values:
    for key in [S.cycles, S.leadtimes]:
        assert not ok(with_set(config, None, key))
        assert logged("is not valid")
    for key in [S.paths, S.variables]:
        assert not ok(with_set(config, None, key))
        assert logged("None is not of type 'object'")


def test_schema_defs_datetime(fs):
    ok = validator(fs, "$defs", "datetime")
    assert ok("2025-05-27T14:13:27")
    assert not ok("2025-05-27 14:13:27")
    assert not ok("25-05-27T14:13:27")


def test_schema_defs_timedelta(fs):
    ok = validator(fs, "$defs", "timedelta")
    # Value may be hh[:mm[:ss]]:
    assert ok("14:13:27")
    assert ok("14:13")
    assert ok("14")
    # The following three timedeltas are all the same:
    assert ok("2:0:0")
    assert ok("0:120:0")
    assert ok("0:0:7200")


def test_schema_baseline(logged, config_data, fs):
    ok = validator(fs, S.properties, S.baseline)
    config = config_data[S.baseline]
    # Basic correctness:
    assert ok(config)
    # The "name" property's value can be "truth", in which case "url" must not be set:
    assert not ok(with_set(config, S.truth, S.name))
    assert ok(with_del(with_set(config, S.truth, S.name), "url"))
    # If name is not "truth", URL must be specified:
    assert not ok(with_del(with_set(config, S.GFS, S.name), "url"))
    assert logged("'url' is a required property")


def test_schema_cycles(logged, config_data, fs, utc):
    ok = validator(fs, S.properties, S.cycles)
    config = config_data[S.cycles]
    # Basic correctness:
    assert ok(config)
    # Certain top-level keys are required:
    for key in ["start", "step", "stop"]:
        assert not ok(with_del(config, key))
        assert logged("is not valid")
    # Additional keys are not allowed:
    assert not ok(with_set(config, 42, "n"))
    assert logged("is not valid")
    # Some keys must match a certain pattern:
    for key in ["start", "step", "stop"]:
        assert not ok(with_set(config, "foo", key))
        assert logged("is not valid")
    # Alternate short form:
    assert ok(["2025-06-03T03:00:00", "2025-06-03T06:00:00", "2025-06-03T12:00:00"])
    assert ok([utc(2025, 6, 3, 3), utc(2025, 6, 3, 6), utc(2025, 6, 3, 12)])


def test_schema_forecast(logged, config_data, fs):
    ok = validator(fs, S.properties, S.forecast)
    config = config_data[S.forecast]
    # Basic correctness:
    assert ok(config)
    # Certain top-level keys are required:
    for key in [S.name, "path"]:
        assert not ok(with_del(config, key))
        assert logged(f"'{key}' is a required property")
    # Additional keys are not allowed:
    assert not ok(with_set(config, 42, "n"))
    assert logged("'n' was unexpected")
    # Some keys have object values:
    for key in [S.coords, "projection"]:
        assert not ok(with_set(config, None, key))
        assert logged("None is not of type 'object'")
    # Some keys have string values:
    for key in [S.name, "path"]:
        assert not ok(with_set(config, None, key))
        assert logged("None is not of type 'string'")
    # Some keys are optional:
    for key in ["mask"]:
        assert ok(with_del(config, key))


def test_schema_forecast_coords(logged, config_data, fs):
    ok = validator(fs, S.properties, S.forecast, S.properties, S.coords)
    config = config_data[S.forecast][S.coords]
    assert ok(config)
    # All keys are required:
    for key in ["latitude", S.level, "longitude", S.time]:
        assert not ok(with_del(config, key))
        assert logged(f"'{key}' is a required property")
    # Some keys must have string values:
    for key in ["latitude", S.level, "longitude"]:
        assert not ok(with_set(config, None, key))
        assert logged("None is not of type 'string'")


def test_schema_forecast_coords_time(logged, config_data, fs):
    ok = validator(fs, S.properties, S.forecast, S.properties, S.coords, S.properties, S.time)
    # Basic correctness of fixture:
    config = config_data[S.forecast][S.coords][S.time]
    assert ok(config)
    obj = {"inittime": "a", "leadtime": "b", "validtime": "c"}
    # Overspecified (leadtime and validtime are mutually exclusive):
    assert not ok(obj)
    # OK:
    for key in ("leadtime", "validtime"):
        assert ok(with_del(obj, key))
    # All values must be strings:
    for x in [
        with_set(obj, None, "inittime"),
        with_set(with_del(obj, "leadtime"), None, "validtime"),
        with_set(with_del(obj, "validtime"), None, "leadtime"),
    ]:
        assert not ok(x)
        assert logged("is not valid")


def test_schema_forecast_mask(logged, config_data, fs):
    ok = validator(fs, S.properties, S.forecast, S.properties, "mask")
    config = config_data[S.forecast]["mask"]
    assert ok(config)
    assert not ok("string")
    assert logged("'string' is not of type 'array'")


def test_schema_forecast_projection(logged, config_data, fs):
    ok = validator(fs, S.properties, S.forecast, S.properties, "projection")
    config = config_data[S.forecast]["projection"]
    # Basic correctness:
    assert ok(config)
    # Certain top-level keys are required:
    for key in ["proj"]:
        assert not ok(with_del(config, key))
        assert logged("'proj' is a required property")
    # Additional keys are not allowed:
    assert not ok(with_set(config, 42, "foo"))
    assert logged("'foo' was unexpected")
    # Some keys have enum values:
    for key in ["proj"]:
        assert not ok(with_set(config, "foo", key))
        assert logged(r"'foo' is not one of \['latlon', 'lcc'\]")
    # For proj latlon:
    config_latlon = {"proj": "latlon"}
    assert ok(config_latlon)
    assert not ok(with_set(config_latlon, 42, "foo"))
    assert logged("'foo' was unexpected")
    # For proj lcc (default in fixture):
    assert config["proj"] == "lcc"
    for key in ["a", "b", "lat_0", "lat_1", "lat_2", "lon_0"]:
        assert not ok(with_del(config, key))
        assert logged(f"'{key}' is a required property")
        assert not ok(with_set(config, None, key))
        assert logged("None is not of type 'number'")


def test_schema_leadtimes(logged, config_data, fs):
    ok = validator(fs, S.properties, S.leadtimes)
    config = config_data[S.leadtimes]
    # Basic correctness:
    assert ok(config)
    # Certain top-level keys are required:
    for key in ["start", "step", "stop"]:
        assert not ok(with_del(config, key))
        assert logged("is not valid")
    # Additional keys are not allowed:
    assert not ok(with_set(config, 42, "n"))
    assert logged("is not valid")
    # Some keys must match a certain pattern:
    for key in ["start", "step", "stop"]:
        assert not ok(with_set(config, "foo", key))
        assert logged("is not valid")
    # Alternate short form:
    assert ok(["01:00:00", "02:00:00", "03:00:00", "12:00:00", "24:00:00"])
    assert ok([1, 2, 3, 12, 24])


def test_schema_meta(config_data, fs, logged):
    ok = validator(fs)
    config = config_data
    # The optional top-level "meta" key must have a object value:
    assert ok(with_set(config, {}, "meta"))
    assert not ok(with_set(config, [], "meta"))
    assert logged("is not of type 'object'")


def test_schema_paths(config_data, fs, logged):
    ok = validator(fs, S.properties, S.paths)
    config = config_data[S.paths]
    # Basic correctness:
    assert ok(config)
    # Certain top-level keys are required:
    for key in [S.run]:
        assert not ok(with_del(config, key))
        assert logged(f"'{key}' is a required property")
    # Additional keys are not allowed:
    assert not ok(with_set(config, 42, "n"))
    # Some keys have object values:
    for key in [S.grids]:
        assert not ok(with_set(config, None, key))
        assert logged("None is not of type 'object'")
    # Some keys have string values:
    for key in [S.run]:
        assert not ok(with_set(config, None, key))
        assert logged("None is not of type 'string'")
    # Either grids.truth or obs is required:
    assert ok(with_del(config, S.grids, S.truth))
    assert ok(with_del(config, S.obs))
    assert not ok(with_del(with_del(config, S.grids, S.truth), S.obs))


def test_schema_paths_grids(config_data, fs, logged):
    ok = validator(fs, S.properties, S.paths, S.properties, S.grids)
    config = config_data[S.paths][S.grids]
    # Basic correctness:
    assert ok(config)
    # Additional keys are not allowed:
    assert not ok(with_set(config, 42, "n"))
    # Some keys have string values:
    for key in [S.forecast, S.truth]:
        assert not ok(with_set(config, None, key))
        assert logged("None is not of type 'string'")
    # Some values are required:
    for key in [S.forecast]:
        assert not ok(with_del(config, key))
        assert logged(f"'{key}' is a required property")
    # Some values are optional:
    for key in [S.baseline]:
        assert ok(with_del(config, key))


def test_schema_regrid(logged, config_data, fs):
    ok = validator(fs, S.properties, "regrid")
    config = config_data["regrid"]
    # Basic correctness:
    assert ok(config)
    # Must be an object:
    assert not ok([])
    assert logged("is not of type 'object'")
    # Must have at least one property:
    assert not ok({})
    assert logged("should be non-empty")
    # "method" must not have an expected value:
    assert not ok(with_set(config, "UNEXPECTED", "method"))
    assert logged("'UNEXPECTED' is not one of")
    # "to" must have an expected value:
    assert ok(with_set(config, "G004", "to"))
    assert not ok(with_set(config, "UNEXPECTED", "to"))
    assert logged("'UNEXPECTED' does not match")


def test_schema_truth(logged, config_data, fs):
    ok = validator(fs, S.properties, S.truth)
    config = config_data[S.truth]
    # Basic correctness:
    assert ok(config)
    # Certain top-level keys are required:
    for key in [S.name, S.type, "url"]:
        assert not ok(with_del(config, key))
        assert logged(f"'{key}' is a required property")
    # Additional keys are not allowed:
    assert not ok(with_set(config, 42, "n"))
    assert logged("'n' was unexpected")
    # Some keys have string values:
    for key in [S.name, "url"]:
        assert not ok(with_set(config, None, key))
        assert logged("None is not of type 'string'")
    # Some keys have enum values:
    for key in [S.type]:
        assert not ok(with_set(config, "foo", key))
        assert logged(r"'foo' is not one of \['grid', 'point'\]")


def test_schema_variables(logged, config_data, fs):
    ok = validator(fs, S.properties, S.variables)
    config = config_data[S.variables]
    one = config["T2M"]
    # Basic correctness:
    assert ok(config)
    # Must be an object:
    assert not ok([])
    assert logged("is not of type 'object'")
    # Array entries must have the correct keys:
    for key in (S.level_type, S.levels, S.name):
        assert not ok(with_del({"X": one}, "X", key))
        assert logged(f"'{key}' is a required property")
    # Additional keys in entries are not allowed:
    assert not ok({"X": {**one, "foo": "bar"}})
    assert logged("Additional properties are not allowed")
    # The "levels" key is required for some level types, forbidden for others:
    for level_type in ("heightAboveGround", "isobaricInhPa"):
        assert not ok({"X": {S.name: "foo", S.level_type: level_type}})
        assert logged("'levels' is a required property")
    for level_type in ("atmosphere", "surface"):
        assert not ok({"X": {S.name: "foo", S.level_type: level_type, S.levels: [1000]}})
        assert logged("should not be valid")
    # Some keys have enum values:
    for key in [S.level_type]:
        assert not ok({"X": {**one, key: None}})
        assert logged("None is not one of")
    # Some keys have string values:
    for key in [S.name]:
        assert not ok({"X": {**one, key: None}})
        assert logged("None is not of type 'string'")


# Helpers


def validator(fs: FakeFilesystem, *args: Any) -> Callable:
    """
    Returns a lambda that validates an eventual config argument.

    :param args: Keys leading to sub-schema to be used to validate config.
    """
    schema_path = resource_path("config.jsonschema")
    fs.add_real_file(schema_path)
    with schema_path.open() as f:
        schema = json.load(f)
    defs = schema.get("$defs", {})
    for arg in args:
        schema = schema[arg]
    if args and args[0] != "$defs":
        schema.update({"$defs": defs})
    schema_file = str(fs.create_file("test.schema", contents=json.dumps(schema)).path)
    return lambda c: validate(schema_file=schema_file, config_data=c)
