#!/usr/bin/env python3
"""Merge versioned wayback-machine-downloader snapshot folders into a single output folder.

The merge never deletes anything. Each output file is written atomically (temporary file,
then rename), and a manifest (:data:`MANIFEST_FILE`, in the output folder) records which
snapshot it came from. A file is (re)written only when:

- the output lacks it, or
- a newer snapshot has it, and the output copy is still exactly the one a previous merge
  wrote (same size and modification time as recorded).

So re-running a merge is safe: files fetched later by ``wmdc-download``, and manual edits,
are never overwritten.
"""

import dataclasses
import json
import logging
import os
import re
import shutil
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse
    import pathlib

    from wayback_machine_downloader_companion.config import AppConfig

logger = logging.getLogger(__name__)

_SNAPSHOT_FOLDER_NAME = re.compile(r"\d{14}")
MANIFEST_FILE = ".wmdc-merge.json"


def is_snapshot_folder(path: "pathlib.Path") -> bool:
    """Returns whether a path looks like a versioned wayback-machine-downloader snapshot folder.

    This is the single source of truth for what counts as a snapshot folder (as produced by
    ``wayback_machine_downloader -s``, one per 14-digit wayback timestamp), shared by
    :func:`build_merge_plan` and
    :func:`wayback_machine_downloader_companion.cli_launcher.needs_merge` so both always agree
    on which folders are real snapshots.

    Args:
        path (pathlib.Path): Candidate folder.

    Returns:
        bool: ``True`` if ``path`` is a directory whose name is a 14-digit wayback timestamp.
    """
    return path.is_dir() and bool(_SNAPSHOT_FOLDER_NAME.fullmatch(path.name))


@dataclasses.dataclass(frozen=True, slots=True)
class MergeEntry:
    """One file of the merged output.

    Attributes:
        source (pathlib.Path): The most recent version of the file, in a snapshot folder.
        relative (str): Its path relative to the snapshot (and output) folder, POSIX style.
        snapshot (str): The 14-digit timestamp of the snapshot it comes from.
    """

    source: "pathlib.Path"
    relative: str
    snapshot: str


@dataclasses.dataclass(slots=True)
class MergePlan:
    """The files to merge: the most recent version of each.

    Attributes:
        entries (list[MergeEntry]): One entry per output file.
    """

    entries: list[MergeEntry] = dataclasses.field(default_factory=list)


def is_case_insensitive(folder: "pathlib.Path") -> bool:
    """Tells whether a folder's filesystem ignores case (macOS and Windows defaults).

    Args:
        folder (pathlib.Path): An existing folder on the filesystem to probe.

    Returns:
        bool: ``True`` if ``A.html`` and ``a.html`` would be the same file there.
    """
    with tempfile.NamedTemporaryFile(prefix="wmdc-Case-", dir=folder) as probe:
        twin = os.path.join(os.path.dirname(probe.name), os.path.basename(probe.name).lower())
        return os.path.exists(twin)


def build_merge_plan(config: "AppConfig", fold_case: bool = False) -> MergePlan:
    """Resolves the most recent version of every file across versioned snapshot folders.

    Args:
        config (AppConfig): The active configuration.
        fold_case (bool): Treat names differing only by case as one file (on case-insensitive
            filesystems, they are: the newest snapshot's copy must win).

    Returns:
        MergePlan: The files to merge. Empty if there is nothing to merge.
    """
    snapshots = config.folder_snapshots
    versions = sorted(
        (f for f in snapshots.glob("*") if is_snapshot_folder(f)) if snapshots.is_dir() else (),
        reverse=True,
    )
    if not versions:
        logger.info("Nothing to merge in %s", snapshots)
        return MergePlan()

    logger.info("Found %d folder(s) to be merged", len(versions))
    plan = MergePlan()
    seen: set[str] = set()
    for folder in versions:  # newest first: the first version seen of a file wins
        for file in folder.rglob("*"):
            if not file.is_file():
                continue
            relative = file.relative_to(folder).as_posix()
            key = relative.casefold() if fold_case else relative
            if key not in seen:
                seen.add(key)
                plan.entries.append(MergeEntry(file, relative, folder.name))

    logger.info("Found %d file(s) for %s", len(plan.entries), config.web_folder)
    return plan


def _load_manifest(path: "pathlib.Path") -> dict[str, dict[str, object]]:
    """Reads the merge manifest.

    Args:
        path (pathlib.Path): The manifest file.

    Returns:
        dict: Relative path -> what the last merge wrote there; empty if absent or unreadable.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:  # unreadable, or not JSON
        logger.warning("Ignoring unreadable merge manifest %s -- %s", path, error)
        return {}
    return data if isinstance(data, dict) else {}


def _untouched_since_merge(destination: "pathlib.Path", record: "dict[str, object]") -> bool:
    """Tells whether an output file is still exactly what a previous merge wrote.

    Args:
        destination (pathlib.Path): The output file.
        record (dict): What the manifest recorded for it.

    Returns:
        bool: ``True`` if its size and modification time match the record.
    """
    stat = destination.stat()
    return record.get("size") == stat.st_size and record.get("mtime_ns") == stat.st_mtime_ns


def _should_copy(
    entry: MergeEntry, destination: "pathlib.Path", record: "dict[str, object] | None"
) -> bool:
    """Decides whether a merge entry replaces (or creates) its output file.

    Args:
        entry (MergeEntry): The candidate.
        destination (pathlib.Path): Where it would go.
        record (dict | None): What the last merge wrote there, if anything.

    Returns:
        bool: ``True`` to write it.
    """
    if not destination.exists():
        return True
    if record is None:  # not written by a merge: downloaded or edited by hand
        return False
    newer = str(record.get("snapshot", "")) < entry.snapshot
    return newer and _untouched_since_merge(destination, record)


def _copy_atomically(source: "pathlib.Path", destination: "pathlib.Path") -> None:
    """Copies a file through a temporary name, so the destination is never half-written.

    Args:
        source (pathlib.Path): File to copy.
        destination (pathlib.Path): Target path; its folder is created if needed.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.wmdc-tmp")
    try:
        _ = shutil.copy2(source, temporary)
        _ = temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)  # left only if the copy failed


def _check_folders(config: "AppConfig") -> str | None:
    """Refuses folder layouts where the merge would write into its own sources.

    Args:
        config (AppConfig): The active configuration.

    Returns:
        str | None: Why the merge can't run, or ``None`` if it can.
    """
    output, snapshots = config.folder_output.resolve(), config.folder_snapshots.resolve()
    if output == snapshots:
        return "WEB_OUTPUT and WEB_FOLDER are the same folder"
    if output.is_relative_to(snapshots) or snapshots.is_relative_to(output):
        return "WEB_OUTPUT and WEB_FOLDER are nested in each other"
    return None


def run(config: "AppConfig", args: "argparse.Namespace") -> int:
    """Merges the most recent version of every snapshot file into the output folder.

    Args:
        config (AppConfig): The active configuration.
        args (argparse.Namespace): Parsed command-line arguments (unused, kept for a uniform
            CLI signature).

    Returns:
        int: ``0`` on success, ``1`` if the folder layout makes merging unsafe.
    """
    del args
    problem = _check_folders(config)
    if problem is not None:
        logger.error("Refusing to merge: %s (%s)", problem, config.folder_output)
        return 1

    output = config.folder_output
    output.mkdir(parents=True, exist_ok=True)
    plan = build_merge_plan(config, fold_case=is_case_insensitive(output))
    if not plan.entries:
        logger.info("Done -- nothing to merge")
        return 0

    manifest_path = output / MANIFEST_FILE
    manifest = _load_manifest(manifest_path)
    written = 0
    for entry in plan.entries:
        destination = output / entry.relative
        if not _should_copy(entry, destination, manifest.get(entry.relative)):
            continue
        logger.debug("Copying %s -> %s", entry.source, destination)
        _copy_atomically(entry.source, destination)
        stat = destination.stat()
        manifest[entry.relative] = {
            "snapshot": entry.snapshot,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
        written += 1

    _ = manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    logger.info("Done -- %d file(s) written, %d kept as is", written, len(plan.entries) - written)
    return 0
