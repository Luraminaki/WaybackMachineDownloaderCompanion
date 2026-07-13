#!/usr/bin/env python3
"""Console-script entry point: menu-driven launcher for merge, find, and download."""

import argparse
import logging
import sys

from wayback_machine_downloader_companion import _cli, downloader, finder, merger
from wayback_machine_downloader_companion.config import UNSPECIFIED_FILE, AppConfig

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

_MENU_CHOICES = {'1': 'full', '2': 'merge', '3': 'find', '4': 'download'}


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


def _dispatch_table() -> dict[str, _cli.RunCallable]:
    """Returns the single mode-name to step-function mapping shared by ``run`` and the menu.

    Returns:
        dict[str, _cli.RunCallable]: Mapping from mode name to the function that performs it.
    """
    return {'full': run_full, 'merge': merger.run, 'find': finder.run, 'download': downloader.run}


def needs_merge(config: AppConfig) -> bool:
    """Detects whether the snapshot folder holds versioned (``-s``) subfolders.

    Args:
        config (AppConfig): The active configuration.

    Returns:
        bool: ``True`` if a merge step should run before finding/downloading.
    """
    if not config.folder_snapshots.is_dir():
        return False

    try:
        children = list(config.folder_snapshots.iterdir())
    except OSError:
        return False

    return any(merger.is_snapshot_folder(child) for child in children)


def _warn_if_unspecified_remain(config: AppConfig) -> None:
    """Warns if ``unspecified.txt`` still has entries that were never auto-downloaded.

    Unclassified links (unrecognized extensions, or links that could not be resolved to a
    local path) are exported for manual review but are never fed to :mod:`downloader`, since
    many of them may be genuinely external or otherwise non-fetchable.

    Args:
        config (AppConfig): The active configuration.
    """
    unspecified_file = config.base_dir / UNSPECIFIED_FILE
    if not unspecified_file.exists():
        return

    count = sum(1 for line in unspecified_file.read_text(encoding='utf-8').splitlines() if line.strip())
    if count:
        logger.warning(
            '%d unclassified link(s) in %s were not downloaded automatically -- check them manually',
            count, unspecified_file,
        )


def _merge_step(config: AppConfig, args: argparse.Namespace) -> bool:
    """Runs the merge step first, if one looks needed.

    Args:
        config (AppConfig): The active configuration.
        args (argparse.Namespace): Parsed command-line arguments (reads ``force_merge``).

    Returns:
        bool: ``True`` if no merge was needed or it succeeded, ``False`` if it failed.
    """
    if not (args.force_merge or needs_merge(config)):
        return True

    try:
        merge_result = merger.run(config, args)
    except Exception:
        logger.exception('Merge step raised an unexpected error -- aborting full run')
        return False

    if merge_result != 0:
        logger.error('Merge step failed -- aborting full run')
        return False

    return True


def run_full(config: AppConfig, args: argparse.Namespace) -> int:
    """Merges (if needed), then loops find/download until nothing is missing.

    Args:
        config (AppConfig): The active configuration.
        args (argparse.Namespace): Parsed command-line arguments (reads ``force_merge`` and
            ``max_iterations``).

    Returns:
        int: ``0`` if the run finished with nothing missing, ``1`` if a step raised an
        unexpected error, the merge step failed, or ``--max-iterations`` was reached without
        finishing.
    """
    if not _merge_step(config, args):
        return 1

    for iteration in range(1, args.max_iterations + 1):
        try:
            result = finder.scan(config)
        except Exception:
            logger.exception('Find step raised an unexpected error during iteration %d', iteration)
            return 1

        if not result.scanned:
            return 1

        if result.missing_count == 0:
            logger.info('Nothing missing after %d iteration(s)', iteration)
            _warn_if_unspecified_remain(config)
            return 0

        try:
            download_result = downloader.run(config, args)
        except Exception:
            logger.exception('Download step raised an unexpected error during iteration %d', iteration)
            return 1

        if download_result != 0:
            logger.warning('Some downloads failed during iteration %d', iteration)

    logger.warning(
        'Reached --max-iterations=%d without finishing -- see missing_html.txt/missing_other.txt in %s '
        'for what still remains',
        args.max_iterations, config.base_dir,
    )
    return 1


def run_interactive(config: AppConfig, args: argparse.Namespace) -> int:
    """Prints a numbered menu and dispatches to the step the user picks.

    Args:
        config (AppConfig): The active configuration.
        args (argparse.Namespace): Parsed command-line arguments.

    Returns:
        int: The exit code of the dispatched step, or ``0`` on quit/invalid/no input.
    """
    print(_MENU)

    try:
        choice = input('Choice [1-5]: ').strip()
    except EOFError:
        print('No input available -- exiting.')
        return 1

    mode = _MENU_CHOICES.get(choice)
    if mode is None:
        print('Goodbye.')
        return 0

    return _dispatch_table()[mode](config, args)


def run(config: AppConfig, args: argparse.Namespace) -> int:
    """Dispatches to ``--mode``, or falls back to the interactive menu.

    Args:
        config (AppConfig): The active configuration.
        args (argparse.Namespace): Parsed command-line arguments.

    Returns:
        int: The exit code of the dispatched step.
    """
    if args.mode is not None:
        return _dispatch_table()[args.mode](config, args)

    return run_interactive(config, args)


def cli() -> None:
    """Runs the launcher and exits with its return code."""
    sys.exit(_cli.main(
        'wmdc', 'Menu-driven launcher for merge, find, and download.', run, configure_parser=configure_parser,
    ))


if __name__ == '__main__':
    cli()
