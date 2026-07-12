#!/usr/bin/env python3
"""Shared argument parsing, logging setup, and config loading for every console script."""

import argparse
import logging
import pathlib
from collections.abc import Callable

from wayback_machine_downloader_companion.config import AppConfig, ConfigError
from wayback_machine_downloader_companion.logging_utils import configure_logging

RunCallable = Callable[[AppConfig, argparse.Namespace], int]
ConfigureParser = Callable[[argparse.ArgumentParser], None]


def build_parser(
    prog_name: str, description: str, configure_parser: ConfigureParser | None = None,
) -> argparse.ArgumentParser:
    """Builds an argument parser with the flags shared by every WMDC command.

    Args:
        prog_name (str): Program name shown in help/usage text.
        description (str): One-line description shown in help text.
        configure_parser (ConfigureParser | None, optional): Callback that adds entry-point-
            specific arguments. Defaults to None.

    Returns:
        argparse.ArgumentParser: The configured parser.
    """
    parser = argparse.ArgumentParser(prog=prog_name, description=description)
    parser.add_argument(
        '-c', '--configuration', type=pathlib.Path, default=pathlib.Path('config.json'),
        help='Path to config.json (default: ./config.json)',
    )
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help='Increase log verbosity to debug (default: info)',
    )

    if configure_parser is not None:
        configure_parser(parser)

    return parser


def main(
    prog_name: str,
    description: str,
    run_callable: RunCallable,
    configure_parser: ConfigureParser | None = None,
    argv: list[str] | None = None,
) -> int:
    """Parses arguments, loads configuration, and runs a command.

    Args:
        prog_name (str): Program name shown in help/usage text, and used as the log file stem.
        description (str): One-line description shown in help text.
        run_callable (RunCallable): Function that performs the command's work.
        configure_parser (ConfigureParser | None, optional): Callback that adds entry-point-
            specific arguments. Defaults to None.
        argv (list[str] | None, optional): Argument list to parse. Defaults to None, which
            parses ``sys.argv[1:]``.

    Returns:
        int: The process exit code: ``0`` on success, ``1`` on a configuration or runtime error.
    """
    parser = build_parser(prog_name, description, configure_parser)
    args = parser.parse_args(argv)

    configure_logging(prog_name, args.verbose)
    logger = logging.getLogger(prog_name)

    try:
        config = AppConfig.load(args.configuration.resolve())
    except (FileNotFoundError, ConfigError) as error:
        logger.error('%s', error)
        return 1

    try:
        return run_callable(config, args)
    except Exception:
        logger.exception('Unhandled error in %s', prog_name)
        return 1
