import json
import logging
import sys
import traceback
from argparse import Action, ArgumentParser, HelpFormatter, Namespace
from pathlib import Path
from typing import NoReturn

from iotaa import tasknames
from uwtools.api.config import get_yaml_config, validate
from uwtools.api.logging import use_uwtools_logger

from wxvx import workflow
from wxvx.types import Config
from wxvx.util import WXVXError, fail, pkgname, resource, resource_path

# Public


def main() -> None:
    try:
        args = _parse_args(sys.argv)
        _check_args(args)
        use_uwtools_logger(verbose=args.debug)
        config_data = get_yaml_config(args.config)
        config_data.dereference()
        if not validate(schema_file=resource_path("config.jsonschema"), config_data=config_data):
            fail()
        if not args.check:
            logging.info("Preparing task graph for %s", args.task)
            task = getattr(workflow, args.task)
            task(Config(config_data.data), threads=args.threads)
    except WXVXError as e:
        for line in traceback.format_exc().strip().split("\n"):
            logging.debug(line)
        fail(str(e))


# Private


def _check_args(args: Namespace) -> None:
    if not args.task:
        _show_tasks_and_exit(0)
    if args.task not in tasknames(workflow):
        logging.error("No such task: %s", args.task)
        _show_tasks_and_exit(1)


def _parse_args(argv: list[str]) -> Namespace:
    parser = ArgumentParser(
        description=pkgname,
        add_help=False,
        formatter_class=lambda prog: HelpFormatter(prog, max_help_position=6),
    )
    required = parser.add_argument_group("Required arguments")
    required.add_argument(
        "-c",
        "--config",
        help="Configuration file",
        metavar="FILE",
        required=True,
        type=Path,
    )
    required.add_argument(
        "-t",
        "--task",
        help="Execute task (no argument => list available tasks)",
        metavar="TASK",
        nargs="?",
        default=None,
    )
    optional = parser.add_argument_group("Optional arguments")
    optional.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Log all messages",
    )
    optional.add_argument(
        "-h",
        "--help",
        action="help",
        help="Show help and exit",
    )
    optional.add_argument(
        "-k",
        "--check",
        action="store_true",
        help="Check config and exit",
    )
    optional.add_argument(
        "-n",
        "--threads",
        help="Number of threads",
        default=1,
        metavar="N",
        type=int,
    )
    optional.add_argument(
        "-s",
        "--show",
        action=ShowConfig,
        help="Show a pro-forma config and exit",
        nargs=0,
    )
    optional.add_argument(
        "-v",
        "--version",
        action="version",
        help="Show version and exit",
        version=f"{Path(argv[0]).name} {_version()}",
    )
    args = parser.parse_args(argv[1:])
    if args.threads < 1:
        print("Specify at least 1 thread", file=sys.stderr)
        sys.exit(1)
    return args


def _show_tasks_and_exit(code: int) -> NoReturn:
    logging.info("Available tasks:")
    for taskname in tasknames(workflow):
        logging.info("  %s", taskname)
    sys.exit(code)


def _version() -> str:
    info = json.loads(resource("info.json"))
    return "version %s build %s" % (info["version"], info["buildnum"])


class ShowConfig(Action):
    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):  # noqa: ARG002
        print(resource("config-grid.yaml").strip())
        sys.exit(0)
