from __future__ import annotations

from datetime import datetime, timedelta
from itertools import product
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wxvx.types import Cycles, Leadtimes

# Public


class TimeCoords:
    """
    Time coordinates.
    """

    def __init__(self, cycle: datetime, leadtime: int | timedelta = 0):
        self.cycle = cycle.replace(tzinfo=None)  # All wxvx times are UTC
        self.leadtime = timedelta(hours=leadtime) if isinstance(leadtime, int) else leadtime
        self.validtime = self.cycle + self.leadtime
        self.yyyymmdd = yyyymmdd(self.validtime)
        self.hh = hh(self.validtime)

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __hash__(self):
        return int(self.validtime.timestamp())

    def __lt__(self, other):
        return hash(self) < hash(other)

    def __repr__(self):
        return self.validtime.isoformat()


def gen_timecoords(cycles: Cycles, leadtimes: Leadtimes) -> list[TimeCoords]:
    return sorted(
        {
            TimeCoords(cycle=cycle, leadtime=leadtime)
            for cycle, leadtime in product(cycles.values, leadtimes.values)
        }
    )


def hh(dt: datetime) -> str:
    return dt.strftime("%H")


def tcinfo(tc: TimeCoords, leadtime_digits: int = 3) -> tuple[str, str, str]:
    fmt = f"%0{leadtime_digits}d"
    return (yyyymmdd(dt=tc.cycle), hh(dt=tc.cycle), fmt % (tc.leadtime.total_seconds() // 3600))


def yyyymmdd(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")
