#!/usr/bin/env python3
"""Download every resource listed in the missing-resource files via wayback_machine_downloader."""

import argparse
import logging
import pathlib
import shlex
import subprocess
import time

from wayback_machine_downloader_companion.config import MISSING_HTML_FILE, MISSING_OTHER_FILE, AppConfig

logger = logging.getLogger(__name__)

MISSING_FILES = (MISSING_HTML_FILE, MISSING_OTHER_FILE)
DOWNLOAD_COMMAND = 'wayback_machine_downloader -e'
DOWNLOAD_COMPLETE_MARKER = 'Download completed'
DOWNLOAD_THROTTLE_SECONDS = 1.0


def start_process(command: str, cwd: pathlib.Path) -> int:
    """Runs a ``wayback_machine_downloader`` command and streams its output until it completes.

    Args:
        command (str): The full command line to run.
        cwd (pathlib.Path): Working directory the command is run from.

    Returns:
        int: ``0`` if a "Download completed" line was seen, ``1`` otherwise.
    """
    logger.info('Running command: %s', command)
    with subprocess.Popen(shlex.split(command), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
        if process.stdout is None:
            return 1

        for raw_line in process.stdout:
            line = raw_line.decode('utf-8', errors='replace').rstrip('\n')
            logger.info(line)
            if DOWNLOAD_COMPLETE_MARKER in line:
                process.terminate()
                return 0

    logger.warning('Command did not return the expected result: %s', command)
    return 1


def run(config: AppConfig, args: argparse.Namespace) -> int:
    """Downloads every resource listed in ``missing_html.txt``/``missing_other.txt``.

    Args:
        config (AppConfig): The active configuration.
        args (argparse.Namespace): Parsed command-line arguments (unused, kept for a uniform
            CLI signature).

    Returns:
        int: ``0`` if every download completed, ``1`` if at least one did not.
    """
    had_failure = False

    for file_name in MISSING_FILES:
        missing_file = config.base_dir / file_name

        if not missing_file.exists():
            logger.info('File %s does not exist', missing_file)
            continue

        for raw_url in missing_file.read_text(encoding='utf-8').splitlines():
            url = raw_url.strip()
            if not url:
                continue

            if start_process(f'{DOWNLOAD_COMMAND} {url}', cwd=config.base_dir.parent) != 0:
                had_failure = True
            time.sleep(DOWNLOAD_THROTTLE_SECONDS)

    logger.info('Done')
    return 1 if had_failure else 0
