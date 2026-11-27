"""Helpers shared by the merger tests: snapshot writing and output inspection."""

import json
from typing import TYPE_CHECKING

from wayback_machine_downloader_companion.merger import MANIFEST_FILE

if TYPE_CHECKING:
    import pathlib

    from wayback_machine_downloader_companion.config import AppConfig


def write_snapshot(config: "AppConfig", timestamp: str, files: dict[str, str]) -> None:
    """Write a snapshot folder.

    Args:
        config: The active configuration.
        timestamp: The snapshot's 14-digit name.
        files: Relative path -> content.
    """
    for relative, content in files.items():
        path = config.folder_snapshots / timestamp / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(content, encoding="utf-8")


def output(config: "AppConfig", relative: str) -> str:
    """Read an output file.

    Args:
        config: The active configuration.
        relative: Its path in the output folder.

    Returns:
        Its content.
    """
    return (config.folder_output / relative).read_text(encoding="utf-8")


#: A Wayback snapshot folder name: the 14-digit capture time, ``YYYYMMDDhhmmss``.
OLDER_SNAPSHOT = "20230101000000"
#: A later snapshot folder name. It sorts after :data:`OLDER_SNAPSHOT`, which is what the
#: merge relies on: names sort in time order, and the newest version of a file wins.
NEWER_SNAPSHOT = "20240101000000"


def manifest(config: "AppConfig") -> dict[str, dict[str, object]]:
    """Read the merge manifest.

    Args:
        config: The active configuration.

    Returns:
        Its content.
    """
    return json.loads((config.folder_output / MANIFEST_FILE).read_text(encoding="utf-8"))


def temporaries(config: "AppConfig") -> list["pathlib.Path"]:
    """List the merge's temporary files left in the output folder.

    Args:
        config: The active configuration.

    Returns:
        Every leftover temporary file.
    """
    return list(config.folder_output.rglob(".wmdc-*.tmp"))


def fail_with_a_full_disk() -> OSError:
    """Build the error a copy hits when the disk fills up.

    Returns:
        An ``ENOSPC`` error.
    """
    return OSError(28, "No space left on device")
