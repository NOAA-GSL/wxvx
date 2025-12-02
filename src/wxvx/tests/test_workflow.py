"""
Tests for wxvx.workflow.
"""

import os
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from textwrap import indent
from threading import Event
from types import SimpleNamespace as ns
from typing import cast
from unittest.mock import ANY, Mock, patch

import pandas as pd
import xarray as xr
from iotaa import Asset, Node, external
from pytest import fixture, mark, raises

from wxvx import variables, workflow
from wxvx.tests.support import with_del
from wxvx.times import gen_validtimes, tcinfo
from wxvx.types import Config, Source
from wxvx.util import DataFormat, WXVXError
from wxvx.variables import Var

TESTDATA = {
    "foo": (
        "T2M",
        2,
        [
            pd.DataFrame({"MODEL": "foo", "FCST_LEAD": [60000], "RMSE": [0.5]}),
            pd.DataFrame({"MODEL": "bar", "FCST_LEAD": [60000], "RMSE": [0.4]}),
        ],
        "RMSE",
        None,
    ),
    "bar": (
        "REFC",
        None,
        [
            pd.DataFrame(
                {"MODEL": "foo", "FCST_LEAD": [60000], "PODY": [0.5], "FCST_THRESH": ">=20"}
            ),
            pd.DataFrame(
                {"MODEL": "bar", "FCST_LEAD": [60000], "PODY": [0.4], "FCST_THRESH": ">=30"}
            ),
        ],
        "PODY",
        None,
    ),
    "baz": (
        "REFC",
        None,
        [
            pd.DataFrame(
                {
                    "MODEL": "foo",
                    "FCST_LEAD": [60000],
                    "FSS": [0.5],
                    "FCST_THRESH": ">=20",
                    "INTERP_PNTS": 9,
                }
            ),
            pd.DataFrame(
                {
                    "MODEL": "bar",
                    "FCST_LEAD": [60000],
                    "FSS": [0.4],
                    "FCST_THRESH": ">=30",
                    "INTERP_PNTS": 9,
                }
            ),
        ],
        "FSS",
        3,
    ),
}

# Task Tests


@mark.parametrize("compare", [True, False])
@mark.parametrize("fmt", [DataFormat.NETCDF, DataFormat.ZARR])
def test_workflow_grids(c, compare, fmt, ngrids, noop):
    c.truth = replace(c.truth, compare=compare)
    with (
        patch.object(workflow, "_grid_grib", noop),
        patch.object(workflow, "_grid_nc", noop),
        patch.object(workflow, "classify_data_format", return_value=fmt),
    ):
        ntypes = 3 if compare else 2  # forecast, truth, and optionally comp grids
        assert len(workflow.grids(c=c).ref) == ngrids * ntypes  # type: ignore[operator]
        assert len(workflow.grids(c=c, forecast=True, truth=True).ref) == ngrids * ntypes
        assert len(workflow.grids(c=c, forecast=False, truth=True).ref) == ngrids * (ntypes - 1)
        assert len(workflow.grids(c=c, forecast=True, truth=False).ref) == ngrids
        assert len(workflow.grids(c=c, forecast=False, truth=False).ref) == 0


@mark.parametrize("fmt", [DataFormat.NETCDF, DataFormat.ZARR])
def test_workflow_grids_forecast(c, fmt, ngrids, noop):
    with (
        patch.object(workflow, "_grid_nc", noop),
        patch.object(workflow, "classify_data_format", return_value=fmt),
    ):
        assert len(workflow.grids_forecast(c=c).ref) == ngrids


def test_workflow_grids_truth(c, ngrids, noop):
    with patch.object(workflow, "_grid_grib", noop):
        assert len(workflow.grids_truth(c=c).ref) == ngrids * 2


def test_workflow_ncobs(c, obs_info):
    c, expected = obs_info
    assert workflow.ncobs(c).ref == [x.with_suffix(".nc") for x in expected]


def test_workflow_obs(c, obs_info):
    c, expected = obs_info
    assert workflow.obs(c).ref == [x.with_suffix(".nr") for x in expected]


def test_workflow_plots(c, noop):
    with patch.object(workflow, "_plot", noop):
        node = workflow.plots(c=c)
    assert len(node.ref) == len(c.cycles.values) * sum(
        len(list(workflow._stats_and_widths(c, varname)))
        for varname, _ in workflow._varnames_and_levels(c)
    )


def test_workflow_stats(c, noop):
    with patch.object(workflow, "_statreqs", return_value=[noop()]) as _statreqs:
        node = workflow.stats(c=c)
    assert len(node.ref) == len(c.variables) + 1  # for 2x SPFH levels


@mark.parametrize("source", [Source.FORECAST, Source.TRUTH])
def test_workflow__config_grid_stat(c, source, fakefs, testvars):
    path = fakefs / "refc.config"
    assert not path.is_file()
    workflow._config_grid_stat(
        c=c,
        path=path,
        source=source,
        varname="REFC",
        var=testvars["refc"],
        prefix="foo",
        datafmt=DataFormat.GRIB,
        polyfile=None,
    )
    assert path.is_file()


def test_workflow__config_pb2nc(c, fakefs, tidy):
    path = fakefs / "pb2nc.config"
    assert not path.is_file()
    workflow._config_pb2nc(c=c, path=path)
    expected = """
    mask = {
      grid = "";
    }
    message_type = [
      "ADPSFC",
      "ADPUPA",
      "AIRCAR",
      "AIRCFT"
    ];
    obs_bufr_var = [
      "POB",
      "QOB",
      "TOB",
      "UOB",
      "VOB",
      "ZOB"
    ];
    obs_window = {
      beg = -1800;
      end = 1800;
    }
    quality_mark_thresh = 9;
    time_summary = {
      obs_var = [];
      step = 3600;
      type = [
        "min",
        "max",
        "range",
        "mean",
        "stdev",
        "median",
        "p80"
      ];
      width = 3600;
    }
    tmp_dir = "/test";
    """
    assert tidy(expected) == path.read_text().strip()


@mark.parametrize("to", ["G104", None])
def test_workflow__config_pb2nc__alt_masks(c, fakefs, tidy, to):
    path = fakefs / "pb2nc.config"
    assert not path.is_file()
    c.regrid = replace(c.regrid, to=to)
    workflow._config_pb2nc(c=c, path=path)
    expected = """
    mask = {
      grid = "%s";
    }
    """ % (to or "")
    assert tidy(expected) in path.read_text()


@mark.parametrize("fmt", [DataFormat.GRIB, DataFormat.NETCDF, DataFormat.ZARR])
def test_workflow__config_point_stat__atm(c, fakefs, fmt, testvars, tidy):
    path = fakefs / "point_stat.config"
    assert not path.is_file()
    workflow._config_point_stat(
        c=c,
        path=path,
        source=Source.FORECAST,
        varname="HGT",
        var=testvars["gh"],
        prefix="atm",
        datafmt=fmt,
    )
    expected = """
    fcst = {
      field = [
        {
    %s
        }
      ];
    }
    interp = {
      shape = SQUARE;
      type = {
        method = BILIN;
        width = 2;
      }
      vld_thresh = 1.0;
    }
    message_type = [
      "ATM"
    ];
    message_type_group_map = [
      {
        key = "ATM";
        val = "ADPUPA,AIRCAR,AIRCFT";
      },
      {
        key = "SFC";
        val = "ADPSFC";
      }
    ];
    model = "Forecast";
    obs = {
      field = [
        {
          level = [
            "P900"
          ];
          name = "HGT";
        }
      ];
    }
    obs_window = {
      beg = -1800;
      end = 1800;
    }
    output_flag = {
      cnt = BOTH;
    }
    output_prefix = "atm";
    regrid = {
      method = NEAREST;
      to_grid = FCST;
      width = 1;
    }
    tmp_dir = "/test";
    """
    fcst = tidy(fcst_field(fmt, surface=False))
    expected = tidy(expected) % respace(fcst)
    assert path.read_text().strip() == expected


@mark.parametrize("fmt", [DataFormat.GRIB, DataFormat.NETCDF, DataFormat.ZARR])
def test_workflow__config_point_stat__sfc(c, fakefs, fmt, testvars, tidy):
    path = fakefs / "point_stat.config"
    assert not path.is_file()
    workflow._config_point_stat(
        c=c,
        path=path,
        source=Source.FORECAST,
        varname="T2M",
        var=testvars["2t"],
        prefix="sfc",
        datafmt=fmt,
    )
    expected = """
    fcst = {
      field = [
        {
    %s
        }
      ];
    }
    interp = {
      shape = SQUARE;
      type = {
        method = BILIN;
        width = 2;
      }
      vld_thresh = 1.0;
    }
    message_type = [
      "SFC"
    ];
    message_type_group_map = [
      {
        key = "ATM";
        val = "ADPUPA,AIRCAR,AIRCFT";
      },
      {
        key = "SFC";
        val = "ADPSFC";
      }
    ];
    model = "Forecast";
    obs = {
      field = [
        {
          level = [
            "Z002"
          ];
          name = "TMP";
        }
      ];
    }
    obs_window = {
      beg = -900;
      end = 900;
    }
    output_flag = {
      cnt = BOTH;
    }
    output_prefix = "sfc";
    regrid = {
      method = NEAREST;
      to_grid = FCST;
      width = 1;
    }
    tmp_dir = "/test";
    """
    fcst = tidy(fcst_field(fmt, surface=True))
    expected = tidy(expected) % respace(fcst)
    assert path.read_text().strip() == expected


def test_workflow__config_point_stat__unsupported_regrid_method(c, fakefs, testvars):
    path = fakefs / "point_stat.config"
    assert not path.is_file()
    task = workflow._config_point_stat(
        c=c,
        path=path,
        source=Source.FORECAST,
        varname="geopotential",
        var=testvars["gh"],
        prefix="atm",
        datafmt=DataFormat.NETCDF,
    )
    assert not task.ready
    assert not path.is_file()


def test_workflow__existing(fakefs):
    path = fakefs / "forecast"
    assert not workflow._existing(path=path).ready
    path.touch()
    assert workflow._existing(path=path).ready


def test_workflow__forecast_dataset(da_with_leadtime, fakefs):
    path = fakefs / "forecast"
    assert not workflow._forecast_dataset(path=path).ready
    path.touch()
    with patch.object(workflow.xr, "open_dataset", return_value=da_with_leadtime.to_dataset()):
        node = workflow._forecast_dataset(path=path)
    assert node.ready
    assert (da_with_leadtime == node.ref.HGT).all()


def test_workflow__grib_index_data_wgrib2(c, tc, tidy):
    gribidx = """
    1:0:d=2024040103:HGT:900 mb:anl:
    2:1:d=2024040103:FOO:900 mb:anl:
    3:2:d=2024040103:TMP:900 mb:anl:
    """
    idxfile = c.paths.grids_truth / "hrrr.idx"
    idxfile.write_text(tidy(gribidx))

    @external
    def mock(*_args, **_kwargs):
        yield "mock"
        yield Asset(idxfile, idxfile.exists)

    with patch.object(workflow, "_local_file_from_http", mock):
        node = workflow._grib_index_data_wgrib2(
            c=c, outdir=c.paths.grids_truth, tc=tc, url=c.truth.url
        )
    assert node.ref == {
        "gh-isobaricInhPa-0900": variables.HRRR(
            name="HGT", levstr="900 mb", firstbyte=0, lastbyte=0
        )
    }


def test_workflow__grib_index_file_eccodes(c, fakefs, logged, tc):
    grib = fakefs / "foo"
    grib.touch()
    with patch.object(workflow, "ec") as ec:
        ec.codes_index_write.side_effect = lambda _idx, p: Path(p).touch()
        assert workflow._grib_index_file_eccodes(c=c, grib_path=grib, tc=tc).ready
    yyyymmdd, hh, leadtime = tcinfo(tc)
    idx_path = c.paths.grids_truth / yyyymmdd / hh / leadtime / f"{grib.name}.ecidx"
    assert idx_path.is_file()
    assert logged("Wrote %s" % idx_path)


@mark.parametrize(("msgs", "expected"), [(0, False), (1, True), (2, True)])
def test__workflow__grib_message_in_file(c, expected, fakefs, logged, msgs, node, tc, testvars):
    grib_path = fakefs / "foo"
    idx_path = fakefs / "foo.ecidx"
    idx_path.touch()
    with (
        patch.object(
            workflow, "_grib_index_file_eccodes", return_value=node
        ) as _grib_index_file_eccodes,
        patch.object(workflow, "ec") as ec,
    ):
        ec.codes_new_from_index.side_effect = [object()] * msgs + [None]
        node = workflow._grib_message_in_file(c=c, path=grib_path, tc=tc, var=testvars["gh"])
        assert node.ready is expected
        if msgs == 2:
            assert logged("Found 2 GRIB messages")


@mark.parametrize("template", ["{root}/foo", "file://{root}/foo"])
def test_workflow__grid_grib__local(config_data, fakefs, gen_config, node, tc, template, testvars):
    config_data["truth"]["url"] = template.format(root=fakefs)
    c = gen_config(config_data, fakefs)
    with patch.object(
        workflow, "_grib_message_in_file", return_value=node
    ) as _grib_message_in_file:
        assert workflow._grid_grib(c=c, tc=tc, var=testvars["t"]).ready
        _grib_message_in_file.assert_called_once()


def test_workflow__grid_grib__remote(c, tc, testvars):
    idxdata = {
        "gh-isobaricInhPa-0900": variables.HRRR(
            name="HGT", levstr="900 mb", firstbyte=0, lastbyte=0
        ),
        "t-isobaricInhPa-0900": variables.HRRR(
            name="TMP", levstr="900 mb", firstbyte=2, lastbyte=2
        ),
    }
    ready = Event()

    @external
    def mock(*_args, **_kwargs):
        yield "mock"
        yield Asset(idxdata, ready.is_set)

    with patch.object(workflow, "_grib_index_data_wgrib2", wraps=mock) as _grib_index_data_wgrib2:
        node = workflow._grid_grib(c=c, tc=tc, var=testvars["t"])
        path = node.ref
        assert not path.exists()
        ready.set()
        with patch.object(workflow, "fetch") as fetch:
            fetch.side_effect = lambda taskname, url, path, headers: path.touch()  # noqa: ARG005
            path.parent.mkdir(parents=True, exist_ok=True)
            workflow._grid_grib(c=c, tc=tc, var=testvars["t"])
        assert path.exists()
    yyyymmdd = tc.yyyymmdd
    hh = tc.hh
    fh = int(tc.leadtime.total_seconds() // 3600)
    outdir = c.paths.grids_truth / tc.yyyymmdd / tc.hh / f"{fh:03d}"
    url = f"https://some.url/{yyyymmdd}/{hh}/{fh:02d}/a.grib2.idx"
    _grib_index_data_wgrib2.assert_called_with(c, outdir, tc, url=url)


def test_workflow__grid_nc(c_real_fs, check_cf_metadata, da_with_leadtime, tc, testvars):
    level = 900
    path = Path(c_real_fs.paths.grids_forecast, "a.nc")
    da_with_leadtime.to_netcdf(path)
    c_real_fs.forecast._path = str(path)
    node = workflow._grid_nc(c=c_real_fs, varname="HGT", tc=tc, var=testvars["gh"])
    assert node.ready
    check_cf_metadata(ds=xr.open_dataset(node.ref, decode_timedelta=True), name="HGT", level=level)


def test_workflow__grid_nc__no_paths_grids_forecast(config_data, tc, testvars):
    c = Config(raw=with_del(config_data, "paths", "grids", "forecast"))
    with raises(WXVXError) as e:
        workflow._grid_nc(c=c, varname="HGT", tc=tc, var=testvars["gh"])
    assert str(e.value) == "Specify path.grids.forecast when forecast dataset is netCDF or Zarr"


def test_workflow__local_file_from_http(c):
    url = f"{c.truth.url}.idx"
    node = workflow._local_file_from_http(outdir=c.paths.grids_truth, url=url, desc="Test")
    path: Path = node.ref
    assert not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with patch.object(workflow, "fetch") as fetch:
        fetch.side_effect = lambda taskname, url, path: path.touch()  # noqa: ARG005
        workflow._local_file_from_http(outdir=c.paths.grids_truth, url=url, desc="Test")
    fetch.assert_called_once_with(ANY, url, ANY)
    assert path.exists()


def test_workflow__missing(fakefs):
    path = fakefs / "missing"
    node = workflow._missing(path)
    assert node.ref == path
    assert not node.ready
    assert str(node).startswith(f"Missing path {path}")


def test_workflow__netcdf_from_obs(c, tc):
    yyyymmdd, hh, _ = tcinfo(tc)
    url = "https://bucket.amazonaws.com/gdas.{{ yyyymmdd }}.t{{ hh }}z.prepbufr.nr"
    c.truth = replace(c.truth, type="point", url=url)
    path = c.paths.obs / yyyymmdd / hh / f"gdas.{yyyymmdd}.t{hh}z.prepbufr.nc"
    assert not path.is_file()
    prepbufr = path.with_suffix(".nr")
    prepbufr.parent.mkdir(parents=True, exist_ok=True)
    prepbufr.touch()
    with patch.object(workflow, "mpexec", side_effect=lambda *_args: path.touch()) as mpexec:
        task = workflow._netcdf_from_obs(c=c, tc=tc)
    assert path.is_file()
    assert task.ready
    cfgfile = cast(dict, task.req)["cfgfile"].ref
    assert cfgfile.is_file()
    runscript = cfgfile.with_suffix(".sh")
    assert runscript.is_file()
    mpexec.assert_called_once_with(str(runscript), ANY, ANY)


def test_workflow__netcdf_from_obs__no_path(c, tc):
    c.paths = replace(c.paths, obs=None)
    with raises(WXVXError) as e:
        workflow._netcdf_from_obs(c=c, tc=tc)
    expected = "Config value paths.obs must be set"
    assert expected in str(e.value)


@mark.parametrize("dictkey", ["foo", "bar", "baz"])
def test_workflow__plot(c, dictkey, fakefs, fs):
    @external
    def _stat(x: str):
        yield x
        yield Asset(fakefs / f"{x}.stat", lambda: True)

    fs.add_real_directory(os.environ["CONDA_PREFIX"])
    varname, level, dfs, stat, width = TESTDATA[dictkey]
    with (
        patch.object(workflow, "_statreqs") as _statreqs,
        patch.object(workflow, "_prepare_plot_data") as _prepare_plot_data,
        patch("matplotlib.pyplot.xticks") as xticks,
    ):
        _statreqs.return_value = [_stat("model1"), _stat("model2")]
        _prepare_plot_data.side_effect = dfs
        os.environ["MPLCONFIGDIR"] = str(fakefs)
        cycle = c.cycles.values[0]  # noqa: PD011
        node = workflow._plot(
            c=c, varname=varname, level=level, cycle=cycle, stat=stat, width=width
        )
    path = node.ref
    assert node.ready
    assert path.is_file()
    assert _prepare_plot_data.call_count == 1
    xticks.assert_called_once_with(ticks=[0, 6, 12], labels=["000", "006", "012"], rotation=90)


def test_workflow__polyfile(fakefs, tidy):
    path = fakefs / "a.poly"
    assert not path.is_file()
    mask = ((52.6, 225.9), (52.6, 255.0), (21.1, 255.0), (21.1, 225.9))
    polyfile = workflow._polyfile(path=path, mask=mask)
    assert polyfile.ready
    expected = """
    MASK
    52.6 225.9
    52.6 255.0
    21.1 255.0
    21.1 225.9
    """
    assert path.read_text().strip() == tidy(expected)


@mark.parametrize("datafmt", [DataFormat.NETCDF, DataFormat.UNKNOWN])
@mark.parametrize("mask", [True, False])
@mark.parametrize("source", [Source.FORECAST, Source.TRUTH])
def test_workflow__stats_vs_grid(c, datafmt, fakefs, mask, source, tc, testvars):
    if not mask:
        c.forecast._mask = None

    @external
    def mock(*_args, **_kwargs):
        yield "mock"
        yield Asset(Path("/some/file"), lambda: True)

    taskfunc = workflow._stats_vs_grid
    rundir = fakefs / "run" / "stats" / "19700101" / "00" / "000"
    taskname = (
        "Stats vs grid for %s 2t-heightAboveGround-0002 at 19700101 00Z 000"
        % str(source).split(".")[1].lower()
    )
    kwargs = dict(c=c, varname="T2M", tc=tc, var=testvars["2t"], prefix="foo", source=source)
    with patch.object(workflow, "classify_data_format", return_value=datafmt):
        stat = taskfunc(**kwargs, dry_run=True).ref
        cfgfile = stat.with_suffix(".config")
        runscript = stat.with_suffix(".sh")
        assert not stat.is_file()
        assert not cfgfile.is_file()
        assert not runscript.is_file()
        with (
            patch.object(workflow, "_grid_grib", mock),
            patch.object(workflow, "_grid_nc", mock),
            patch.object(workflow, "mpexec", side_effect=lambda *_: stat.touch()) as mpexec,
        ):
            stat.parent.mkdir(parents=True)
            taskfunc(**kwargs)
        if datafmt != DataFormat.UNKNOWN:
            assert stat.is_file()
            assert cfgfile.is_file()
            assert runscript.is_file()
            mpexec.assert_called_once_with(str(runscript), rundir, taskname)


@mark.parametrize("datafmt", [DataFormat.NETCDF, DataFormat.ZARR, DataFormat.UNKNOWN])
def test_workflow__stats_vs_obs(c, datafmt, fakefs, tc, testvars):
    @external
    def mock(*_args, **_kwargs):
        yield "mock"
        yield Asset(Path("/some/file"), lambda: True)

    taskfunc = workflow._stats_vs_obs
    url = "https://bucket.amazonaws.com/gdas.{{ yyyymmdd }}.t{{ hh }}z.prepbufr.nr"
    c.truth = replace(c.truth, type="point", url=url)
    rundir = fakefs / "run" / "stats" / "19700101" / "00" / "000"
    taskname = "Stats vs obs for truth 2t-heightAboveGround-0002 at 19700101 00Z 000"
    kwargs = dict(c=c, varname="T2M", tc=tc, var=testvars["2t"], prefix="foo", source=Source.TRUTH)
    with patch.object(workflow, "classify_data_format", return_value=datafmt):
        stat = taskfunc(**kwargs, dry_run=True).ref
        cfgfile = stat.with_suffix(".config")
        runscript = stat.with_suffix(".sh")
        assert not stat.is_file()
        assert not cfgfile.is_file()
        assert not runscript.is_file()
        with (
            patch.object(workflow, "_grid_nc", mock),
            patch.object(workflow, "_netcdf_from_obs", mock),
            patch.object(workflow, "mpexec", side_effect=lambda *_: stat.touch()) as mpexec,
        ):
            stat.parent.mkdir(parents=True)
            taskfunc(**kwargs)
        if datafmt != DataFormat.UNKNOWN:
            assert stat.is_file()
            assert cfgfile.is_file()
            assert runscript.is_file()
            mpexec.assert_called_once_with(str(runscript), rundir, taskname)


# Support Tests


def test_workflow__at_validtime(tc):
    assert workflow._at_validtime(tc=tc) == "at 19700101 00Z 000"


def test_workflow__enforce_point_truth_type(c):
    c.truth = replace(c.truth, type="grid")
    with raises(WXVXError) as e:
        workflow._enforce_point_truth_type(c=c, taskname="foo")
    expected = "foo: This task requires that config value truth.type be set to 'point'"
    assert str(e.value) == expected


def test_workflow__meta(c):
    meta = workflow._meta(c=c, varname="HGT")
    assert meta.cf_standard_name == "geopotential_height"
    assert meta.level_type == "isobaricInhPa"


@mark.parametrize("dictkey", ["foo", "bar", "baz"])
def test_workflow__prepare_plot_data(dictkey):
    _, _, dfs, stat, width = TESTDATA[dictkey]
    node = lambda x: Mock(ref=f"{x}.stat", taskname=x)
    reqs = cast(Sequence[Node], [node("node1"), node("node2")])
    with patch.object(workflow.pd, "read_csv", side_effect=dfs):
        tdf = workflow._prepare_plot_data(reqs=reqs, stat=stat, width=width)
    assert isinstance(tdf, pd.DataFrame)
    assert stat in tdf.columns
    assert "FCST_LEAD" in tdf.columns
    assert all(tdf["FCST_LEAD"] == 6)
    if stat == "PODY":
        assert "FCST_THRESH" in tdf.columns
        assert "LABEL" in tdf.columns
    if stat == "FSS":
        assert width is not None
        assert "INTERP_PNTS" in tdf.columns
        assert tdf["INTERP_PNTS"].eq(width**2).all()


def test_workflow__regrid_width(c):
    c.regrid = replace(c.regrid, method="BILIN")
    assert workflow._regrid_width(c=c) == 2
    c.regrid = replace(c.regrid, method="NEAREST")
    assert workflow._regrid_width(c=c) == 1
    c.regrid = replace(c.regrid, method="FOO")
    with raises(WXVXError) as e:
        workflow._regrid_width(c=c)
    assert str(e.value) == "Could not determine 'width' value for regrid method 'FOO'"


@mark.parametrize(
    ("fmt", "path"),
    [
        (DataFormat.NETCDF, "/path/to/a.nc"),
        (DataFormat.ZARR, "/path/to/a.zarr"),
    ],
)
def test_workflow__req_grid(c, fmt, path, tc, testvars):
    with patch.object(workflow, "classify_data_format", return_value=fmt):
        req, datafmt = workflow._req_grid(path=path, c=c, varname="foo", tc=tc, var=testvars["2t"])
    # For netCDF and Zarr forecast datasets, the grid will be extracted from the dataset and CF-
    # decorated, so the requirement is a _grid_nc task, whose taskname is "Forecast grid ..."
    assert req.taskname.startswith("Forecast grid")
    assert datafmt == fmt


def test_workflow__req_grid__grib(c, tc, testvars):
    path = Path("/path/to/a.grib2")
    with patch.object(workflow, "classify_data_format", return_value=DataFormat.GRIB):
        req, datafmt = workflow._req_grid(path=path, c=c, varname="foo", tc=tc, var=testvars["2t"])
    # For GRIB forecast datasets, the entire GRIB file will be accessed by MET, so the requirement
    # is an existing local path.
    assert req.taskname.startswith("Existing path")
    assert datafmt == DataFormat.GRIB


def test_workflow__req_grid__missing(c, tc, testvars):
    path = Path("/path/to/a.grib2")
    with patch.object(workflow, "classify_data_format", return_value=DataFormat.UNKNOWN):
        req, datafmt = workflow._req_grid(path=path, c=c, varname="foo", tc=tc, var=testvars["2t"])
    # For missing forecast datasets, the requirement is a missing-file external task that blocks
    # further execution.
    assert req.taskname.startswith("Missing path")
    assert datafmt == DataFormat.UNKNOWN


def test_workflow__req_prepbufr(fakefs):
    assert not workflow._req_prepbufr(url="https://example.com/prepbufr.nr", outdir=fakefs).ready
    path = fakefs / "prepbufr.nr"
    path.touch()
    assert workflow._req_prepbufr(url=str(path), outdir=fakefs).ready
    assert workflow._req_prepbufr(url=f"file://{path}", outdir=fakefs).ready


@mark.parametrize("cycle", [datetime(2024, 12, 19, 18, tzinfo=timezone.utc), None])
def test_workflow__statargs(c, statkit, cycle):
    with (
        patch.object(workflow, "_vxvars", return_value={statkit.var: statkit.varname}),
        patch.object(workflow, "gen_validtimes", return_value=[statkit.tc]),
    ):
        statargs = workflow._statargs(
            c=c,
            varname=statkit.varname,
            level=statkit.level,
            source=statkit.source,
            cycle=cycle,
        )
    assert list(statargs) == [
        (c, statkit.varname, statkit.tc, statkit.var, statkit.prefix, statkit.source)
    ]


@mark.parametrize("compare", [True, False])
@mark.parametrize("cycle", [datetime(2024, 12, 19, 18, tzinfo=timezone.utc), None])
def test_workflow__statreqs(c, compare, statkit, cycle):
    c.truth = replace(c.truth, compare=compare)
    with (
        patch.object(workflow, "_stats_vs_grid") as _stats_vs_grid,
        patch.object(workflow, "_vxvars", return_value={statkit.var: statkit.varname}),
        patch.object(workflow, "gen_validtimes", return_value=[statkit.tc]),
    ):
        reqs = workflow._statreqs(c=c, varname=statkit.varname, level=statkit.level, cycle=cycle)
    n = 2 if compare else 1
    assert len(reqs) == n
    assert _stats_vs_grid.call_count == n
    args = (c, statkit.varname, statkit.tc, statkit.var)
    assert _stats_vs_grid.call_args_list[0].args == (
        *args,
        f"forecast_gh_{statkit.level_type}_{statkit.level:04d}",
        Source.FORECAST,
    )
    if compare:
        assert _stats_vs_grid.call_args_list[1].args == (
            *args,
            f"gfs_gh_{statkit.level_type}_{statkit.level:04d}",
            Source.TRUTH,
        )


def test_workflow__stats_and_widths(c):
    assert list(workflow._stats_and_widths(c=c, varname="REFC")) == [
        ("FSS", 3),
        ("FSS", 5),
        ("FSS", 11),
        ("PODY", None),
    ]
    assert list(workflow._stats_and_widths(c=c, varname="SPFH")) == [
        ("ME", None),
        ("RMSE", None),
    ]


def test_workflow__var(c, testvars):
    assert workflow._var(c=c, varname="HGT", level=900) == testvars["gh"]


def test_workflow__varnames_and_levels(c):
    assert list(workflow._varnames_and_levels(c=c)) == [
        ("HGT", 900),
        ("REFC", None),
        ("SPFH", 900),
        ("SPFH", 1000),
        ("T2M", 2),
    ]


def test_workflow__vxvars(c, testvars):
    assert workflow._vxvars(c=c) == {
        testvars["2t"]: "T2M",
        testvars["gh"]: "HGT",
        Var("q", "isobaricInhPa", 1000): "SPFH",
        Var("q", "isobaricInhPa", 900): "SPFH",
        testvars["refc"]: "REFC",
    }


def test_workflow__write_runscript(fakefs, tidy):
    path = fakefs / "runscript"
    assert not path.exists()
    workflow._write_runscript(path=path, content="foo")
    expected = """
    #!/usr/bin/env bash

    foo
    """
    assert path.read_text().strip() == tidy(expected)


# Fixtures


@fixture
def ngrids(c):
    n_validtimes = len(list(gen_validtimes(c.cycles, c.leadtimes)))
    n_var_level_pairs = len(list(workflow._varnames_and_levels(c)))
    return n_validtimes * n_var_level_pairs


@fixture
def noop():
    @external
    def noop(*_args, **_kwargs):
        yield "mock"
        yield Asset(None, lambda: False)

    return noop


@fixture
def obs_info(c):
    url = "https://bucket.amazonaws.com/gdas.{{ yyyymmdd }}.t{{ hh }}z.prepbufr.nr"
    c.truth = replace(c.truth, type="point", url=url)
    expected = [
        c.paths.obs / yyyymmdd / hh / f"gdas.{yyyymmdd}.t{hh}z.prepbufr.x"
        for (yyyymmdd, hh) in [
            ("20241219", "18"),
            ("20241220", "00"),
            ("20241220", "06"),
            ("20241220", "12"),
            ("20241220", "18"),
        ]
    ]
    return c, expected


@fixture
def statkit(tc, testvars):
    level = 900
    level_type = "isobaricInhPa"
    return ns(
        level=level,
        level_type=level_type,
        prefix=f"forecast_gh_{level_type}_{level:04d}",
        source=Source.FORECAST,
        tc=tc,
        var=testvars["gh"],
        varname="HGT",
    )


@fixture
def testvars():
    return {
        "2t": Var("2t", "heightAboveGround", 2),
        "gh": Var(name="gh", level_type="isobaricInhPa", level=900),
        "refc": Var(name="refc", level_type="atmosphere"),
        "t": Var(name="t", level_type="isobaricInhPa", level=900),
    }


# Helpers


def fcst_field(fmt: DataFormat, surface: bool) -> str:
    assert fmt in [DataFormat.GRIB, DataFormat.NETCDF, DataFormat.ZARR]
    if fmt in [DataFormat.NETCDF, DataFormat.ZARR]:
        if surface:
            return """
            level = [
              "(0,0,*,*)"
            ];
            name = "T2M";
            set_attr_level = "Z002";
            """
        return """
        level = [
          "(0,0,*,*)"
        ];
        name = "HGT";
        set_attr_level = "P900";
        """
    if surface:
        return """
        level = [
          "Z002"
        ];
        name = "TMP";
        """
    return """
    level = [
      "P900"
    ];
    name = "HGT";
    """


def respace(text: str) -> str:
    return indent(text, "      ")
