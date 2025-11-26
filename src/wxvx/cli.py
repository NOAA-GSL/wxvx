import json
import logging
import sys
import traceback
from argparse import ArgumentParser, ArgumentTypeError, HelpFormatter, Namespace
from pathlib import Path

from iotaa import tasknames
from uwtools.api.config import get_yaml_config
from uwtools.api.logging import use_uwtools_logger

from wxvx import workflow
from wxvx.types import validated_config
from wxvx.util import WXVXError, fail, pkgname, resource

# Public


def main() -> None:
    try:
        args = _parse_args(sys.argv)
        use_uwtools_logger(verbose=args.debug)
        _process_args(args)
        yc = get_yaml_config(args.config)
        yc.dereference()
        if args.show:
            yc.dump()
            if not args.check:
                sys.exit(0)
        c = validated_config(yc)
        if not args.check:
            logging.info("Preparing task graph for %s", args.task)
            task = getattr(workflow, args.task)
            task(c, threads=args.threads)
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
        help="List available tasks and exit",
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
        action="store_true",
        help="Show the realized config and exit",
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
        if not args.check and not args.show:
            sys.exit(0)
    if not args.config:
        fail("No configuration file specified")
    if args.check or args.show:
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
