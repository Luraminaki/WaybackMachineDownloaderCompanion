#!/usr/bin/env python3
"""The merge manifest: what previous merges wrote in the output folder, file by file.

See :mod:`wayback_machine_downloader_companion.merger` for how it decides what to rewrite.
"""

import json
import logging
from typing import TYPE_CHECKING

from wayback_machine_downloader_companion._filesystem import fold_key, replace_atomically

if TYPE_CHECKING:
    import pathlib

logger = logging.getLogger(__name__)


class Manifest:
    """What previous merges wrote, by each file's relative path as spelled when written.

    Keys are stored unfolded, so the manifest stays right when the output moves to a
    filesystem that handles case differently; only lookups fold them. A manifest from 0.4.0
    development builds, whose keys were folded, is read the same way.
    """

    def __init__(self, records: "dict[str, dict[str, object]]", fold_case: bool) -> None:
        """Indexes the records for lookups.

        Args:
            records (dict): Relative path -> what a merge wrote there.
            fold_case (bool): Look paths up whatever their case.
        """
        self.records: dict[str, dict[str, object]] = records
        self._fold_case: bool = fold_case
        self._stored: dict[str, str] = {fold_key(key, fold_case): key for key in records}

    def get(self, relative: str) -> "dict[str, object] | None":
        """Finds what a merge wrote at a path.

        Args:
            relative (str): The output file's relative path.

        Returns:
            dict | None: Its record, or ``None`` if no merge wrote it.
        """
        stored = self._stored.get(fold_key(relative, self._fold_case))
        return None if stored is None else self.records[stored]

    def put(self, relative: str, record: "dict[str, object]") -> None:
        """Records a write, replacing the record of any other spelling of the same file.

        Args:
            relative (str): The written file's relative path.
            record (dict): What was written.
        """
        key = fold_key(relative, self._fold_case)
        previous = self._stored.get(key)
        if previous is not None and previous != relative:
            del self.records[previous]
        self.records[relative] = record
        self._stored[key] = relative


def load_manifest(path: "pathlib.Path") -> dict[str, dict[str, object]]:
    """Reads the merge manifest.

    An unusable manifest is never fatal and never unsafe: with no record, every existing
    output file counts as downloaded or edited by hand, so it is kept as is.

    Args:
        path (pathlib.Path): The manifest file.

    Returns:
        dict: Relative path -> what the last merge wrote there; empty if absent or unusable.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:  # unreadable, or not JSON (torn, edited...)
        logger.warning(
            "Ignoring unreadable merge manifest %s -- %s; existing files are kept as is",
            path,
            error,
        )
        return {}
    if not isinstance(data, dict):
        logger.warning(
            "Ignoring merge manifest %s: not a JSON object; existing files are kept as is", path
        )
        return {}
    return {key: record for key, record in data.items() if isinstance(record, dict)}


def save_manifest(path: "pathlib.Path", manifest: Manifest) -> None:
    """Writes the merge manifest atomically.

    Args:
        path (pathlib.Path): The manifest file.
        manifest (Manifest): What the merges wrote.
    """
    content = json.dumps(manifest.records, sort_keys=True)
    replace_atomically(path, lambda temporary: temporary.write_text(content, encoding="utf-8"))
