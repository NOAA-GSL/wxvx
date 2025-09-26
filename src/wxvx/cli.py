import json
import logging
import sys
import traceback
from argparse import Action, ArgumentParser, ArgumentTypeError, HelpFormatter, Namespace
from pathlib import Path

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
        use_uwtools_logger(verbose=args.debug)
        _process_args(args)
        config_data = get_yaml_config(args.config)
        config_data.dereference()
        if not validate(schema_file=resource_path("config.jsonschema"), config_data=config_data):
            fail()
        if args.check:
            return
        logging.info("Preparing task graph for %s", args.task)
        task = getattr(workflow, args.task)
        task(Config(config_data.data), threads=args.threads)
    except WXVXError as e:
        for line in traceback.format_exc().strip().split("\n"):
            logging.debug(line)
        fail(str(e))


# Private


def _arg_type_int_greater_than_zero(val: str) -> int:
    msg = "Integer > 0 required"
    try:
        intval = int(val)
    except ValueError as e:
        raise ArgumentTypeError(msg) from e
    if intval < 1:
        raise ArgumentTypeError(msg)
    return intval


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
        type=Path,
    )
    required.add_argument(
        "-t",
        "--task",
        help="Task to execute",
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
        "-l",
        "--list",
        action="store_true",
        help="List tasks and exit",
    )
    optional.add_argument(
        "-n",
        "--threads",
        help="Number of threads",
        default=1,
        metavar="N",
        type=_arg_type_int_greater_than_zero,
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
    return parser.parse_args(argv[1:])


def _process_args(args: Namespace) -> None:
    if args.list:
        _show_tasks()
        if not args.check:
            sys.exit(0)
        return
    if not args.config:
        fail("No configuration file specified")
    if args.check:
        return
    if args.task not in tasknames(workflow):
        logging.error("No such task: %s", args.task)
        _show_tasks()
        sys.exit(1)
    return


def _show_tasks() -> None:
    logging.info("Available tasks:")
    for taskname in tasknames(workflow):
        logging.info("  %s", taskname)


def _version() -> str:
    info = json.loads(resource("info.json"))
    return "version %s build %s" % (info["version"], info["buildnum"])


class ShowConfig(Action):
    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):  # noqa: ARG002
        print(resource("config-grid.yaml").strip())
        sys.exit(0)
