"""
Tests for wxvx.util.
"""

import logging
import os
import re
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from pytest import mark, raises

from wxvx import util
from wxvx.strings import S
from wxvx.times import TimeCoords

# Tests


def test_util_atomic(fakefs):
    greeting, recipient = [fakefs / f"out.{x}" for x in ("greeting", "recipient")]
    assert not greeting.is_file()
    assert not recipient.is_file()
    s1, s2 = "hello", "world"
    with util.atomic(greeting) as tmp1:
        with util.atomic(recipient) as tmp2:
            assert tmp2 != tmp1
            tmp1.write_text(s1)
            tmp2.write_text(s2)
            assert tmp1.is_file()
            assert tmp2.is_file()
        assert not tmp2.is_file()
    assert not tmp1.is_file()
    assert greeting.read_text() == s1
    assert recipient.read_text() == s2


@mark.parametrize(
    ("expected", "inferred"),
    [
        (util.DataFormat.BUFR, "Binary Universal Form data (BUFR) Edition 3"),
        (util.DataFormat.GRIB, "Gridded binary (GRIB) version 2"),
        (util.DataFormat.NETCDF, "Hierarchical Data Format (version 5) data"),
    ],
)
def test_util_classify_data_format__file(expected, fakefs, inferred):
    path = fakefs / "datafile"
    path.touch()
    with patch.object(util.magic, "from_file", return_value=inferred):
        assert util.classify_data_format(path=path) == expected


def test_util_classify_data_format__file_missing(fakefs, logged):
    path = fakefs / "no-souch-file"
    assert util.classify_data_format(path=path) == util.DataFormat.UNKNOWN
    assert logged(f"Path not found: {path}")


def test_util_classify_data_format__file_unrecognized(fakefs):
    path = fakefs / "datafile"
    path.touch()
    with (
        patch.object(util.magic, "from_file", return_value="What Is This I Don't Even"),
        raises(util.WXVXError) as e,
    ):
        util.classify_data_format(path=path)
    assert str(e.value) == f"Could not determine format of {path}"


def test_util_classify_data_format__zarr(fakefs):
    path = fakefs / "datadir"
    path.mkdir()
    with patch.object(util.zarr, "open"):
        assert util.classify_data_format(path=path) == util.DataFormat.ZARR


def test_util_classify_data_format__zarr_corrupt(fakefs):
    path = fakefs / "datadir"
    path.mkdir()
    with (
        patch.object(util.zarr, "open", side_effect=Exception("failure")),
        raises(util.WXVXError) as e,
    ):
        util.classify_data_format(path=path)
    assert str(e.value) == f"Could not determine format of {path}"


def test_util_classify_data_format__zarr_missing(fakefs, logged):
    path = fakefs / "no-such-dir"
    assert util.classify_data_format(path=path) == util.DataFormat.UNKNOWN
    assert logged(f"Path not found: {path}")


@mark.parametrize(
    (S.url, "expected_scheme"),
    [
        ("http://example.com/path/to/gfs.t00z.pgrb2.0p25.f001", util.Proximity.REMOTE),
        ("file:///path/to/gfs.t00z.pgrb2.0p25.f001", util.Proximity.LOCAL),
        ("/path/to/gfs.t00z.pgrb2.0p25.f001", util.Proximity.LOCAL),
    ],
)
def test_workflow_classify_url(expected_scheme, url):
    scheme, _ = util.classify_url(url)
    assert scheme == expected_scheme


def test_workflow_classify_url_unsupported():
    url = "foo:///path/to/gfs.t00z.pgrb2.0p25.f000"
    with raises(util.WXVXError) as e:
        util.classify_url(url)
    assert str(e.value) == f"Scheme 'foo' in '{url}' not supported."


def test_util_expand_basic(utc):
    start = utc(2024, 12, 19, 12, 0)
    step = timedelta(hours=6)
    stop = utc(2024, 12, 20, 6, 0)
    assert util.expand(start=start, stop=stop, step=step) == [
        utc(2024, 12, 19, 12, 0),
        utc(2024, 12, 19, 18, 0),
        utc(2024, 12, 20, 0, 0),
        utc(2024, 12, 20, 6, 0),
    ]


def test_util_expand_degenerate_one(utc):
    start = utc(2024, 12, 19, 12, 0)
    step = timedelta(hours=6)
    stop = utc(2024, 12, 19, 12, 0)
    assert util.expand(start=start, step=step, stop=stop) == [utc(2024, 12, 19, 12, 0)]


def test_util_expand_stop_precedes_start(utc):
    start = utc(2024, 12, 19, 12, 0)
    step = timedelta(hours=6)
    stop = utc(2024, 12, 19, 6, 0)
    with raises(util.WXVXError) as e:
        util.expand(start=start, step=step, stop=stop)
    assert str(e.value) == "Stop time 2024-12-19 06:00:00 precedes start time 2024-12-19 12:00:00"


def test_util_fail(caplog):
    caplog.set_level(logging.INFO)
    with raises(SystemExit) as e:
        util.fail()
    assert not caplog.messages
    with raises(SystemExit) as e:
        util.fail("foo")
    assert "foo" in caplog.messages
    with raises(SystemExit) as e:
        util.fail("foo %s", "bar")
    assert "foo bar" in caplog.messages
    assert e.value.code == 1


@mark.parametrize("env", [{"PI": "3.14"}, None])
@mark.parametrize("delpool", [True, False])
def test_util_mpexec(delpool, env, tmp_path):
    # Manipulating the multiprocessing Pool here is safe because pytest-xdist parallelizes across
    # *processes*, and each process has its own memory space, and tests run serially within each
    # process, so if this test is running then no other test is modifying the state / pool.
    util._initpool()
    if delpool:
        del util._STATE[S.pool]
    path = tmp_path / "out"
    cmd = 'echo "$PI" | tee %s' % path
    result = util.mpexec(cmd=cmd, rundir=tmp_path, taskname="foo", env=env)
    assert result.stderr == ""
    expected = "3.14" if env else ""
    assert result.stdout.strip() == expected
    assert path.read_text().strip() == expected


def test_util_mpexec__fail(tmp_path):
    result = util.mpexec(cmd="echo good && echo bad >&2 && false", rundir=tmp_path, taskname="foo")
    assert result.stdout.strip() == "good"
    assert result.stderr.strip() == "bad"
    assert result.returncode == 1


def test_util_render(utc):
    template = "{{ yyyymmdd }}-{{ yyyymmdd[:4] }}-{{ hh }}-{{ '%03d' % fh }}"
    tc = TimeCoords(cycle=utc(2025, 8, 21, 6), leadtime=1)
    assert util.render(template, tc) == "20250821-2025-06-001"


def test_util_render_with_context(utc):
    template = "{{ meta.workdir }}/file_{{ yyyymmdd }}{{ hh }}_f{{ '%03d' % fh }}.nc"
    tc = TimeCoords(cycle=utc(2025, 8, 21, 6), leadtime=1)
    ctx = {"meta": {"workdir": "/meta/dir"}}
    assert util.render(template, tc, context=ctx) == "/meta/dir/file_2025082106_f001.nc"


def test_util_render_with_cycle(utc):
    template = "{{ cycle.strftime('%Y%m%d') }}-{{ (cycle + leadtime).strftime('%H') }}"
    tc = TimeCoords(cycle=utc(2025, 8, 21, 6), leadtime=1)
    assert util.render(template, tc) == "20250821-07"


def test_util_render_with_env_var(utc):
    template = '{{ "FOO" | env }}-{{ cycle.strftime("%Y%m%d") }}'
    tc = TimeCoords(cycle=utc(2025, 8, 21, 6), leadtime=1)
    with patch.object(os, "environ", {"FOO": "bar"}):
        assert util.render(template, tc) == "bar-20250821"


def test_util_resource(fs):
    expected = "bar"
    path = Path(fs.create_file("/path/to/foo", contents=expected).path)
    with patch.object(util.resources, "as_file", return_value=path.parent):
        assert util.resource(path) == expected


def test_util_resource_path():
    assert str(util.resource_path("foo")).endswith("%s/resources/foo" % util.pkgname)


def test_util_shutdown():
    # See safety note in mpexec() test.
    pool = Mock()
    with patch.dict(util._STATE, {S.pool: pool}):
        util.shutdown()
    pool.close.assert_called_once_with()
    pool.terminate.assert_called_once_with()


def test_util_to_datetime(utc):
    expected = utc(2025, 6, 4, 12)
    assert util.to_datetime(value="2025-06-04T12:00:00") == expected
    assert util.to_datetime(value=expected) == expected


def test_util_to_timedelta():
    assert util.to_timedelta(value="01:02:03") == timedelta(hours=1, minutes=2, seconds=3)
    assert util.to_timedelta(value="168:00:00") == timedelta(days=7)


def test_util_version():
    assert re.match(r"^version \d+\.\d+\.\d+ build \d+$", util.version())
