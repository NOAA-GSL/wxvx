"""
Tests for wxvx.times.
"""

from datetime import timedelta

from pytest import mark

from wxvx import times
from wxvx.strings import S
from wxvx.types import Cycles, Leadtimes

# Tests


@mark.parametrize(S.leadtime, [timedelta(hours=1), 1])
def test_times_TimeCoords(leadtime, utc):
    cycle = utc(2025, 1, 28, 12)
    tc = times.TimeCoords(cycle=cycle, leadtime=leadtime)
    assert hash(tc) == hash((cycle.timestamp(), 3600))
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
    assert hash(tc) == hash((cycle.timestamp(), 0))
    assert tc < times.TimeCoords(cycle=cycle, leadtime=timedelta(hours=1))
    assert tc == times.TimeCoords(cycle=cycle, leadtime=timedelta(hours=0))
    assert tc > times.TimeCoords(cycle=cycle, leadtime=timedelta(hours=-1))
    assert repr(tc) == "2025-01-28T12:00:00"
    assert str(tc) == "2025-01-28T12:00:00"
    assert tc.hh == "12"
    assert tc.yyyymmdd == "20250128"


def test_times_gen_timecoords(config_data, utc):
    actual = times.gen_timecoords(
        cycles=Cycles(raw=config_data[S.cycles]),
        leadtimes=Leadtimes(raw=config_data[S.leadtimes]),
    )
    expected = [
        times.TimeCoords(cycle=utc(2024, 12, 19, 18), leadtime=0),
        times.TimeCoords(cycle=utc(2024, 12, 19, 18), leadtime=6),
        times.TimeCoords(cycle=utc(2024, 12, 19, 18), leadtime=12),
        times.TimeCoords(cycle=utc(2024, 12, 20, 6), leadtime=0),
        times.TimeCoords(cycle=utc(2024, 12, 20, 6), leadtime=6),
        times.TimeCoords(cycle=utc(2024, 12, 20, 6), leadtime=12),
    ]
    assert actual == expected


def test_times_gen_timecoords_truth(config_data, utc):
    actual = times.gen_timecoords_truth(
        cycles=Cycles(raw=config_data[S.cycles]),
        leadtimes=Leadtimes(raw=config_data[S.leadtimes]),
    )
    expected = [
        times.TimeCoords(cycle=utc(2024, 12, 19, 18), leadtime=0),
        times.TimeCoords(cycle=utc(2024, 12, 20, 0), leadtime=0),
        times.TimeCoords(cycle=utc(2024, 12, 20, 6), leadtime=0),
        times.TimeCoords(cycle=utc(2024, 12, 20, 12), leadtime=0),
        times.TimeCoords(cycle=utc(2024, 12, 20, 18), leadtime=0),
    ]
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
