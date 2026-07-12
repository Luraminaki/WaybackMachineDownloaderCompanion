#!/usr/bin/env python3
"""Find resources referenced by downloaded HTML pages that are missing locally."""

import argparse
import dataclasses
import logging
import pathlib

from wayback_machine_downloader_companion.config import AppConfig
from wayback_machine_downloader_companion.html_parser import HTML_EXT, OTHER_EXT, WBMHTMLParser, find_all_links

logger = logging.getLogger(__name__)

MISSING_HTML_FILE = 'missing_html.txt'
MISSING_OTHER_FILE = 'missing_other.txt'
UNSPECIFIED_FILE = 'unspecified.txt'


def get_all_files(files: list[pathlib.Path], exts: frozenset[str]) -> tuple[list[pathlib.Path], set[str]]:
    """Filters files down to the ones matching a set of extensions.

    Args:
        files (list[pathlib.Path]): Candidate files to filter.
        exts (frozenset[str]): Lowercase extensions to keep, each including the leading dot
            (e.g. ``".htm"``).

    Returns:
        tuple[list[pathlib.Path], set[str]]: The matching files as a list, and their string
        paths as a set.
    """
    matched = [file for file in files if file.suffix.lower() in exts]
    logger.info('Found %d file(s) matching %s', len(matched), sorted(exts))
    return matched, {file.as_posix() for file in matched}


@dataclasses.dataclass(slots=True)
class SortedResourceReport:
    """The overall status of a resource type between what's local and what's referenced.

    Attributes:
        common (list[str]): Resources that exist locally and are referenced.
        missing (list[str]): Resources that are referenced but do not exist locally.
        never_mentioned (list[str]): Resources that exist locally but are never referenced.
    """

    common: list[str]
    missing: list[str]
    never_mentioned: list[str]


def sort_data(local_files: set[str], found_links: set[str], resource_name: str) -> SortedResourceReport:
    """Diffs local files against referenced links.

    Args:
        local_files (set[str]): Paths of the files that exist locally.
        found_links (set[str]): Links found while parsing the downloaded HTML.
        resource_name (str): Label used for logging (e.g. ``"html"``).

    Returns:
        SortedResourceReport: The common, missing, and never-mentioned resources.
    """
    report = SortedResourceReport(
        common=sorted(local_files & found_links),
        missing=sorted(found_links - local_files),
        never_mentioned=sorted(local_files - found_links),
    )

    logger.info('Found %d existing %s resource(s)', len(report.common), resource_name)
    logger.info('Found %d missing %s resource(s)', len(report.missing), resource_name)
    logger.info("Found %d existing but never 'called' %s resource(s)", len(report.never_mentioned), resource_name)

    return report


def export_missing(file_path: pathlib.Path, missing: list[str], config: AppConfig) -> None:
    """Exports a list of missing resources into a writable file, as remote wayback URLs.

    Args:
        file_path (pathlib.Path): Destination file path.
        missing (list[str]): Local-style resource paths to translate back into URLs.
        config (AppConfig): The active configuration, used to translate local paths into URLs.
    """
    logger.info('Saving %s', file_path)
    with file_path.open('w', encoding='utf-8') as export_file:
        for link in missing:
            line = link.replace(config.base_dir.as_posix(), 'https:/')
            line = line.replace(config.web_output, config.web_folder)
            export_file.write(line + '\n')


@dataclasses.dataclass(slots=True)
class FinderResult:
    """The outcome of a find run.

    Attributes:
        scanned (bool): ``False`` if there was nothing to scan (``config.folder_output`` had no
            files), in which case ``missing_count`` is meaningless.
        missing_count (int): Total number of missing resources found (html + other).
    """

    scanned: bool
    missing_count: int


def scan(config: AppConfig) -> FinderResult:
    """Scans downloaded HTML for missing local resources and exports the results.

    This is the core logic behind :func:`run`; callers that need the resulting counts (e.g.
    :func:`wayback_machine_downloader_companion.cli_launcher.run_full`, which loops until
    nothing is missing) should call this directly instead of re-parsing the exported
    ``missing_*.txt`` files that :func:`run` only reports as an exit code.

    Args:
        config (AppConfig): The active configuration.

    Returns:
        FinderResult: Whether a scan happened, and how many resources are missing.
    """
    files = sorted(config.folder_output.rglob('*.*'))
    if not files:
        logger.warning('Nothing found in %s -- Aborting', config.folder_output)
        return FinderResult(scanned=False, missing_count=0)

    html_files_path, html_files_str = get_all_files(files, HTML_EXT)
    _, other_files_str = get_all_files(files, OTHER_EXT)

    link_report = find_all_links(WBMHTMLParser(), html_files_path)

    html_report = sort_data(html_files_str, set(link_report.html_links), 'html')
    other_report = sort_data(other_files_str, set(link_report.other_links), 'other')

    export_missing(config.base_dir / MISSING_HTML_FILE, html_report.missing, config)
    export_missing(config.base_dir / MISSING_OTHER_FILE, other_report.missing, config)
    export_missing(config.base_dir / UNSPECIFIED_FILE, link_report.unspecified_links, config)

    logger.info('Done')
    return FinderResult(scanned=True, missing_count=len(html_report.missing) + len(other_report.missing))


def run(config: AppConfig, args: argparse.Namespace) -> int:
    """Scans downloaded HTML for missing local resources and exports the results.

    Args:
        config (AppConfig): The active configuration.
        args (argparse.Namespace): Parsed command-line arguments (unused, kept for a uniform
            CLI signature).

    Returns:
        int: ``0`` on success, ``1`` if nothing was found to scan.
    """
    return 0 if scan(config).scanned else 1
