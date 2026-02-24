from __future__ import annotations

import json
import logging
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from enum import Enum, auto
from functools import cache
from importlib import resources
from multiprocessing.pool import Pool
from pathlib import Path
from signal import SIG_IGN, SIGINT, signal
from subprocess import CompletedProcess, run
from typing import TYPE_CHECKING, NoReturn, cast, overload
from urllib.parse import urlparse

import jinja2
import netCDF4
import zarr

from wxvx.strings import MET, S
from wxvx.times import tcinfo

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from wxvx.times import TimeCoords

# The pool must be initialized via initialize_pool() before mpexec() is called. The 'processes'
# argument should be the number of threads in use, so the call is made from wxvx.cli.main() where
# this is known.

_STATE: dict = {}

pkgname = __name__.split(".", maxsplit=1)[0]


class DataFormat(Enum):
    BUFR = auto()
    GRIB = auto()
    NETCDF = auto()
    ZARR = auto()
    UNKNOWN = auto()


class Proximity(Enum):
    LOCAL = auto()
    REMOTE = auto()


LINETYPE = {
    MET.FSS: MET.nbrcnt,
    MET.ME: MET.cnt,
    MET.PODY: MET.cts,
    MET.RMSE: MET.cnt,
}


class WXVXError(Exception): ...


@contextmanager
def atomic(path: Path) -> Iterator[Path]:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path("%s.tmp" % path)
    yield tmp
    tmp.rename(path)


@cache
def classify_data_format(path: str | Path) -> DataFormat:
    def check(f: Callable) -> bool:
        try:
            f()
        except Exception as e:
            for line in str(e).split():
                logging.debug(line)
            return False
        return True

    def grib(path: Path) -> None:
        # It might be better to just try to read the file with a GRIB library like cfgrib, but this
        # tends to be unacceptably slow: Since a GRIB file is just a series of messages without any
        # kind of header/metadata, cfgrib et al. read the entire file. Instead, inspect the initial
        # bytes in the file to see if it is apparently GRIB.
        with path.open(mode="rb") as f:
            header = f.read(8)
        editions = (1, 2)
        apparently_grib = header[:4] == b"GRIB" and header[7] in editions
        assert apparently_grib

    path = Path(path)
    if not path.exists():
        logging.warning("Path not found: %s", path)
        return DataFormat.UNKNOWN
    if check(lambda: zarr.open(path, mode="r")):
        return DataFormat.ZARR
    if check(lambda: netCDF4.Dataset(path, mode="r")):
        return DataFormat.NETCDF
    if check(lambda: grib(path)):
        return DataFormat.GRIB

    logging.error("Could not determine format of: %s", path)
    return DataFormat.UNKNOWN


def classify_url(url: str) -> tuple[Proximity, str | Path]:
    p = urlparse(url)
    if p.scheme in {"http", "https"}:
        return Proximity.REMOTE, url
    if p.scheme in {"file", ""}:
        return Proximity.LOCAL, Path(p.path if p.scheme else url)
    msg = f"Scheme '{p.scheme}' in '{url}' not supported."
    raise WXVXError(msg)


@overload
def expand(start: datetime, step: timedelta, stop: datetime) -> list[datetime]: ...
@overload
def expand(start: timedelta, step: timedelta, stop: timedelta) -> list[timedelta]: ...
def expand(start, step, stop):
    if stop < start:
        raise WXVXError("Stop time %s precedes start time %s" % (stop, start))
    xs = [start]
    while (x := xs[-1]) < stop:
        xs.append(x + step)
    return xs


def fail(msg: str | None = None, *args) -> NoReturn:
    if msg:
        logging.error(msg, *args)
    finalize_pool()
    sys.exit(1)


def finalize_pool() -> None:
    # Only call from a serial context. See the "Warning" section in:
    # https://docs.python.org/3/library/multiprocessing.html#multiprocessing.pool.Pool
    if pool := _STATE.get(S.pool):
        pool.close()
        pool.terminate()
        pool.join()


def initialize_pool(processes: int) -> None:
    _STATE[S.pool] = Pool(processes=processes, initializer=signal, initargs=(SIGINT, SIG_IGN))


def mpexec(cmd: str, rundir: Path, taskname: str, env: dict | None = None) -> CompletedProcess:
    logging.info("%s: Running in %s: %s", taskname, rundir, cmd)
    rundir.mkdir(parents=True, exist_ok=True)
    kwds = {"capture_output": True, "check": False, "cwd": rundir, "shell": True, "text": True}
    if env:
        kwds[S.env] = env
    result: CompletedProcess = _STATE[S.pool].apply(run, (cmd,), kwds)  # i.e. subprocess.run
    if result.returncode != 0:
        logging.error("%s: %s", taskname, result)
    return result


def render(template: str, tc: TimeCoords, context: dict | None = None) -> str:
    yyyymmdd, hh, leadtime = tcinfo(tc)
    timevars = {
        S.yyyymmdd: yyyymmdd,
        S.hh: hh,
        S.fh: int(leadtime),
        S.cycle: tc.cycle,
        S.leadtime: tc.leadtime,
    }
    ctx = context or {}
    ctx.update(timevars)
    env = jinja2.Environment(autoescape=True)
    env.filters.update({S.env: lambda x: os.environ[x]})
    return env.from_string(template).render(**ctx)


def resource(relpath: str | Path) -> str:
    return resource_path(relpath).read_text()


def resource_path(relpath: str | Path) -> Path:
    return cast(Path, resources.files(f"{pkgname}.resources").joinpath(str(relpath)))


def to_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def to_timedelta(value: str | int) -> timedelta:
    if isinstance(value, int):
        return timedelta(hours=value)
    keys = ["hours", "minutes", "seconds"]
    args = dict(zip(keys, map(int, value.split(":")), strict=False))
    return timedelta(**args)


def version() -> str:
    info = json.loads(resource("info.json"))
    return "version %s build %s" % (info["version"], info["buildnum"])
