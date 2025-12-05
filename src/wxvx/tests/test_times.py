"""
Tests for wxvx.times.
"""

from datetime import timedelta

from pytest import mark

from wxvx import times
from wxvx.strings import S
from wxvx.types import Cycles, Leadtimes

# Tests


@mark.parametrize("leadtime", [timedelta(hours=1), 1])
def test_times_TimeCoords(leadtime, utc):
    cycle = utc(2025, 1, 28, 12)
    tc = times.TimeCoords(cycle=cycle, leadtime=leadtime)
    ltobj = leadtime if isinstance(leadtime, timedelta) else timedelta(hours=leadtime)
    assert hash(tc) == (cycle + ltobj).timestamp()
    assert tc < times.TimeCoords(cycle=cycle, leadtime=timedelta(hours=2))
    assert tc == times.TimeCoords(cycle=cycle, leadtime=timedelta(hours=1))
    assert tc > times.TimeCoords(cycle=cycle, leadtime=timedelta(hours=0))
    assert repr(tc) == "2025-01-28T13:00:00"
    assert str(tc) == "2025-01-28T13:00:00"
    assert tc.hh == "13"
    assert tc.yyyymmdd == "20250128"


def test_times_TimeCoords__no_leadtime(utc):
    cycle = utc(2025, 1, 28, 12)
    tc = times.TimeCoords(cycle=cycle)
    assert hash(tc) == cycle.timestamp()
    assert tc < times.TimeCoords(cycle=cycle, leadtime=timedelta(hours=1))
    assert tc == times.TimeCoords(cycle=cycle, leadtime=timedelta(hours=0))
    assert tc > times.TimeCoords(cycle=cycle, leadtime=timedelta(hours=-1))
    assert repr(tc) == "2025-01-28T12:00:00"
    assert str(tc) == "2025-01-28T12:00:00"
    assert tc.hh == "12"
    assert tc.yyyymmdd == "20250128"


def test_times_gen_validtimes(config_data, utc):
    actual = {
        vt.validtime
        for vt in times.gen_validtimes(
            cycles=Cycles(raw=config_data[S.cycles]),
            leadtimes=Leadtimes(raw=config_data[S.leadtimes]),
        )
    }
    expected = {
        utc(2024, 12, 19, 18),
        utc(2024, 12, 20, 0),
        utc(2024, 12, 20, 6),
        utc(2024, 12, 20, 12),
        utc(2024, 12, 20, 18),
    }
    assert actual == expected


def test_times_hh(utc):
    assert times.hh(utc(2025, 1, 30, 6)) == "06"
    assert times.hh(utc(2025, 1, 30, 18)) == "18"


def test_times_tcinfo(utc):
    cycle = utc(2025, 2, 11, 3)
    leadtime = timedelta(hours=8)
    tc = times.TimeCoords(cycle=cycle, leadtime=leadtime)
    assert times.tcinfo(tc=tc) == ("20250211", "03", "008")
    assert times.tcinfo(tc=tc, leadtime_digits=2) == ("20250211", "03", "08")


def test_times_yyyymmdd(utc):
    assert times.yyyymmdd(utc(2025, 1, 30, 18)) == "20250130"
