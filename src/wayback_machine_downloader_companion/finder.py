#!/usr/bin/env python3
"""Find resources referenced by downloaded HTML pages that are missing locally."""

import dataclasses
import logging
import pathlib
import urllib.parse
from typing import TYPE_CHECKING

from wayback_machine_downloader_companion.config import (
    MISSING_HTML_FILE,
    MISSING_OTHER_FILE,
    UNSPECIFIED_FILE,
)
from wayback_machine_downloader_companion.html_parser import (
    WBMHTMLParser,
    find_all_links,
    is_external,
)

if TYPE_CHECKING:
    import argparse

    from wayback_machine_downloader_companion.config import (
        AppConfig,
    )

logger = logging.getLogger(__name__)

HTML_EXT = frozenset({".htm", ".html"})
OTHER_EXT = frozenset(
    {
        ".css",
        ".gif",
        ".jpg",
        ".jpeg",
        ".png",
        ".ico",
        ".js",
        ".mjs",
        ".svg",
        ".webp",
        ".bmp",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".otf",
        ".pdf",
        ".json",
        ".xml",
        ".txt",
        ".mp3",
        ".mp4",
        ".webm",
    }
)


def get_all_files(
    files: list["pathlib.Path"], exts: frozenset[str]
) -> tuple[list["pathlib.Path"], set[str]]:
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
    logger.info("Found %d file(s) matching %s", len(matched), sorted(exts))
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


def sort_data(
    local_files: set[str], found_links: set[str], resource_name: str
) -> SortedResourceReport:
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

    logger.info("Found %d existing %s resource(s)", len(report.common), resource_name)
    logger.info("Found %d missing %s resource(s)", len(report.missing), resource_name)
    logger.info(
        "Found %d existing but never 'called' %s resource(s)",
        len(report.never_mentioned),
        resource_name,
    )

    return report


def to_wayback_url(link: str, config: "AppConfig") -> str | None:
    """Turns a local resource path back into the site URL to download.

    Args:
        link (str): A resolved local path inside the output folder (posix style).
        config (AppConfig): The active configuration.

    Returns:
        str | None: ``https://<WEB_FOLDER>/<path relative to WEB_OUTPUT>``, percent-encoded;
        ``None`` if ``link`` isn't inside the output folder.
    """
    path, output = (
        pathlib.PurePosixPath(link),
        pathlib.PurePosixPath(config.folder_output.as_posix()),
    )
    if not path.is_relative_to(output):
        return None
    relative = path.relative_to(output).as_posix()
    return f"https://{config.web_folder}/{urllib.parse.quote(relative)}"


def export_missing(file_path: "pathlib.Path", missing: list[str], config: "AppConfig") -> None:
    """Exports resources into a file, one URL per line.

    Local paths are turned back into site URLs (see :func:`to_wayback_url`); external links
    are written as they are; local paths outside the output folder are left out.

    Args:
        file_path (pathlib.Path): Destination file path.
        missing (list[str]): Resolved local paths, or external links.
        config (AppConfig): The active configuration, used to translate local paths into URLs.
    """
    logger.info("Saving %s", file_path)
    lines = [link if is_external(link) else to_wayback_url(link, config) for link in missing]
    skipped = lines.count(None)
    if skipped:
        logger.warning(
            "%d link(s) outside %s left out of %s", skipped, config.folder_output, file_path
        )
    _ = file_path.write_text("".join(f"{line}\n" for line in lines if line is not None), "utf-8")


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


def scan(config: "AppConfig") -> FinderResult:
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
    files = [path for path in config.folder_output.rglob("*.*") if path.is_file()]
    if not files:
        logger.warning("Nothing found in %s -- Aborting", config.folder_output)
        return FinderResult(scanned=False, missing_count=0)

    html_files_path, html_files_str = get_all_files(files, HTML_EXT)
    _, other_files_str = get_all_files(files, OTHER_EXT)

    parser = WBMHTMLParser(HTML_EXT, OTHER_EXT, site_root=config.folder_output)
    link_report = find_all_links(parser, html_files_path)

    html_report = sort_data(html_files_str, set(link_report.html_links), "html")
    other_report = sort_data(other_files_str, set(link_report.other_links), "other")

    export_missing(config.base_dir / MISSING_HTML_FILE, html_report.missing, config)
    export_missing(config.base_dir / MISSING_OTHER_FILE, other_report.missing, config)
    export_missing(config.base_dir / UNSPECIFIED_FILE, link_report.unspecified_links, config)

    logger.info("Done")
    return FinderResult(
        scanned=True, missing_count=len(html_report.missing) + len(other_report.missing)
    )


def run(config: "AppConfig", args: "argparse.Namespace") -> int:
    """Scans downloaded HTML for missing local resources and exports the results.

    Args:
        config (AppConfig): The active configuration.
        args (argparse.Namespace): Parsed command-line arguments (unused, kept for a uniform
            CLI signature).

    Returns:
        int: ``0`` on success, ``1`` if nothing was found to scan.
    """
    del args
    return 0 if scan(config).scanned else 1
