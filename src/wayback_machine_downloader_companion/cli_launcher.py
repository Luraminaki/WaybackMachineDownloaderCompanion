#!/usr/bin/env python3
"""Console-script entry point: menu-driven launcher for merge, find, and download."""

import argparse
import logging
import sys

from wayback_machine_downloader_companion import _cli, downloader, finder, merger
from wayback_machine_downloader_companion.config import AppConfig

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ITERATIONS = 10

_MENU = """
Wayback Machine Downloader Companion
  1) Full run (merge if needed -> find -> download, repeat until nothing missing)
  2) Merge snapshots only
  3) Find missing resources only
  4) Download missing resources only
  5) Quit
"""


def configure_parser(parser: argparse.ArgumentParser) -> None:
    """Adds launcher-specific arguments to the shared parser.

    Args:
        parser (argparse.ArgumentParser): The parser to extend.
    """
    parser.add_argument(
        '--mode', choices=('full', 'merge', 'find', 'download'), default=None,
        help='Run non-interactively: perform one step (or the full sequence) and exit.',
    )
    parser.add_argument(
        '--force-merge', action='store_true',
        help='Always merge snapshots first, even if none look versioned.',
    )
    parser.add_argument(
        '--max-iterations', type=int, default=_DEFAULT_MAX_ITERATIONS,
        help=f'Maximum find/download loops in full mode (default: {_DEFAULT_MAX_ITERATIONS}).',
    )


def needs_merge(config: AppConfig) -> bool:
    """Detects whether the snapshot folder holds versioned (``-s``) subfolders.

    Args:
        config (AppConfig): The active configuration.

    Returns:
        bool: ``True`` if a merge step should run before finding/downloading.
    """
    if not config.folder_snapshots.is_dir():
        return False

    return any(merger.is_snapshot_folder(child) for child in config.folder_snapshots.iterdir())


def run_full(config: AppConfig, args: argparse.Namespace) -> int:
    """Merges (if needed), then loops find/download until nothing is missing.

    Args:
        config (AppConfig): The active configuration.
        args (argparse.Namespace): Parsed command-line arguments (reads ``force_merge`` and
            ``max_iterations``).

    Returns:
        int: ``0`` if the run finished with nothing missing, ``1`` if the merge/find step
        failed or ``--max-iterations`` was reached without finishing.
    """
    if (args.force_merge or needs_merge(config)) and merger.run(config, args) != 0:
        logger.error('Merge step failed -- aborting full run')
        return 1

    for iteration in range(1, args.max_iterations + 1):
        result = finder.scan(config)
        if not result.scanned:
            return 1

        if result.missing_count == 0:
            logger.info('Nothing missing after %d iteration(s)', iteration)
            return 0

        if downloader.run(config, args) != 0:
            logger.warning('Some downloads failed during iteration %d', iteration)

    logger.warning('Reached --max-iterations=%d without finishing', args.max_iterations)
    return 1


def run_interactive(config: AppConfig, args: argparse.Namespace) -> int:
    """Prints a numbered menu and dispatches to the step the user picks.

    Args:
        config (AppConfig): The active configuration.
        args (argparse.Namespace): Parsed command-line arguments.

    Returns:
        int: The exit code of the dispatched step, or ``0`` on quit/invalid input.
    """
    print(_MENU)
    choice = input('Choice [1-5]: ').strip()

    dispatch: dict[str, _cli.RunCallable] = {'1': run_full, '2': merger.run, '3': finder.run, '4': downloader.run}
    action = dispatch.get(choice)
    if action is None:
        print('Goodbye.')
        return 0

    return action(config, args)


def run(config: AppConfig, args: argparse.Namespace) -> int:
    """Dispatches to ``--mode``, or falls back to the interactive menu.

    Args:
        config (AppConfig): The active configuration.
        args (argparse.Namespace): Parsed command-line arguments.

    Returns:
        int: The exit code of the dispatched step.
    """
    dispatch: dict[str, _cli.RunCallable] = {
        'full': run_full, 'merge': merger.run, 'find': finder.run, 'download': downloader.run,
    }

    if args.mode is not None:
        return dispatch[args.mode](config, args)

    return run_interactive(config, args)


def cli() -> None:
    """Runs the launcher and exits with its return code."""
    sys.exit(_cli.main(
        'wmdc', 'Menu-driven launcher for merge, find, and download.', run, configure_parser=configure_parser,
    ))


if __name__ == '__main__':
    cli()
