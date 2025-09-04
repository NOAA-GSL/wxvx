"""
Tests for wxvx.cli.
"""

import logging
import re
from pathlib import Path
from textwrap import dedent
from unittest.mock import DEFAULT as D
from unittest.mock import patch

import yaml
from pytest import mark, raises

import wxvx
from wxvx import cli
from wxvx.types import Config
from wxvx.util import WXVXError, pkgname, resource_path

# Tests


@mark.parametrize("switch_c", ["-c", "--config"])
@mark.parametrize("switch_n", ["-n", "--threads"])
@mark.parametrize("switch_t", ["-t", "--task"])
def test_cli_main(config_data, fs, switch_c, switch_n, switch_t):
    fs.add_real_file(resource_path("config.jsonschema"))
    fs.add_real_file(resource_path("info.json"))
    with patch.multiple(cli, workflow=D, sys=D, use_uwtools_logger=D) as mocks:
        cf = fs.create_file("/path/to/config.yaml", contents=yaml.safe_dump(config_data))
        argv = [pkgname, switch_c, cf.path, switch_n, "2", switch_t, "plots"]
        mocks["sys"].argv = argv
        with patch.object(cli, "_parse_args", wraps=cli._parse_args) as _parse_args:
            cli.main()
        _parse_args.assert_called_once_with(argv)
    mocks["use_uwtools_logger"].assert_called_once_with(verbose=False)
    mocks["workflow"].plots.assert_called_once_with(Config(config_data), threads=2)


def test_cli_main__bad_config(fakefs, fs):
    fs.add_real_file(resource_path("config.jsonschema"))
    fs.add_real_file(resource_path("info.json"))
    bad_config = fakefs / "config.yaml"
    bad_config.write_text("{}")
    with (
        patch.object(cli.sys, "argv", [pkgname, "-c", str(bad_config), "-t", "grids"]),
        raises(SystemExit) as e,
    ):
        cli.main()
    assert e.value.code == 1


@mark.parametrize("switch", ["-k", "--check"])
def test_cli_main__check_config(fs, switch):
    fs.add_real_file(resource_path("config.jsonschema"))
    fs.add_real_file(resource_path("config-grid.yaml"))
    fs.add_real_file(resource_path("info.json"))
    argv = [pkgname, switch, "-c", str(resource_path("config-grid.yaml")), "-t", "grids"]
    with (
        patch.object(cli.sys, "argv", argv),
        patch.object(cli, "tasknames", return_value=["grids"]),
        patch.object(cli.workflow, "grids") as grids,
    ):
        cli.main()
    grids.assert_not_called()


def test_cli_main__exception(logged):
    msg = "Oh no!"
    with patch.object(cli, "_parse_args", side_effect=WXVXError(msg)), raises(SystemExit) as e:
        cli.main()
    assert logged(msg)
    assert e.value.code == 1


def test_cli_main__task_list(caplog):
    caplog.set_level(logging.INFO)
    with (
        patch.object(cli.sys, "argv", [pkgname, "-c", str(resource_path("config-grid.yaml"))]),
        patch.object(cli, "use_uwtools_logger"),
    ):
        with raises(SystemExit) as e:
            cli.main()
        assert e.value.code == 0
        expected = """
        Available tasks:
          grids
          grids_baseline
          grids_forecast
          plots
          stats
        """
        for line in dedent(expected).strip().split("\n"):
            assert line in caplog.messages


def test_cli_main__task_missing(caplog):
    caplog.set_level(logging.INFO)
    argv = [pkgname, "-c", str(resource_path("config-grid.yaml")), "-t", "foo"]
    with patch.object(cli.sys, "argv", argv), patch.object(cli, "use_uwtools_logger"):
        with raises(SystemExit) as e:
            cli.main()
        assert e.value.code == 1
        assert "No such task: foo" in caplog.messages


@mark.parametrize("c", ["-c", "--config"])
@mark.parametrize("d", ["-d", "--debug", None])
def test_cli__parse_args(c, d):
    fn = "a.yaml"
    args = cli._parse_args([pkgname, c, fn] + ([d] if d else []))
    assert isinstance(args.config, Path)
    assert str(args.config) == fn
    assert args.debug is bool(d)


@mark.parametrize("h", ["-h", "--help"])
def test_cli__parse_args__help(capsys, h):
    with raises(SystemExit) as e:
        cli._parse_args([pkgname, h])
    assert e.value.code == 0
    assert capsys.readouterr().out.startswith("usage:")


@mark.parametrize("v", ["-v", "--version"])
def test_cli__parse_args__version(capsys, v):
    with raises(SystemExit) as e:
        cli._parse_args([pkgname, v])
    assert e.value.code == 0
    assert re.match(r"^\w+ version \d+\.\d+\.\d+ build \d+$", capsys.readouterr().out.strip())


def test_cli__parse_args__required_arg_missing():
    with raises(SystemExit) as e:
        cli._parse_args([pkgname])
    assert e.value.code == 2


@mark.parametrize("n", ["-n", "--threads"])
def test_cli__parse_args__threads_bad(capsys, n):
    with raises(SystemExit) as e:
        cli._parse_args([pkgname, "-c", "a.yaml", n, "0"])
    assert e.value.code == 1
    assert capsys.readouterr().err.strip() == "Specify at least 1 thread"


def test_cli__version():
    assert re.match(r"^version \d+\.\d+\.\d+ build \d+$", cli._version())


def test_cli_ShowConfig(capsys, fs):
    msg = "testing ShowConfig"
    cf = Path(fs.create_file("config.yaml", contents=msg).path)
    sc = cli.ShowConfig(option_strings=["-s", "--show"], dest="show")
    with patch.object(wxvx.util, "resource_path", return_value=cf):
        with raises(SystemExit) as e:
            sc(None, None, None)
        assert e.value.code == 0
    assert capsys.readouterr().out.strip() == msg
