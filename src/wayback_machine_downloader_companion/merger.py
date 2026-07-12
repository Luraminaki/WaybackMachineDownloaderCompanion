#!/usr/bin/env python3
"""Merge versioned wayback-machine-downloader snapshot folders into a single output folder."""

import argparse
import dataclasses
import logging
import pathlib
import re
import shutil

from wayback_machine_downloader_companion.config import AppConfig

logger = logging.getLogger(__name__)

_SNAPSHOT_FOLDER_NAME = re.compile(r'\d{14}')


def is_snapshot_folder(path: pathlib.Path) -> bool:
    """Returns whether a path looks like a versioned wayback-machine-downloader snapshot folder.

    This is the single source of truth for what counts as a snapshot folder (as produced by
    ``wayback_machine_downloader -s``, one per 14-digit wayback timestamp), shared by
    :func:`get_all_files` and :func:`wayback_machine_downloader_companion.cli_launcher.needs_merge`
    so both always agree on which folders are real snapshots.

    Args:
        path (pathlib.Path): Candidate folder.

    Returns:
        bool: ``True`` if ``path`` is a directory whose name is a 14-digit wayback timestamp.
    """
    return path.is_dir() and bool(_SNAPSHOT_FOLDER_NAME.fullmatch(path.name))


def rm_tree(path: pathlib.Path) -> None:
    """Deletes a folder and its content.

    Args:
        path (pathlib.Path): Folder to delete. Does nothing if it does not exist.
    """
    if path.exists():
        shutil.rmtree(path)


@dataclasses.dataclass(slots=True)
class MergePlan:
    """A list of files to copy from versioned snapshot folders into the merged output.

    Attributes:
        sources (list[pathlib.Path]): Paths of the most recent version of each file.
        destinations (list[pathlib.Path]): Corresponding destination paths, one per source.
    """

    sources: list[pathlib.Path] = dataclasses.field(default_factory=list)
    destinations: list[pathlib.Path] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        """Validates that sources and destinations line up.

        Raises:
            ValueError: ``sources`` and ``destinations`` have different lengths.
        """
        if len(self.sources) != len(self.destinations):
            raise ValueError('sources and destinations must be the same length')


def get_all_files(config: AppConfig) -> MergePlan:
    """Resolves the most recent version of every file across versioned snapshot folders.

    Args:
        config (AppConfig): The active configuration.

    Returns:
        MergePlan: The files to copy and where they should land in the merged output folder.
        Empty if there is nothing to merge.
    """
    versions = sorted((f for f in config.folder_snapshots.glob('*') if is_snapshot_folder(f)), reverse=True)
    if not versions:
        logger.info('Nothing to merge in %s', config.folder_snapshots)
        return MergePlan()

    logger.info('Found %d folder(s) to be merged', len(versions))

    sources: list[pathlib.Path] = []
    destinations: list[pathlib.Path] = []
    seen: set[pathlib.Path] = set()

    for folder in versions:
        files = sorted(folder.rglob('*.*'))
        if not files:
            logger.info('Nothing to merge in %s', folder.name)
            continue

        logger.info('Found %d file(s) in folder %s', len(files), folder.name)

        for file in files:
            relative = file.relative_to(folder)
            if relative in seen:
                continue

            seen.add(relative)
            sources.append(file)
            destinations.append(config.folder_output / relative)

    logger.info('Found %d file(s) for %s', len(sources), config.web_folder)
    return MergePlan(sources=sources, destinations=destinations)


def run(config: AppConfig, args: argparse.Namespace) -> int:
    """Rebuilds the merged output folder from the most recent version of every snapshot file.

    Args:
        config (AppConfig): The active configuration.
        args (argparse.Namespace): Parsed command-line arguments (unused, kept for a uniform
            CLI signature).

    Returns:
        int: ``0`` on success.
    """
    rm_tree(config.folder_output)
    config.folder_output.mkdir(parents=True, exist_ok=True)

    plan = get_all_files(config)
    if not plan.sources:
        logger.info('Done -- nothing to merge')
        return 0

    for source, destination in zip(plan.sources, plan.destinations, strict=True):
        logger.info('Copying %s -> %s', source, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, destination)

    logger.info('Done')
    return 0
