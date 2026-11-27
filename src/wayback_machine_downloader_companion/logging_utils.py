#!/usr/bin/env python3
"""Shared logging setup for the CLI entry points."""

import logging
import os
import pathlib
import re
from logging.handlers import RotatingFileHandler

_DEFAULT_MAX_BYTES = 5 * 1024 * 1024
_DEFAULT_BACKUP_COUNT = 5
_VERBOSITY_LEVELS = (logging.INFO, logging.DEBUG)
_FORMAT = "[%(asctime)s] [%(process)s] [%(name)s] [%(levelname)s]: %(funcName)s -- %(message)s"
LOG_DIR = pathlib.Path("logs")
KEPT_LOG_FILES = 20


def _prune_old_logs(log_dir: pathlib.Path, log_file_stem: str, keep: int) -> None:
    """Deletes the oldest log files of a program, keeping the most recent ones.

    Only the program's own files count: ``<stem>-<pid>.log`` and its rotated
    ``<stem>-<pid>.log.<n>``. A plain ``<stem>-*`` glob would also take ``wmdc-merge-*``
    files for ``wmdc`` ones.

    Args:
        log_dir (pathlib.Path): The log folder.
        log_file_stem (str): The program's log file stem.
        keep (int): How many of its log files (rotated ones included) to keep.
    """
    own_name = re.compile(rf"{re.escape(log_file_stem)}-\d+\.log(?:\.\d+)?")
    dated = [
        (mtime, file)
        for file in log_dir.glob(f"{log_file_stem}-*.log*")
        if own_name.fullmatch(file.name) and (mtime := _mtime(file)) is not None
    ]
    dated.sort(reverse=True)
    for _, old in dated[keep:]:
        _delete_if_possible(old)


def _mtime(path: pathlib.Path) -> float | None:
    """Reads a file's modification time.

    Args:
        path (pathlib.Path): The file.

    Returns:
        float | None: Its mtime, or ``None`` if it no longer exists.
    """
    try:
        return path.stat().st_mtime
    except FileNotFoundError:  # another run, pruning the same folder, deleted it first
        return None


def _delete_if_possible(path: pathlib.Path) -> None:
    """Deletes a file, leaving it for a later run if the OS refuses.

    Args:
        path (pathlib.Path): The file.
    """
    try:
        path.unlink(missing_ok=True)
    except OSError as error:  # still open by another process (Windows)
        logging.getLogger(__name__).debug("Keeping %s for a later run -- %s", path, error)


def configure_logging(
    log_file_stem: str,
    verbosity: int = 0,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    backup_count: int = _DEFAULT_BACKUP_COUNT,
) -> None:
    """Initializes logging consistently across the CLI entry points.

    The log file is ``logs/<log_file_stem>-<pid>.log`` (relative to the working directory),
    one per OS process, rather than one shared file: ``RotatingFileHandler``'s rotation
    (renaming the file once it grows past `max_bytes`) is not safe across multiple processes
    -- if two processes hold the same file open, one process rotating it can orphan the
    other's file handle, silently dropping its log lines from then on. Each file still rotates
    on its own (`backup_count` older files), and only the :data:`KEPT_LOG_FILES` most recent
    files of a program are kept, so runs don't pile files up.

    Args:
        log_file_stem (str): The stem for the log file name (typically the program name).
        verbosity (int, optional): Number of times ``-v`` was passed on the command line. ``0``
            (default) logs info and above; ``1+`` logs debug and above. Defaults to 0.
        max_bytes (int, optional): Size in bytes a log file may reach before it rolls over.
            Defaults to 5 MiB.
        backup_count (int, optional): Number of rotated log files to keep. Defaults to 5.
    """
    LOG_DIR.mkdir(exist_ok=True)
    _prune_old_logs(LOG_DIR, log_file_stem, KEPT_LOG_FILES - 1)  # room for this run's file

    level = _VERBOSITY_LEVELS[min(verbosity, len(_VERBOSITY_LEVELS) - 1)]
    log_file = LOG_DIR / f"{log_file_stem}-{os.getpid()}.log"
    logging.basicConfig(
        level=level,
        format=_FORMAT,
        handlers=[
            RotatingFileHandler(
                log_file, mode="a", maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
            ),
            logging.StreamHandler(),
        ],
        force=True,  # replaces any previous configuration (e.g. a second run in one process)
    )
