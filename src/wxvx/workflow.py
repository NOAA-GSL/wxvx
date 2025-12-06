from __future__ import annotations

import logging
import re
from functools import cache
from itertools import chain, pairwise, product
from pathlib import Path
from stat import S_IEXEC
from textwrap import dedent
from threading import Lock
from typing import TYPE_CHECKING, cast
from urllib.parse import urlparse
from warnings import catch_warnings, simplefilter

import eccodes as ec  # type: ignore[import-untyped]
import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import xarray as xr
from iotaa import Asset, Node, collection, external, task

from wxvx import variables
from wxvx.metconf import render as render_metconf
from wxvx.net import fetch
from wxvx.strings import S
from wxvx.times import TimeCoords, gen_validtimes, hh, tcinfo, yyyymmdd
from wxvx.types import Cycles, Named, Source, TruthType
from wxvx.util import (
    LINETYPE,
    DataFormat,
    Proximity,
    WXVXError,
    atomic,
    classify_data_format,
    classify_url,
    mpexec,
    render,
    version,
)
from wxvx.variables import VARMETA, Var, da_construct, da_select, ds_construct, metlevel

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from datetime import datetime

    from wxvx.types import Config, VarMeta

_PLOT_LOCK = Lock()

# Public tasks


@collection
def grids(c: Config):
    yield "Grids"
    reqs = [grids_forecast(c)]
    if c.baseline.name:
        reqs.append(grids_baseline(c))
    if c.truth.type == TruthType.GRID:
        reqs.append(grids_truth(c))
    yield reqs


@collection
def grids_baseline(c: Config):
    if c.baseline.name is None:
        yield "No baseline defined"
        yield None
    else:
        name, source = (
            (c.truth.name, Source.TRUTH)
            if c.baseline.name == S.truth
            else (c.baseline.name, Source.BASELINE)
        )
        yield "Baseline grids for %s" % name
        reqs = []
        for var, _, tc in _vars_varnames_times(c):
            reqs.append(_grid_grib(c, tc, var, source))
        yield reqs


@collection
def grids_forecast(c: Config):
    yield "Forecast grids for %s" % c.forecast.name
    reqs = []
    for var, varname, tc in _vars_varnames_times(c):
        path = Path(render(c.forecast.path, tc, context=c.raw))
        node, _ = _forecast_grid(path, c, varname, tc, var)
        reqs.append(node)
    yield reqs


@collection
def grids_truth(c: Config):
    yield "Truth grids for %s" % c.truth.name
    if c.truth.type is TruthType.GRID:
        reqs = [
            _grid_grib(c, TimeCoords(cycle=tc.validtime, leadtime=0), var, Source.TRUTH)
            for var, _, tc in _vars_varnames_times(c)
        ]
    else:
        reqs = None
    yield reqs


@collection
def ncobs(c: Config):
    taskname = "Truth netCDF from obs for %s" % c.truth.name
    _enforce_point_truth_type(c, taskname)
    yield taskname
    yield [
        _netcdf_from_obs(c, TimeCoords(tc.validtime))
        for tc in gen_validtimes(c.cycles, c.leadtimes)
    ]


@collection
def obs(c: Config):
    taskname = "Truth obs for %s" % c.truth.name
    _enforce_point_truth_type(c, taskname)
    yield taskname
    reqs = []
    for tc in gen_validtimes(c.cycles, c.leadtimes):
        tc_valid = TimeCoords(tc.validtime)
        url = render(c.truth.url, tc_valid, context=c.raw)
        yyyymmdd, hh, _ = tcinfo(tc_valid)
        reqs.append(_prepbufr(url, c.paths.obs / yyyymmdd / hh))
    yield reqs


@collection
def plots(c: Config):
    taskname = "Plots for %s vs %s" % (c.forecast.name, c.truth.name)
    yield taskname
    yield [
        _plot(c, cycle, varname, level, stat, width)
        for cycle in c.cycles.values  # noqa: PD011
        for varname, level in _varnames_levels(c)
        for stat, width in _stats_widths(c, varname)
    ]


@collection
def stats(c: Config):
    taskname = "Stats for %s vs %s" % (c.forecast.name, c.truth.name)
    yield taskname
    reqs: list[Node] = []
    for varname, level in _varnames_levels(c):
        reqs.extend(_stat_reqs(c, varname, level))
    yield reqs


# Private tasks


@task
def _config_grid_stat(
    c: Config,
    path: Path,
    source: Source,
    varname: str,
    var: Var,
    prefix: str,
    datafmt: DataFormat,
    polyfile: Node | None,
):
    taskname = f"Config for grid_stat {path}"
    yield taskname
    yield Asset(path, path.is_file)
    yield None
    field_fcst, field_obs = _config_fields(c, varname, var, datafmt)
    meta = _meta(c, varname)
    config = {
        "fcst": {"field": [field_fcst]},
        "mask": {"grid": [] if polyfile else ["FULL"], "poly": [polyfile.ref] if polyfile else []},
        "model": c.truth.name if source == Source.TRUTH else c.forecast.name,
        "nc_pairs_flag": "FALSE",
        "obs": {"field": [field_obs]},
        "obtype": c.truth.name,
        "output_flag": dict.fromkeys(sorted({LINETYPE[x] for x in meta.met_stats}), "BOTH"),
        "output_prefix": f"{prefix}",
        "regrid": {"method": c.regrid.method, "to_grid": c.regrid.to},
        "tmp_dir": path.parent,
    }
    if nbrhd := {k: v for k, v in [("shape", meta.nbrhd_shape), ("width", meta.nbrhd_width)] if v}:
        config["nbrhd"] = nbrhd
    with atomic(path) as tmp:
        tmp.write_text("%s\n" % render_metconf(config))


@task
def _config_pb2nc(c: Config, path: Path):
    taskname = f"Config for pb2nc {path}"
    yield taskname
    yield Asset(path, path.is_file)
    yield None
    # Specify the union of values needed by either sfc or atm vx and let point_stat restrict its
    # selection of obs from the netCDF file created by pb2nc.
    _type = ["min", "max", "range", "mean", "stdev", "median", "p80"]
    config: dict = {
        "mask": {"grid": c.regrid.to if re.match(r"^G\d{3}$", str(c.regrid.to)) else ""},
        "message_type": ["ADPSFC", "ADPUPA", "AIRCAR", "AIRCFT"],
        "obs_bufr_var": ["POB", "QOB", "TOB", "UOB", "VOB", "ZOB"],
        "obs_window": {"beg": -1800, "end": 1800},
        "quality_mark_thresh": 9,
        "time_summary": {"step": 3600, "width": 3600, "obs_var": [], "type": _type},
        "tmp_dir": path.parent,
    }
    with atomic(path) as tmp:
        tmp.write_text("%s\n" % render_metconf(config))


@task
def _config_point_stat(
    c: Config, path: Path, source: Source, varname: str, var: Var, prefix: str, datafmt: DataFormat
):
    taskname = f"Config for point_stat {path}"
    yield taskname
    yield Asset(path, path.is_file)
    yield None
    field_fcst, field_obs = _config_fields(c, varname, var, datafmt)
    surface = var.level_type in ("heightAboveGround", "surface")
    sections = {Source.BASELINE: c.baseline, Source.FORECAST: c.forecast, Source.TRUTH: c.truth}
    config = {
        "fcst": {"field": [field_fcst]},
        "interp": {"shape": "SQUARE", "type": {"method": "BILIN", "width": 2}, "vld_thresh": 1.0},
        "message_type": ["SFC" if surface else "ATM"],
        "message_type_group_map": {"ATM": "ADPUPA,AIRCAR,AIRCFT", "SFC": "ADPSFC"},
        "model": cast(Named, sections[source]).name,
        "obs": {"field": [field_obs]},
        "obs_window": {"beg": -900 if surface else -1800, "end": 900 if surface else 1800},
        "output_flag": {"cnt": "BOTH"},
        "output_prefix": f"{prefix}",
        "regrid": {
            "method": c.regrid.method,
            "to_grid": c.regrid.to,
            "width": _regrid_width(c),
        },
        "tmp_dir": path.parent,
    }
    with atomic(path) as tmp:
        tmp.write_text("%s\n" % render_metconf(config))


@external
def _existing(path: Path):
    taskname = "Existing path %s" % path
    yield taskname
    yield Asset(path, path.exists)


@task
def _forecast_dataset(path: Path):
    taskname = "Forecast dataset %s" % path
    yield taskname
    ds = xr.Dataset()
    yield Asset(ds, lambda: bool(ds))
    yield _existing(path)
    logging.info("%s: Opening forecast %s", taskname, path)
    with catch_warnings():
        simplefilter("ignore")
        src = xr.open_dataset(path, decode_timedelta=True)
        ds.update(src)
        ds.attrs.update(src.attrs)


@task
def _grib_index_data_wgrib2(c: Config, outdir: Path, tc: TimeCoords, url: str):
    taskname = "GRIB index data %s" % _at_validtime(tc)
    yield taskname
    idxdata: dict[str, Var] = {}
    yield Asset(idxdata, lambda: bool(idxdata))
    idxfile = _local_file_from_http(outdir, url, "GRIB index file")
    yield idxfile
    lines = idxfile.ref.read_text(encoding="utf-8").strip().split("\n")
    lines.append(":-1:::::")  # end marker
    vxvars = set(_vxvars(c).keys())
    truth_class = variables.model_class(c.truth.name)
    for this_record, next_record in pairwise([line.split(":") for line in lines]):
        truth_var = truth_class(
            name=this_record[3],
            levstr=this_record[4],
            firstbyte=int(this_record[1]),
            lastbyte=int(next_record[1]) - 1,
        )
        if truth_var in vxvars:
            idxdata[str(truth_var)] = truth_var


@task
def _grib_index_file_eccodes(c: Config, grib_path: Path, tc: TimeCoords, source: Source):
    yyyymmdd, hh, leadtime = tcinfo(tc)
    gridsdir = c.paths.grids_truth if source is Source.TRUTH else c.paths.grids_baseline
    outdir = gridsdir / yyyymmdd / hh / leadtime
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"{grib_path.name}.ecidx"
    taskname = "GRIB index file %s %s" % (path, _at_validtime(tc))
    yield taskname
    yield Asset(path, path.is_file)
    yield _existing(grib_path)
    grib_index_keys = ["shortName", "typeOfLevel", S.level]
    idx = ec.codes_index_new_from_file(str(grib_path), grib_index_keys)
    with atomic(path) as tmp:
        ec.codes_index_write(idx, str(tmp))
    logging.info("%s: Wrote %s", taskname, path)


@task
def _grib_message_in_file(c: Config, path: Path, tc: TimeCoords, var: Var, source: Source):
    taskname = "GRIB message for %s in %s %s" % (var, path, _at_validtime(tc))
    yield taskname
    exists = [False]
    yield Asset(exists, lambda: exists[0])
    idx = _grib_index_file_eccodes(c, path, tc, source)
    yield idx
    idx = ec.codes_index_read(str(idx.ref))
    for k, v in [
        ("shortName", var.name),
        ("typeOfLevel", var.level_type),
        ("level", int(var.level) if var.level else 0),
    ]:
        ec.codes_index_select(idx, k, v)
    count = 0
    while gid := ec.codes_new_from_index(idx):
        count += 1
        ec.codes_release(gid)
    if count > 1:
        logging.warning("Found %d GRIB messages matching %s in index %s.", count, var, path)
    exists[0] = count > 0


@task
def _grid_grib(c: Config, tc: TimeCoords, var: Var, source: Source):
    assert source in (Source.BASELINE, Source.TRUTH)
    template = c.truth.url
    if source is Source.BASELINE and c.baseline.name != S.truth:
        template = cast(str, c.baseline.url)
    url = render(template, tc, context=c.raw)
    proximity, src = classify_url(url)
    if proximity == Proximity.LOCAL:
        yield "GRIB file %s providing %s grid %s" % (src, var, _at_validtime(tc))
        exists = [False]
        yield Asset(src, lambda: exists[0])
        msg = _grib_message_in_file(c, src, tc, var, source)
        yield msg
        exists[0] = msg.ready
    else:
        yyyymmdd, hh, leadtime = tcinfo(tc)
        gridsdir = c.paths.grids_truth if source is Source.TRUTH else c.paths.grids_baseline
        outdir = gridsdir / yyyymmdd / hh / leadtime
        path = outdir / f"{var}.grib2"
        taskname = "%s grid %s" % (source.name.lower().capitalize(), path)
        yield taskname
        yield Asset(path, path.is_file)
        idxdata = _grib_index_data_wgrib2(c, outdir, tc, url=f"{url}.idx")
        yield idxdata
        var_idx = idxdata.ref[str(var)]
        fb, lb = var_idx.firstbyte, var_idx.lastbyte
        headers = {"Range": "bytes=%s" % (f"{fb}-{lb}" if lb else fb)}
        fetch(taskname, url, path, headers)


@task
def _grid_nc(c: Config, varname: str, tc: TimeCoords, var: Var):
    yyyymmdd, hh, leadtime = tcinfo(tc)
    if not c.paths.grids_forecast:
        msg = "Specify path.grids.forecast when forecast dataset is netCDF or Zarr"
        raise WXVXError(msg)
    path = c.paths.grids_forecast / yyyymmdd / hh / leadtime / f"{var}.nc"
    taskname = "Forecast grid %s" % path
    yield taskname
    yield Asset(path, path.is_file)
    fd = _forecast_dataset(Path(render(c.forecast.path, tc, context=c.raw)))
    yield fd
    src = da_select(c, fd.ref, varname, tc, var)
    da = da_construct(c, src)
    ds = ds_construct(c, da, taskname, var.level)
    with atomic(path) as tmp:
        ds.to_netcdf(tmp, encoding={varname: {"zlib": True, "complevel": 9}})
    logging.info("%s: Wrote %s", taskname, path)


@task
def _local_file_from_http(outdir: Path, url: str, desc: str):
    path = outdir / Path(urlparse(url).path).name
    taskname = "%s %s" % (desc, path)
    yield taskname
    yield Asset(path, path.is_file)
    yield None
    fetch(taskname, url, path)


@external
def _missing(path: Path):
    taskname = "Missing path %s" % path
    yield taskname
    yield Asset(path, lambda: False)


@task
def _netcdf_from_obs(c: Config, tc: TimeCoords):
    yyyymmdd, hh, _ = tcinfo(tc)
    taskname = "netCDF from prepbufr at %s %sZ" % (yyyymmdd, hh)
    yield taskname
    url = render(c.truth.url, tc, context=c.raw)
    if not c.paths.obs:
        msg = "Config value paths.obs must be set"
        raise WXVXError(msg)
    path = (c.paths.obs / yyyymmdd / hh / url.split("/")[-1]).with_suffix(".nc")
    yield Asset(path, path.is_file)
    rundir = c.paths.run / "pb2nc" / yyyymmdd / hh
    cfgfile = _config_pb2nc(c, rundir / path.with_suffix(".config").name)
    prepbufr = _prepbufr(url, path.parent)
    yield {"cfgfile": cfgfile, "prepbufr": prepbufr}
    runscript = cfgfile.ref.with_suffix(".sh")
    content = "exec time pb2nc -v 4 {prepbufr} {netcdf} {config} >{log} 2>&1".format(
        prepbufr=prepbufr.ref,
        netcdf=path,
        config=cfgfile.ref,
        log=f"{path.stem}.log",
    )
    _write_runscript(runscript, content)
    path.parent.mkdir(parents=True, exist_ok=True)
    mpexec(str(runscript), rundir, taskname)


@task
def _plot(
    c: Config, cycle: datetime, varname: str, level: float | None, stat: str, width: int | None
):
    meta = _meta(c, varname)
    var = _var(c, varname, level)
    desc = meta.description.format(level=var.level)
    cyclestr = f"{yyyymmdd(cycle)} {hh(cycle)}Z"
    taskname = f"Plot {desc}{' width ' + str(width) if width else ''} {stat} at {cyclestr}"
    yield taskname
    rundir = c.paths.run / "plots" / yyyymmdd(cycle) / hh(cycle)
    path = rundir / f"{var}-{stat}{'-width-' + str(width) if width else ''}-plot.png"
    yield Asset(path, path.is_file)
    reqs = _stat_reqs(c, varname, level, cycle)
    yield reqs
    leadtimes = ["%03d" % (td.total_seconds() // 3600) for td in c.leadtimes.values]  # noqa: PD011
    plot_data = _prepare_plot_data(reqs, stat, width)
    hue = "LABEL" if "LABEL" in plot_data.columns else "MODEL"
    w = f"(width={width}) " if width else ""
    with _PLOT_LOCK, catch_warnings():
        simplefilter("ignore")
        sns.set(style="darkgrid")
        plt.figure(figsize=(10, 6), constrained_layout=True)
        sns.lineplot(data=plot_data, x="FCST_LEAD", y=stat, hue=hue, marker="o", linewidth=2)
        plt.title(
            "%s %s %s%s vs %s at %s" % (desc, stat, w, c.forecast.name, c.truth.name, cyclestr)
        )
        plt.xlabel("Leadtime")
        plt.ylabel(f"{stat} ({meta.units})")
        plt.xticks(ticks=[int(lt) for lt in leadtimes], labels=leadtimes, rotation=90)
        plt.legend(title="Model", bbox_to_anchor=(1.02, 1), loc="upper left")
        plt.figtext(0.403, 0.0, f"wxvx {version()}", fontsize=6)
        plt.tight_layout(rect=(0, 0.005, 1, 1))
        path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(path, bbox_inches="tight")
        plt.close()


@task
def _polyfile(path: Path, mask: tuple[tuple[float, float]]):
    taskname = "Poly file %s" % path
    yield taskname
    yield Asset(path, path.is_file)
    yield None
    content = "MASK\n%s\n" % "\n".join(f"{lat} {lon}" for lat, lon in mask)
    with atomic(path) as tmp:
        tmp.write_text(content)


@task
def _stats_vs_grid(c: Config, varname: str, tc: TimeCoords, var: Var, prefix: str, source: Source):
    taskname = "Stats vs grid for %s %s %s" % (source.name.lower(), var, _at_validtime(tc))
    yield taskname
    yyyymmdd, hh, leadtime = tcinfo(tc)
    rundir = c.paths.run / "stats" / yyyymmdd / hh / leadtime
    yyyymmdd_valid, hh_valid, _ = tcinfo(TimeCoords(tc.validtime))
    template = "grid_stat_%s_%02d0000L_%s_%s0000V.stat"
    path = rundir / (template % (prefix, int(leadtime), yyyymmdd_valid, hh_valid))
    yield Asset(path, path.is_file)
    if source == Source.FORECAST:
        location = Path(render(c.forecast.path, tc, context=c.raw))
        fcst, datafmt = _forecast_grid(location, c, varname, tc, var)
    else:
        fcst = _grid_grib(c, tc, var, source)
        datafmt = DataFormat.GRIB
    obs = _grid_grib(c, TimeCoords(cycle=tc.validtime, leadtime=0), var, Source.TRUTH)
    reqs = [fcst, obs]
    polyfile = None
    if mask := c.forecast.mask:
        polyfile = _polyfile(c.paths.run / "stats" / "mask.poly", mask)
        reqs.append(polyfile)
    path_config = path.with_suffix(".config")
    config = _config_grid_stat(c, path_config, source, varname, var, prefix, datafmt, polyfile)
    if datafmt != DataFormat.UNKNOWN:
        reqs.append(config)
    yield reqs
    runscript = path.with_suffix(".sh")
    content = """
    export OMP_NUM_THREADS=1
    exec time grid_stat -v 4 {fcst} {obs} {config} >{log} 2>&1
    """.format(
        fcst=fcst.ref,
        obs=obs.ref,
        config=config.ref,
        log=f"{path.stem}.log",
    )
    _write_runscript(runscript, content)
    mpexec(str(runscript), rundir, taskname)


@task
def _stats_vs_obs(c: Config, varname: str, tc: TimeCoords, var: Var, prefix: str, source: Source):
    assert source in (Source.BASELINE, Source.FORECAST)
    taskname = "Stats vs obs for %s %s %s" % (source.name.lower(), var, _at_validtime(tc))
    yield taskname
    yyyymmdd, hh, leadtime = tcinfo(tc)
    rundir = c.paths.run / "stats" / yyyymmdd / hh / leadtime
    template = "point_stat_%s_%02d0000L_%s_%s0000V.stat"
    yyyymmdd_valid, hh_valid, _ = tcinfo(TimeCoords(tc.validtime))
    path = rundir / (template % (prefix, int(leadtime), yyyymmdd_valid, hh_valid))
    yield Asset(path, path.is_file)
    obs = _netcdf_from_obs(c, TimeCoords(tc.validtime))
    reqs: list[Node] = [obs]
    if source is Source.FORECAST:
        location = Path(render(c.forecast.path, tc, context=c.raw))
        fcst, datafmt = _forecast_grid(location, c, varname, tc, var)
    else:
        fcst = _grid_grib(c, tc, var, Source.BASELINE)
        datafmt = DataFormat.GRIB
    reqs.append(fcst)
    config = _config_point_stat(
        c, path.with_suffix(".config"), source, varname, var, prefix, datafmt
    )
    if datafmt != DataFormat.UNKNOWN:
        reqs.append(config)
    yield reqs
    runscript = path.with_suffix(".sh")
    content = "exec time point_stat -v 4 {fcst} {obs} {config} -outdir {rundir} >{log} 2>&1".format(
        fcst=fcst.ref,
        obs=obs.ref,
        config=config.ref,
        rundir=rundir,
        log=f"{path.stem}.log",
    )
    _write_runscript(runscript, content)
    mpexec(str(runscript), rundir, taskname)


# Support


def _at_validtime(tc: TimeCoords) -> str:
    yyyymmdd, hh, leadtime = tcinfo(tc)
    return "at %s %sZ %s" % (yyyymmdd, hh, leadtime)


def _config_fields(c: Config, varname: str, var: Var, datafmt: DataFormat):
    level_obs = metlevel(var.level_type, var.level)
    varname_truth = variables.model_class(c.truth.name).varname(var.name)
    assert datafmt != DataFormat.UNKNOWN
    level_fcst, name_fcst = (
        (level_obs, varname_truth) if datafmt == DataFormat.GRIB else ("(0,0,*,*)", varname)
    )
    field_fcst = {S.level: [level_fcst], S.name: name_fcst}
    if datafmt != DataFormat.GRIB:
        field_fcst["set_attr_level"] = level_obs
    field_obs = {S.level: [level_obs], S.name: varname_truth}
    meta = _meta(c, varname)
    if meta.cat_thresh:
        for x in field_fcst, field_obs:
            x["cat_thresh"] = meta.cat_thresh
    if meta.cnt_thresh:
        for x in field_fcst, field_obs:
            x["cnt_thresh"] = meta.cnt_thresh
    return field_fcst, field_obs


def _enforce_point_truth_type(c: Config, taskname: str):
    if c.truth.type != TruthType.POINT:
        msg = "%s: This task requires that config value truth.type be set to 'point'"
        raise WXVXError(msg % taskname)


def _forecast_grid(
    path: Path, c: Config, varname: str, tc: TimeCoords, var: Var
) -> tuple[Node, DataFormat]:
    data_format = classify_data_format(path)
    if data_format is DataFormat.UNKNOWN:
        return _missing(path), data_format
    if data_format == DataFormat.GRIB:
        return _existing(path), data_format
    return _grid_nc(c, varname, tc, var), data_format


def _meta(c: Config, varname: str) -> VarMeta:
    return VARMETA[c.variables[varname][S.name]]


def _prepare_plot_data(reqs: Sequence[Node], stat: str, width: int | None) -> pd.DataFrame:
    linetype = LINETYPE[stat]
    files = [str(x.ref).replace(".stat", f"_{linetype}.txt") for x in reqs]
    columns = ["MODEL", "FCST_LEAD", stat]
    if linetype in ["cts", "nbrcnt"]:
        columns.append("FCST_THRESH")
    if linetype == "nbrcnt":
        columns.append("INTERP_PNTS")
    plot_rows = [pd.read_csv(file, sep=r"\s+")[columns] for file in files]
    plot_data = pd.concat(plot_rows)
    plot_data["FCST_LEAD"] = plot_data["FCST_LEAD"] // 10000
    if "FCST_THRESH" in columns:
        plot_data["LABEL"] = plot_data.apply(
            lambda row: f"{row['MODEL']}, threshold: {row['FCST_THRESH']}", axis=1
        )
    if "INTERP_PNTS" in columns and width is not None:
        plot_data = plot_data[plot_data["INTERP_PNTS"] == width**2]
    return plot_data


def _prepbufr(url: str, outdir: Path) -> Node:
    proximity, src = classify_url(url)
    if proximity == Proximity.LOCAL:
        return _existing(src)
    return _local_file_from_http(outdir, url, "prepbufr file")


def _regrid_width(c: Config) -> int:
    try:
        return {"BILIN": 2, "NEAREST": 1}[c.regrid.method]
    except KeyError as e:
        msg = "Could not determine 'width' value for regrid method '%s'" % c.regrid.method
        raise WXVXError(msg) from e


def _stat_args(
    c: Config, varname: str, level: float | None, source: Source, cycle: datetime | None
) -> Iterator:
    if cycle:
        start = cycle.strftime("%Y-%m-%dT%H:%M:%S")
        step = "00:00:00"
        stop = start
        cycles = Cycles(dict(start=start, step=step, stop=stop))
    else:
        cycles = c.cycles
    sections = {Source.BASELINE: c.baseline, Source.FORECAST: c.forecast, Source.TRUTH: c.truth}
    name = cast(Named, sections[source]).name.lower()
    prefix = lambda var: "%s_%s" % (name, str(var).replace("-", "_"))
    args = [
        (c, vn, tc, var, prefix(var), source)
        for (var, vn), tc in product(_vxvars(c).items(), gen_validtimes(cycles, c.leadtimes))
        if vn == varname and var.level == level
    ]
    return iter(sorted(args))


def _stat_reqs(
    c: Config, varname: str, level: float | None, cycle: datetime | None = None
) -> Sequence[Node]:
    f = _stats_vs_obs if c.truth.type == TruthType.POINT else _stats_vs_grid
    reqs_for = lambda source: [f(*args) for args in _stat_args(c, varname, level, source, cycle)]
    reqs: Sequence[Node] = reqs_for(Source.FORECAST)
    if c.baseline.name is not None:
        source = Source.TRUTH if c.baseline.name == S.truth else Source.BASELINE
        reqs = [*reqs, *reqs_for(source)]
    return reqs


def _stats_widths(c: Config, varname) -> Iterator[tuple[str, int | None]]:
    meta = _meta(c, varname)
    return chain.from_iterable(
        ((stat, width) for width in (meta.nbrhd_width or []))
        if LINETYPE[stat] == "nbrcnt"
        else [(stat, None)]
        for stat in meta.met_stats
    )


def _var(c: Config, varname: str, level: float | None) -> Var:
    m = _meta(c, varname)
    return Var(m.name, m.level_type, level)


def _varnames_levels(c: Config) -> Iterator[tuple[str, float | None]]:
    return iter(
        (varname, level)
        for varname, attrs in c.variables.items()
        for level in attrs.get(S.levels, [None])
    )


def _vars_varnames_times(c: Config) -> Iterator[tuple[Var, str, TimeCoords]]:
    return iter(
        (var, varname, tc)
        for var, varname in _vxvars(c).items()
        for tc in gen_validtimes(c.cycles, c.leadtimes)
    )


@cache
def _vxvars(c: Config) -> dict[Var, str]:
    return {
        Var(attrs[S.name], attrs[S.level_type], level): varname
        for varname, attrs in c.variables.items()
        for level in attrs.get(S.levels, [None])
    }


def _write_runscript(path: Path, content: str) -> None:
    with atomic(path) as tmp:
        tmp.write_text("#!/usr/bin/env bash\n\n%s\n" % dedent(content).strip())
    path.chmod(path.stat().st_mode | S_IEXEC)
