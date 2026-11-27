#!/usr/bin/env python3
"""Download every resource listed in the missing-resource files via wayback_machine_downloader.

Written against the maintained StrawberryMaster fork: ``-e`` downloads one exact URL and
``-d`` names the folder to save it in, as ``<folder>/<url path>``. Files therefore land in
the output folder the finder scans. The fork retries failed requests itself.
"""

import logging
import shlex
import shutil
import subprocess
import time
from typing import TYPE_CHECKING

from wayback_machine_downloader_companion.config import (
    MISSING_HTML_FILE,
    MISSING_OTHER_FILE,
)

if TYPE_CHECKING:
    import argparse
    import pathlib

    from wayback_machine_downloader_companion.config import AppConfig

logger = logging.getLogger(__name__)

MISSING_FILES = (MISSING_HTML_FILE, MISSING_OTHER_FILE)
EXECUTABLE = "wayback_machine_downloader"
# The fork's last lines: "Download finished in <s>s." on success; "Download completed with
# errors." (logged before the summary of failed URLs) when some request failed.
SUCCESS_MARKER = "Download finished"
FAILURE_MARKER = "Download completed with errors"
DOWNLOAD_TIMEOUT_SECONDS = 600.0
DOWNLOAD_THROTTLE_SECONDS = 1.0


def download_command(executable: str, url: str, directory: "pathlib.Path") -> list[str]:
    """Builds the command downloading one URL into a folder.

    Args:
        executable (str): The ``wayback_machine_downloader`` path ``shutil.which`` found: on
            Windows it's a ``.bat`` that the bare name wouldn't start.
        url (str): The exact URL to fetch from the Wayback Machine.
        directory (pathlib.Path): The folder the site's files live in.

    Returns:
        list[str]: The argument list. It runs without a shell, so on Linux and macOS the URL
        reaches the program as one argument, unchanged, quotes and spaces included. On
        Windows the ``.bat`` runs through ``cmd.exe``, which parses the command line again: a
        ``%NAME%`` sequence in a URL can be expanded when ``NAME`` is an environment variable,
        so such a URL may reach the program altered.
    """
    return [executable, "-e", "-d", str(directory), url]


class MissingUrlsError(Exception):
    """Raised when a missing-resource file can't be read."""


class ToolStartError(Exception):
    """Raised when the ``wayback_machine_downloader`` process can't be started at all."""


def start_process(
    command: list[str], cwd: "pathlib.Path", timeout: float = DOWNLOAD_TIMEOUT_SECONDS
) -> int:
    """Runs a ``wayback_machine_downloader`` command to completion and logs its output.

    Args:
        command (list[str]): The argument list to run.
        cwd (pathlib.Path): Working directory the command is run from.
        timeout (float): Seconds after which the download is abandoned (and the process killed).

    Returns:
        int: ``0`` if the process exited cleanly and reported a finished download without
        errors, ``1`` otherwise (it failed or timed out).

    Raises:
        ToolStartError: The process couldn't start (the program vanished, isn't executable,
            or is a broken ``.bat``): every other URL would fail the same way.
    """
    logger.info("Running: %s", shlex.join(command))
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("No result after %gs -- download abandoned: %s", timeout, command[-1])
        return 1
    except OSError as error:  # the program vanished, isn't executable, or a bad .bat
        raise ToolStartError(f"Can't start {command[0]}: {error}") from error

    output = completed.stdout.decode("utf-8", errors="replace")
    for line in output.splitlines():
        logger.info(line)

    succeeded = (
        completed.returncode == 0 and SUCCESS_MARKER in output and FAILURE_MARKER not in output
    )
    if not succeeded:
        logger.warning("Download failed (exit code %d): %s", completed.returncode, command[-1])
    return 0 if succeeded else 1


def read_missing_urls(config: "AppConfig") -> list[str]:
    """Reads the URLs listed by the finder, without blanks or duplicates.

    Args:
        config (AppConfig): The active configuration.

    Returns:
        list[str]: The URLs, HTML pages first, in file order.

    Raises:
        MissingUrlsError: A file can't be read, or isn't UTF-8 (the finder writes UTF-8, so it
            was edited by hand).
    """
    urls: dict[str, None] = {}  # ordered set
    for file_name in MISSING_FILES:
        missing_file = config.base_dir / file_name
        if not missing_file.exists():
            logger.info("File %s does not exist", missing_file)
            continue
        try:
            text = missing_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise MissingUrlsError(f"Can't read {missing_file}: {error}") from error
        for raw_url in text.splitlines():
            if raw_url.strip():
                urls[raw_url.strip()] = None
    return list(urls)


def _download_all(executable: str, urls: list[str], config: "AppConfig") -> int:
    """Downloads each URL in turn, pausing between them.

    Args:
        executable (str): The ``wayback_machine_downloader`` path.
        urls (list[str]): The URLs to fetch.
        config (AppConfig): The active configuration.

    Returns:
        int: How many downloads failed.

    Raises:
        ToolStartError: The process couldn't start (see :func:`start_process`).
    """
    failures = 0
    for index, url in enumerate(urls):
        if index:
            time.sleep(DOWNLOAD_THROTTLE_SECONDS)  # spare the Wayback Machine
        command = download_command(executable, url, config.folder_output)
        failures += start_process(command, cwd=config.base_dir)
    return failures


def run(config: "AppConfig", args: "argparse.Namespace") -> int:
    """Downloads every resource listed in ``missing_html.txt``/``missing_other.txt``.

    Args:
        config (AppConfig): The active configuration.
        args (argparse.Namespace): Parsed command-line arguments (unused, kept for a uniform
            CLI signature).

    Returns:
        int: ``0`` if every download succeeded (or there was nothing to download), ``1`` if
        at least one failed, a missing-resource file can't be read, or
        ``wayback_machine_downloader`` isn't installed or can't start (the run then stops at
        once: no other URL is tried).
    """
    del args
    try:
        urls = read_missing_urls(config)
    except MissingUrlsError as error:
        logger.error("%s", error)
        return 1
    if not urls:
        logger.info("Done -- nothing to download")
        return 0
    executable = shutil.which(EXECUTABLE)
    if executable is None:
        logger.error("%s not found -- install it first (see INSTALL.md)", EXECUTABLE)
        return 1

    try:
        failures = _download_all(executable, urls, config)
    except ToolStartError as error:
        logger.error("%s -- stopping: the remaining URLs are not tried (see INSTALL.md)", error)
        return 1
    logger.info("Done -- %d of %d download(s) failed", failures, len(urls))
    return 1 if failures else 0
