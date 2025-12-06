"""
Tests for wxvx.cli.
"""

import logging
import re
from argparse import ArgumentTypeError, Namespace
from pathlib import Path
from unittest.mock import DEFAULT as D
from unittest.mock import patch

import yaml
from pytest import mark, raises

from wxvx import cli
from wxvx.strings import S
from wxvx.types import Config
from wxvx.util import WXVXError, pkgname, resource_path

# Tests


@mark.parametrize("switch_c", ["-c", "--config"])
@mark.parametrize("switch_n", ["-n", "--threads"])
@mark.parametrize("switch_t", ["-t", "--task"])
@mark.parametrize("threads", [1, 2])
def test_cli_main(config_data, fs, logged, switch_c, switch_n, switch_t, threads):
    fs.add_real_file(resource_path("config.jsonschema"))
    fs.add_real_file(resource_path("info.json"))
    with patch.multiple(cli, workflow=D, sys=D, use_uwtools_logger=D) as mocks:
        cf = fs.create_file("/path/to/config.yaml", contents=yaml.safe_dump(config_data))
        argv = [pkgname, switch_c, cf.path, switch_n, str(threads), switch_t, S.plots]
        mocks["sys"].argv = argv
        with patch.object(cli, "_parse_args", wraps=cli._parse_args) as _parse_args:
            cli.main()
        _parse_args.assert_called_once_with(argv)
    mocks["use_uwtools_logger"].assert_called_once_with(verbose=False)
    mocks["workflow"].plots.assert_called_once_with(Config(config_data), threads=threads)
    if threads > 1:
        assert logged("Using %s threads" % threads)
    else:
        assert not logged(r"Using \d+ threads")


def test_cli_main__bad_config(fakefs, fs):
    fs.add_real_file(resource_path("config.jsonschema"))
    fs.add_real_file(resource_path("info.json"))
    bad_config = fakefs / "config.yaml"
    bad_config.write_text("{}")
    with (
        patch.object(cli.sys, "argv", [pkgname, "-c", str(bad_config), "-t", S.grids]),
        raises(SystemExit) as e,
    ):
        cli.main()
    assert e.value.code == 1


@mark.parametrize("switch", ["-k", "--check"])
@mark.parametrize("truthtype", [S.grid, S.point])
def test_cli_main__check_config(fs, switch, truthtype):
    fn = "config-%s.yaml" % truthtype
    fs.add_real_file(resource_path("config.jsonschema"))
    fs.add_real_file(resource_path("info.json"))
    fs.add_real_file(resource_path(fn))
    argv = [pkgname, switch, "-c", str(resource_path(fn)), "-t", S.grids]
    with (
        patch.object(cli.sys, "argv", argv),
        patch.object(cli, "tasknames", return_value=[S.grids]),
        patch.object(cli.workflow, S.grids) as grids,
        raises(SystemExit) as e,
    ):
        cli.main()
    grids.assert_not_called()
    assert e.value.code == 0


def test_cli_main__exception(logged):
    msg = "Oh no!"
    with patch.object(cli, "_parse_args", side_effect=WXVXError(msg)), raises(SystemExit) as e:
        cli.main()
    assert logged(msg)
    assert e.value.code == 1


@mark.parametrize("switch", ["-l", "--list"])
def test_cli_main__task_list(caplog, switch, tidy):
    caplog.set_level(logging.INFO)
    with (
        patch.object(
            cli.sys, "argv", [pkgname, "-c", str(resource_path("config-grid.yaml")), switch]
        ),
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
          grids_truth
          ncobs
          obs
          plots
          stats
        """
        assert re.sub(r"INFO     [^ ]+ ", "", caplog.text.strip()) == tidy(expected)


@mark.parametrize("check", [True, False])
@mark.parametrize("switch", ["-s", "--show"])
def test_cli_main__show_config(capsys, check, fs, switch):
    fn = "config-grid.yaml"
    fs.add_real_file(resource_path("config.jsonschema"))
    fs.add_real_file(resource_path("info.json"))
    fs.add_real_file(resource_path(fn))
    argv = [pkgname, switch, "-c", str(resource_path(fn))]
    if check:
        argv.append("--check")
    with patch.object(cli.sys, "argv", argv), raises(SystemExit):
        cli.main()
    assert isinstance(yaml.safe_load(capsys.readouterr().out), dict)


def test_cli_main__task_missing(caplog):
    caplog.set_level(logging.INFO)
    argv = [pkgname, "-c", str(resource_path("config-grid.yaml")), "-t", "foo"]
    with patch.object(cli.sys, "argv", argv), patch.object(cli, "use_uwtools_logger"):
        with raises(SystemExit) as e:
            cli.main()
        assert e.value.code == 1
        assert "No such task: foo" in caplog.messages


def test_cli__arg_type_int_greater_than_zero__pass():
    assert cli._arg_type_int_greater_than_zero("42") == 42


@mark.parametrize("val", ["foo", 0])
def test_cli__arg_type_int_greater_than_zero__fail(val):
    with raises(ArgumentTypeError) as e:
        cli._arg_type_int_greater_than_zero(val)
    assert str(e.value) == "Integer > 0 required"


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


@mark.parametrize("n", ["-n", "--threads"])
def test_cli__parse_args__threads_bad(capsys, n):
    with raises(SystemExit) as e:
        cli._parse_args([pkgname, "-c", "a.yaml", n, "0"])
    assert e.value.code == 2
    assert "argument -n/--threads: Integer > 0 required" in capsys.readouterr().err


def test_cli__process_args__bad_task(logged):
    kwargs = dict(check=False, config=Path("/some/path"), list=False, show=False, task="foo")
    with patch.object(cli, "_show_tasks") as _show_tasks, raises(SystemExit) as e:
        cli._process_args(args=Namespace(**kwargs))
    assert e.value.code == 1
    _show_tasks.assert_called_once_with()
    assert logged("No such task: foo")


def test_cli__process_args__list_and_check():
    args = Namespace(check=True, config=Path("/some/path"), list=True)
    with patch.object(cli, "_show_tasks") as _show_tasks:
        cli._process_args(args=args)
    _show_tasks.assert_called_once_with()


def test_cli__process_args__no_config(logged):
    args = Namespace(check=True, config=None, list=True)
    with raises(SystemExit) as e:
        cli._process_args(args=args)
    assert e.value.code == 1
    assert logged("No configuration file specified")


def test_cli__process_args__only_check():
    args = Namespace(check=True, config=Path("/some/path"), list=False, show=False)
    with patch.object(cli, "_show_tasks") as _show_tasks:
        cli._process_args(args=args)
    _show_tasks.assert_not_called()


def test_cli__process_args__only_list():
    args = Namespace(check=False, list=True, show=False)
    with patch.object(cli, "_show_tasks") as _show_tasks, raises(SystemExit) as e:
        cli._process_args(args=args)
    assert e.value.code == 0
    _show_tasks.assert_called_once_with()


def test_cli__process_args__only_show():
    args = Namespace(check=True, config=Path("/some/path"), list=False, show=True)
    with patch.object(cli, "_show_tasks") as _show_tasks:
        cli._process_args(args=args)
    _show_tasks.assert_not_called()
