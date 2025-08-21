from __future__ import annotations

import logging
from datetime import datetime
from functools import cache
from itertools import chain, pairwise, product
from pathlib import Path
from stat import S_IEXEC
from textwrap import dedent
from typing import TYPE_CHECKING
from urllib.parse import urlparse
from warnings import catch_warnings, simplefilter

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import xarray as xr
from iotaa import Node, asset, external, task, tasks

from wxvx import variables
from wxvx.metconf import render as render_metconf
from wxvx.net import fetch
from wxvx.times import TimeCoords, gen_validtimes, hh, tcinfo, yyyymmdd
from wxvx.types import Cycles, Source
from wxvx.util import LINETYPE, Proximity, atomic, classify_url, mpexec, render
from wxvx.variables import VARMETA, Var, da_construct, da_select, ds_construct, metlevel

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from wxvx.types import Config, VarMeta

# Public tasks


@tasks  # PM REMOVE
def test(c: Config):
    yield "test"
    yield [_netcdf_from_prepbufr(c, tc) for tc in gen_validtimes(c.cycles, c.leadtimes)]


@tasks
def grids(c: Config, baseline: bool = True, forecast: bool = True):
    if baseline and not forecast:
        suffix = "{b}"
    elif forecast and not baseline:
        suffix = "{f}"
    else:
        suffix = "{f} vs {b}"
    taskname = "Grids for %s" % suffix.format(b=c.baseline.name, f=c.forecast.name)
    yield taskname
    reqs: list[Node] = []
    for var, varname in _vxvars(c).items():
        for tc in gen_validtimes(c.cycles, c.leadtimes):
            if forecast:
                forecast_grid = _grid_nc(c, varname, tc, var)
                reqs.append(forecast_grid)
            if baseline:
                baseline_grid = _grid_grib(c, TimeCoords(cycle=tc.validtime, leadtime=0), var)
                reqs.append(baseline_grid)
                if c.baseline.compare:
                    comp_grid = _grid_grib(c, tc, var)
                    reqs.append(comp_grid)
    yield reqs


@tasks
def grids_baseline(c: Config):
    taskname = "Baseline grids for %s" % c.baseline.name
    yield taskname
    yield grids(c, baseline=True, forecast=False)


@tasks
def grids_forecast(c: Config):
    taskname = "Forecast grids for %s" % c.forecast.name
    yield taskname
    yield grids(c, baseline=False, forecast=True)


@tasks
def plots(c: Config):
    taskname = "Plots for %s vs %s" % (c.forecast.name, c.baseline.name)
    yield taskname
    yield [
        _plot(c, cycle, varname, level, stat, width)
        for cycle in c.cycles.values  # noqa: PD011
        for varname, level in _varnames_and_levels(c)
        for stat, width in _stats_and_widths(c, varname)
    ]


@tasks
def stats(c: Config):
    taskname = "Stats for %s vs %s" % (c.forecast.name, c.baseline.name)
    yield taskname
    reqs: list[Node] = []
    for varname, level in _varnames_and_levels(c):
        reqs.extend(_statreqs(c, varname, level))
    yield reqs


# Private tasks


@external
def _existing(path: Path):
    taskname = "Existing path %s" % path
    yield taskname
    yield asset(path, path.exists)


@task
def _forecast_dataset(path: Path):
    taskname = "Forecast dataset %s" % path
    yield taskname
    ds = xr.Dataset()
    yield asset(ds, lambda: bool(ds))
    yield _existing(path)
    logging.info("%s: Opening forecast %s", taskname, path)
    with catch_warnings():
        simplefilter("ignore")
        src = xr.open_dataset(path, decode_timedelta=True)
        ds.update(src)
        ds.attrs.update(src.attrs)


@task
def _grib_index_data(c: Config, outdir: Path, tc: TimeCoords, url: str):
    yyyymmdd, hh, leadtime = tcinfo(tc)
    taskname = "GRIB index data %s %sZ %s" % (yyyymmdd, hh, leadtime)
    yield taskname
    idxdata: dict[str, Var] = {}
    yield asset(idxdata, lambda: bool(idxdata))
    idxfile = _local_file_from_http(outdir, url, "GRIB index file")
    yield idxfile
    lines = idxfile.ref.read_text(encoding="utf-8").strip().split("\n")
    lines.append(":-1:::::")  # end marker
    vxvars = set(_vxvars(c).keys())
    baseline_class = variables.model_class(c.baseline.name)
    for this_record, next_record in pairwise([line.split(":") for line in lines]):
        baseline_var = baseline_class(
            name=this_record[3],
            levstr=this_record[4],
            firstbyte=int(this_record[1]),
            lastbyte=int(next_record[1]) - 1,
        )
        if baseline_var in vxvars:
            idxdata[str(baseline_var)] = baseline_var


@task
def _grid_grib(c: Config, tc: TimeCoords, var: Var):
    yyyymmdd, hh, leadtime = tcinfo(tc)
    url = render(c.baseline.url, tc)
    proximity, src = classify_url(url)
    if proximity == Proximity.LOCAL:
        assert isinstance(src, Path)
        yield "GRIB file %s providing %s grid" % (src, var)
        yield asset(src, src.is_file)
        yield None
    else:
        outdir = c.paths.grids_baseline / yyyymmdd / hh / leadtime
        path = outdir / f"{var}.grib2"
        taskname = "Baseline grid %s" % path
        yield taskname
        yield asset(path, path.is_file)
        idxdata = _grib_index_data(c, outdir, tc, url=f"{url}.idx")
        yield idxdata
        var_idx = idxdata.ref[str(var)]
        fb, lb = var_idx.firstbyte, var_idx.lastbyte
        headers = {"Range": "bytes=%s" % (f"{fb}-{lb}" if lb else fb)}
        fetch(taskname, url, path, headers)


@task
def _grid_nc(c: Config, varname: str, tc: TimeCoords, var: Var):
    yyyymmdd, hh, leadtime = tcinfo(tc)
    path = c.paths.grids_forecast / yyyymmdd / hh / leadtime / f"{var}.nc"
    taskname = "Forecast grid %s" % path
    yield taskname
    yield asset(path, path.is_file)
    fd = _forecast_dataset(Path(render(c.forecast.path, tc)))
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
    yield asset(path, path.is_file)
    yield None
    fetch(taskname, url, path)


@task
def _netcdf_from_prepbufr(c: Config, tc: TimeCoords):
    yyyymmdd, hh, _ = tcinfo(tc)
    taskname = "netCDF from prepbufr at %s %sZ" % (yyyymmdd, hh)
    yield taskname
    rundir = c.paths.run / "obs" / yyyymmdd / hh
    url = render(c.baseline.url, tc)
    netcdf = (rundir / url.split("/")[-1]).with_suffix(".nc")
    yield asset(netcdf, netcdf.is_file)
    config = Path("/work/point/pb2nc.config")  # PM GENERATE CONFIG INSTEAD
    prepbufr = _local_file_from_http(c.paths.obs / yyyymmdd / hh, url, "prepbufr file")
    yield [_existing(config), prepbufr]
    runscript = netcdf.with_suffix(".sh")
    content = f"pb2nc -v 4 {prepbufr.ref} {netcdf} {config} >{netcdf.stem}.log 2>&1"
    _write_runscript(runscript, content)
    mpexec(str(runscript), rundir, taskname)


@task
def _polyfile(path: Path, mask: tuple[tuple[float, float]]):
    taskname = "Poly file %s" % path
    yield taskname
    yield asset(path, path.is_file)
    yield None
    content = "MASK\n%s\n" % "\n".join(f"{lat} {lon}" for lat, lon in mask)
    with atomic(path) as tmp:
        tmp.write_text(content)


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
    yield asset(path, path.is_file)
    reqs = _statreqs(c, varname, level, cycle)
    yield reqs
    leadtimes = ["%03d" % (td.total_seconds() // 3600) for td in c.leadtimes.values]  # noqa: PD011
    plot_data = _prepare_plot_data(reqs, stat, width)
    sns.set(style="darkgrid")
    plt.figure(figsize=(10, 6), constrained_layout=True)
    hue = "LABEL" if "LABEL" in plot_data.columns else "MODEL"
    sns.lineplot(data=plot_data, x="FCST_LEAD", y=stat, hue=hue, marker="o", linewidth=2)
    w = f"(width={width}) " if width else ""
    plt.title(
        "%s %s %s%s vs %s at %s" % (desc, stat, w, c.forecast.name, c.baseline.name, cyclestr)
    )
    plt.xlabel("Leadtime")
    plt.ylabel(f"{stat} ({meta.units})")
    plt.xticks(ticks=[int(lt) for lt in leadtimes], labels=leadtimes, rotation=90)
    plt.legend(title="Model", bbox_to_anchor=(1.02, 1), loc="upper left")
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, bbox_inches="tight")
    plt.close()


@task
def _stats_vs_grid(c: Config, varname: str, tc: TimeCoords, var: Var, prefix: str, source: Source):
    yyyymmdd, hh, leadtime = tcinfo(tc)
    source_name = {Source.BASELINE: "baseline", Source.FORECAST: "forecast"}[source]
    taskname = "Stats vs grid for %s %s at %s %sZ %s" % (source_name, var, yyyymmdd, hh, leadtime)
    yield taskname
    rundir = c.paths.run / "stats" / yyyymmdd / hh / leadtime
    yyyymmdd_valid, hh_valid, _ = tcinfo(TimeCoords(tc.validtime))
    template = "grid_stat_%s_%02d0000L_%s_%s0000V.stat"
    path = rundir / (template % (prefix, int(leadtime), yyyymmdd_valid, hh_valid))
    yield asset(path, path.is_file)
    baseline = _grid_grib(c, TimeCoords(cycle=tc.validtime, leadtime=0), var)
    forecast = _grid_nc(c, varname, tc, var)
    toverify = _grid_grib(c, tc, var) if source == Source.BASELINE else forecast
    reqs = [toverify, baseline]
    if source == Source.BASELINE:
        reqs.append(forecast)
    polyfile = None
    if mask := c.forecast.mask:
        polyfile = _polyfile(c.paths.run / "stats" / "mask.poly", mask)
        reqs.append(polyfile)
    yield reqs
    cfgfile = path.with_suffix(".config")
    _grid_stat_config(c, cfgfile, varname, rundir, var, prefix, source, polyfile)
    runscript = path.with_suffix(".sh")
    content = f"""
    export OMP_NUM_THREADS=1
    grid_stat -v 4 {toverify.ref} {baseline.ref} {cfgfile} >{path.stem}.log 2>&1
    """
    _write_runscript(runscript, content)
    mpexec(str(runscript), rundir, taskname)


# PM DRY OUT ^ and v


@task
def _stats_vs_obs(c: Config, varname: str, tc: TimeCoords, var: Var, prefix: str):
    yyyymmdd, hh, leadtime = tcinfo(tc)
    taskname = "Stats vs obs for %s %s at %s %sZ %s" % ("forecast", var, yyyymmdd, hh, leadtime)
    yield taskname
    rundir = c.paths.run / "stats" / yyyymmdd / hh / leadtime
    template = "point_stat_%s_%02d0000L_%s_%s0000V.stat"
    yyyymmdd_valid, hh_valid, _ = tcinfo(TimeCoords(tc.validtime))
    path = rundir / (template % (prefix, int(leadtime), yyyymmdd_valid, hh_valid))
    yield asset(path, path.is_file)
    fcst = _grid_nc(c, varname, tc, var)
    obs = _netcdf_from_prepbufr(c, tc)
    config = _existing(Path("/work/point/pointstat.config"))  # PM GENERATE CONFIG INSTEAD
    yield [fcst, obs, config]
    runscript = fcst.ref.with_suffix(".sh")
    cmd = "point_stat -v 4 {fcst} {obs} {config} -outdir {rundir} >{log} 2>&1".format(
        fcst=fcst.ref, obs=obs.ref, config=config.ref, rundir=rundir, log=f"{fcst.ref.stem}.log"
    )
    _write_runscript(runscript, cmd)
    mpexec(str(runscript), rundir, taskname)


# Support


def _grid_stat_config(
    c: Config,
    path: Path,
    varname: str,
    rundir: Path,
    var: Var,
    prefix: str,
    source: Source,
    polyfile: Node | None,
):
    level_obs = metlevel(var.level_type, var.level)
    baseline_class = variables.model_class(c.baseline.name)
    attrs = {
        Source.BASELINE: (level_obs, baseline_class.varname(var.name), c.baseline.name),
        Source.FORECAST: ("(0,0,*,*)", varname, c.forecast.name),
    }
    level_fcst, name_fcst, model = attrs[source]
    field_fcst = {"level": [level_fcst], "name": name_fcst, "set_attr_level": level_obs}
    field_obs = {"level": [level_obs], "name": baseline_class.varname(var.name)}
    meta = _meta(c, varname)
    if meta.cat_thresh:
        for x in field_fcst, field_obs:
            x["cat_thresh"] = meta.cat_thresh
    if meta.cnt_thresh:
        for x in field_fcst, field_obs:
            x["cnt_thresh"] = meta.cnt_thresh
    mask_grid = [] if polyfile else ["FULL"]
    mask_poly = [polyfile.ref] if polyfile else []
    config = {
        "fcst": {"field": [field_fcst]},
        "mask": {"grid": mask_grid, "poly": mask_poly},
        "model": model,
        "nc_pairs_flag": "FALSE",
        "obs": {"field": [field_obs]},
        "obtype": c.baseline.name,
        "output_flag": dict.fromkeys(sorted({LINETYPE[x] for x in meta.met_stats}), "BOTH"),
        "output_prefix": f"{prefix}",
        "regrid": {"method": c.regrid.method, "to_grid": c.regrid.to},
        "tmp_dir": rundir,
    }
    if nbrhd := {k: v for k, v in [("shape", meta.nbrhd_shape), ("width", meta.nbrhd_width)] if v}:
        config["nbrhd"] = nbrhd
    with atomic(path) as tmp:
        tmp.write_text("%s\n" % render_metconf(config))


def _meta(c: Config, varname: str) -> VarMeta:
    return VARMETA[c.variables[varname]["name"]]


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


def _statargs(
    c: Config, varname: str, level: float | None, source: Source, cycle: datetime | None = None
) -> Iterator:
    if isinstance(cycle, datetime):
        start = cycle.strftime("%Y-%m-%dT%H:%M:%S")
        step = "00:00:00"
        stop = start
        cycles = Cycles(dict(start=start, step=step, stop=stop))
    else:
        cycles = c.cycles
    name = (c.baseline if source == Source.BASELINE else c.forecast).name.lower()
    prefix = lambda var: "%s_%s" % (name, str(var).replace("-", "_"))
    args = [
        (c, vn, tc, var, prefix(var), source)
        for (var, vn), tc in product(_vxvars(c).items(), gen_validtimes(cycles, c.leadtimes))
        if vn == varname and var.level == level
    ]
    return iter(sorted(args))


def _statreqs(
    c: Config, varname: str, level: float | None, cycle: datetime | None = None
) -> Sequence[Node]:
    genreqs = lambda source: [
        _stats_vs_grid(*args) for args in _statargs(c, varname, level, source, cycle)
    ]
    reqs: Sequence[Node] = genreqs(Source.FORECAST)
    if c.baseline.compare:
        reqs = [*reqs, *genreqs(Source.BASELINE)]
    return reqs


def _stats_and_widths(c: Config, varname) -> Iterator[tuple[str, int | None]]:
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


def _varnames_and_levels(c: Config) -> Iterator[tuple[str, float | None]]:
    return iter(
        (varname, level)
        for varname, attrs in c.variables.items()
        for level in attrs.get("levels", [None])
    )


@cache
def _vxvars(c: Config) -> dict[Var, str]:
    return {
        Var(attrs["name"], attrs["level_type"], level): varname
        for varname, attrs in c.variables.items()
        for level in attrs.get("levels", [None])
    }


def _write_runscript(path: Path, content: str) -> None:
    # PM WRITE UNIT TEST FOR THIS.
    with atomic(path) as tmp:
        tmp.write_text("#!/usr/bin/env bash\n\n%s\n" % dedent(content).strip())
    path.chmod(path.stat().st_mode | S_IEXEC)
