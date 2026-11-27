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

When the newest snapshot has a file where an older one has a folder (or the reverse), the
newest wins and the older path is skipped with a warning. Symlinks inside snapshots are
skipped, never followed, and so is a manifest at a snapshot's root. On a case-insensitive
output filesystem, names differing only by case are one file (in the plan and in the
manifest, which still records each file under its own spelling).
"""

import dataclasses
import itertools
import logging
import re
import shutil
import stat
from typing import TYPE_CHECKING

from wayback_machine_downloader_companion._filesystem import (
    fold_key,
    is_case_insensitive,
    replace_atomically,
)
from wayback_machine_downloader_companion._manifest import Manifest, load_manifest, save_manifest

if TYPE_CHECKING:
    import argparse
    import pathlib
    from collections.abc import Iterator

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


@dataclasses.dataclass(slots=True)
class _Claims:
    """Output paths already taken by newer snapshots, as files and as the folders above them.

    A path can't be both a file and a folder, so ``files`` and ``folders`` never overlap, and
    ``folders`` holds every ancestor of every file: an ancestor walk stops at the first known
    folder.

    Attributes:
        files (dict[str, str]): Keys of the files in the plan -> their relative path.
        folders (set[str]): Keys of the folders holding them.
    """

    files: dict[str, str] = dataclasses.field(default_factory=dict)
    folders: set[str] = dataclasses.field(default_factory=set)

    def conflict(self, key: str) -> str | None:
        """Finds a newer path that makes ``key`` impossible to write.

        Args:
            key (str): The candidate file's key (POSIX relative path, maybe case-folded).

        Returns:
            str | None: ``key`` itself if it is already a folder, the ancestor of ``key``
            that is already a file, or ``None`` if ``key`` can be a file.
        """
        if key in self.folders:
            return key
        parent = key.rpartition("/")[0]
        while parent and parent not in self.folders:
            if parent in self.files:
                return parent
            parent = parent.rpartition("/")[0]
        return None

    def add(self, key: str, relative: str) -> None:
        """Takes ``key`` as a file, and its ancestors as folders.

        Args:
            key (str): A key :meth:`conflict` accepted.
            relative (str): The file's relative path, as spelled in its snapshot.
        """
        self.files[key] = relative
        parent = key.rpartition("/")[0]
        while parent and parent not in self.folders:
            self.folders.add(parent)
            parent = parent.rpartition("/")[0]


def _is_older_version(claims: _Claims, key: str, relative: str, path: "pathlib.Path") -> bool:
    """Tells whether a newer snapshot already has this file, and says so if it is respelled.

    Args:
        claims (_Claims): Output paths taken by newer snapshots.
        key (str): The candidate's key.
        relative (str): The candidate's relative path.
        path (pathlib.Path): The candidate file, for the log.

    Returns:
        bool: ``True`` if the newer file takes the candidate's place.
    """
    claimed = claims.files.get(key)
    if claimed is None:
        return False
    if claimed != relative:  # only case folding makes two spellings one file
        logger.warning(
            "Skipping %s: a newer snapshot has %s, the same file on a case-insensitive output",
            path,
            claimed,
        )
    return True


def _add_snapshot(
    plan: MergePlan, folder: "pathlib.Path", claims: _Claims, fold_case: bool
) -> None:
    """Adds a snapshot's files to the plan, unless a newer snapshot already decided them.

    Args:
        plan (MergePlan): The plan being built (newest snapshots first).
        folder (pathlib.Path): The snapshot folder.
        claims (_Claims): Output paths taken by newer snapshots; updated.
        fold_case (bool): Treat names differing only by case as one file.
    """
    skip = len(folder.parts)
    # A snapshot's own manifest at its root would overwrite the output's: it isn't a site file.
    manifest_key = fold_key(MANIFEST_FILE, fold_case)
    for path in folder.rglob("*"):
        mode = path.lstat().st_mode  # one call tells a symlink, a file and a folder apart
        if stat.S_ISLNK(mode):
            logger.warning("Skipping symlink %s (symlinks are not followed)", path)
            continue
        if not stat.S_ISREG(mode):
            continue
        # rglob yields paths under `folder`: slicing its parts is exact, and much cheaper
        # than `relative_to` (measured: most of the merge time).
        relative = "/".join(path.parts[skip:])
        key = fold_key(relative, fold_case)
        if key == manifest_key:
            logger.info("Skipping %s: a merge manifest, not a site file", path)
            continue
        if _is_older_version(claims, key, relative, path):
            continue
        conflict = claims.conflict(key)
        if conflict is not None:
            logger.warning(
                "Skipping %s: a newer snapshot has %s as a %s",
                path,
                conflict,
                "folder" if conflict == key else "file",
            )
            continue
        claims.add(key, relative)
        plan.entries.append(MergeEntry(path, relative, folder.name))


def _snapshot_versions(config: "AppConfig") -> list["pathlib.Path"]:
    """Lists the snapshot folders, newest first.

    Args:
        config (AppConfig): The active configuration.

    Returns:
        list[pathlib.Path]: The snapshot folders (see :func:`is_snapshot_folder`).
    """
    snapshots = config.folder_snapshots
    if not snapshots.is_dir():
        return []
    return sorted((f for f in snapshots.glob("*") if is_snapshot_folder(f)), reverse=True)


def build_merge_plan(config: "AppConfig", fold_case: bool = False) -> MergePlan:
    """Resolves the most recent version of every file across versioned snapshot folders.

    Args:
        config (AppConfig): The active configuration.
        fold_case (bool): Treat names differing only by case as one file (on case-insensitive
            filesystems, they are: the newest snapshot's copy must win).

    Returns:
        MergePlan: The files to merge. Empty if there is nothing to merge.
    """
    versions = _snapshot_versions(config)
    if not versions:
        logger.info("Nothing to merge in %s", config.folder_snapshots)
        return MergePlan()

    logger.info("Found %d folder(s) to be merged", len(versions))
    plan = MergePlan()
    claims = _Claims()
    for folder in versions:  # newest first: the first version seen of a path wins
        _add_snapshot(plan, folder, claims, fold_case)

    logger.info("Found %d file(s) for %s", len(plan.entries), config.web_folder)
    return plan


def _untouched_since_merge(destination: "pathlib.Path", record: "dict[str, object]") -> bool:
    """Tells whether an output file is still exactly what a previous merge wrote.

    Args:
        destination (pathlib.Path): The output file.
        record (dict): What the manifest recorded for it.

    Returns:
        bool: ``True`` if its size and modification time match the record.
    """
    stat_result = destination.stat()
    return (
        record.get("size") == stat_result.st_size
        and record.get("mtime_ns") == stat_result.st_mtime_ns
    )


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


def _ensure_folder(folder: "pathlib.Path", known: "set[pathlib.Path]") -> bool:
    """Creates an output folder, unless a file is in the way.

    Args:
        folder (pathlib.Path): The folder, inside the output folder.
        known (set[pathlib.Path]): Folders known to exist, the output folder included (so
            the ancestor walk stops there); updated. It saves a ``mkdir`` per copied file.

    Returns:
        bool: ``True`` if ``folder`` now exists, ``False`` if a non-folder is in the way.
    """
    missing: list[pathlib.Path] = []
    current = folder
    while current not in known and not current.is_dir():
        if current.exists():  # a file where a folder should be
            return False
        missing.append(current)
        current = current.parent
    for created in reversed(missing):
        created.mkdir(exist_ok=True)
    known.update(missing)
    known.add(current)
    return True


def _merge_entry(
    entry: MergeEntry, output: "pathlib.Path", manifest: Manifest, known: "set[pathlib.Path]"
) -> bool:
    """Copies one entry into the output folder if it should be, and records it.

    Args:
        entry (MergeEntry): The candidate.
        output (pathlib.Path): The output folder.
        manifest (Manifest): What the merges wrote; updated.
        known (set[pathlib.Path]): Output folders known to exist; updated.

    Returns:
        bool: ``True`` if the file was written.
    """
    destination = output / entry.relative
    if not _should_copy(entry, destination, manifest.get(entry.relative)):
        return False
    if not _ensure_folder(destination.parent, known):
        logger.warning(
            "Skipping %s: a file in the output is in the way of its folder", entry.source
        )
        return False
    logger.debug("Copying %s -> %s", entry.source, destination)
    replace_atomically(destination, lambda temporary: shutil.copy2(entry.source, temporary))
    stat_result = destination.stat()
    manifest.put(
        entry.relative,
        {
            "snapshot": entry.snapshot,
            "size": stat_result.st_size,
            "mtime_ns": stat_result.st_mtime_ns,
        },
    )
    return True


def _merge_entries(plan: MergePlan, output: "pathlib.Path", fold_case: bool) -> int:
    """Copies the plan into the output folder, keeping the manifest up to date.

    The manifest is saved even when a copy fails midway (the error then propagates), so the
    next merge still recognises the files this one wrote. It is left alone when nothing was
    written.

    Args:
        plan (MergePlan): The files to merge.
        output (pathlib.Path): The output folder (it exists).
        fold_case (bool): Look manifest records up whatever their case, as the plan was folded.

    Returns:
        int: How many files were written.
    """
    manifest_path = output / MANIFEST_FILE
    manifest = Manifest(load_manifest(manifest_path), fold_case)
    known = {output}
    written = 0
    try:
        for entry in plan.entries:
            if _merge_entry(entry, output, manifest, known):
                written += 1
    finally:
        if written:
            save_manifest(manifest_path, manifest)
    return written


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


def _probe_entries(config: "AppConfig") -> "Iterator[pathlib.Path]":
    """Lists, lazily, the entries that tell whether the output folder ignores case.

    The output's own entries come first (after a first merge, at least its manifest); an
    empty output falls back on the snapshots' entries, usually on the same filesystem.

    Args:
        config (AppConfig): The active configuration (its output folder exists).

    Returns:
        Iterator[pathlib.Path]: The candidate entries, read only as far as the probe needs.
    """
    snapshots = (folder.iterdir() for folder in _snapshot_versions(config))
    return itertools.chain(config.folder_output.iterdir(), itertools.chain.from_iterable(snapshots))


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
    fold_case = is_case_insensitive(_probe_entries(config))
    plan = build_merge_plan(config, fold_case=fold_case)
    if not plan.entries:
        logger.info("Done -- nothing to merge")
        return 0

    written = _merge_entries(plan, output, fold_case)
    logger.info("Done -- %d file(s) written, %d kept as is", written, len(plan.entries) - written)
    return 0
