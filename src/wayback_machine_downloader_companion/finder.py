#!/usr/bin/env python3
"""Find resources referenced by downloaded HTML pages that are missing locally.

On a case-insensitive output folder (macOS and Windows defaults), a link matches a local file
whatever the case of either: ``Page.HTM`` there is the local ``page.htm`` (see
:mod:`wayback_machine_downloader_companion._filesystem` for how case is compared).
"""

import dataclasses
import logging
import pathlib
import urllib.parse
from typing import TYPE_CHECKING

from wayback_machine_downloader_companion._filesystem import fold_key, is_case_insensitive
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
from wayback_machine_downloader_companion.merger import MANIFEST_FILE

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
SITE_EXT = HTML_EXT | OTHER_EXT


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


def _sort_folded(local_files: set[str], found_links: set[str]) -> SortedResourceReport:
    """Diffs local files against referenced links, ignoring case.

    Args:
        local_files (set[str]): Paths of the files that exist locally.
        found_links (set[str]): Links found while parsing the downloaded HTML.

    Returns:
        SortedResourceReport: The common and never-mentioned local files (named as on disk),
        and the missing links (named as in the pages; spellings of one file listed once).
    """
    local_keys = {file: fold_key(file, True) for file in local_files}
    found_keys = {link: fold_key(link, True) for link in found_links}
    folded_local, folded_found = set(local_keys.values()), set(found_keys.values())
    missing: dict[str, str] = {}  # folded key -> its first spelling, in sorted order
    for link in sorted(found_links):
        if found_keys[link] not in folded_local:
            _ = missing.setdefault(found_keys[link], link)
    return SortedResourceReport(
        common=sorted(file for file, key in local_keys.items() if key in folded_found),
        missing=list(missing.values()),
        never_mentioned=sorted(file for file, key in local_keys.items() if key not in folded_found),
    )


def sort_data(
    local_files: set[str], found_links: set[str], resource_name: str, fold_case: bool = False
) -> SortedResourceReport:
    """Diffs local files against referenced links.

    Args:
        local_files (set[str]): Paths of the files that exist locally.
        found_links (set[str]): Links found while parsing the downloaded HTML.
        resource_name (str): Label used for logging (e.g. ``"html"``).
        fold_case (bool): Match links and files whatever their case (case-insensitive
            filesystem, where they name the same file).

    Returns:
        SortedResourceReport: The common, missing, and never-mentioned resources.
    """
    report = (
        _sort_folded(local_files, found_links)
        if fold_case
        else SortedResourceReport(
            common=sorted(local_files & found_links),
            missing=sorted(found_links - local_files),
            never_mentioned=sorted(local_files - found_links),
        )
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
        ``None`` if ``link`` isn't inside the output folder. The output folder itself is the
        site root, ``https://<WEB_FOLDER>/``.
    """
    path, output = (
        pathlib.PurePosixPath(link),
        pathlib.PurePosixPath(config.folder_output.as_posix()),
    )
    if not path.is_relative_to(output):
        return None
    # relative_to gives "." for the folder itself, which would make "https://host/.".
    relative = "" if path == output else path.relative_to(output).as_posix()
    return f"https://{config.web_folder}/{urllib.parse.quote(relative)}"


def export_missing(
    file_path: "pathlib.Path",
    missing: list[str],
    config: "AppConfig",
    keep_unresolved: bool = False,
) -> list[str]:
    """Exports resources into a file, one URL per line.

    Local paths are turned back into site URLs (see :func:`to_wayback_url`); external links
    are written as they are. A link that is neither (one leaving the site folder, kept as
    written in the page) is written as is with `keep_unresolved`, left out otherwise: the
    downloader couldn't fetch it.

    Args:
        file_path (pathlib.Path): Destination file path.
        missing (list[str]): Resolved local paths, external links, or unresolved links.
        config (AppConfig): The active configuration, used to translate local paths into URLs.
        keep_unresolved (bool): Write unresolved links as they are, for review by hand.

    Returns:
        list[str]: The lines written, in order.
    """
    logger.info("Saving %s", file_path)
    # Local paths first: on Windows they start with a drive letter ("C:/..."), which
    # is_external takes for a URI scheme.
    candidates = [
        to_wayback_url(link, config) or (link if keep_unresolved or is_external(link) else None)
        for link in missing
    ]
    lines = [line for line in candidates if line is not None]
    skipped = len(candidates) - len(lines)
    if skipped:
        logger.warning(
            "%d link(s) outside %s left out of %s", skipped, config.folder_output, file_path
        )
    _ = file_path.write_text("".join(f"{line}\n" for line in lines), "utf-8")
    return lines


@dataclasses.dataclass(slots=True)
class FinderResult:
    """The outcome of a find run.

    Attributes:
        scanned (bool): ``False`` if there was nothing to scan (``config.folder_output`` is
            missing or has no site file, i.e. none with an extension of :data:`SITE_EXT`, the
            merge manifest aside), in which case the other fields are meaningless.
        missing_count (int): Total number of missing resources found (html + other).
        missing_urls (frozenset[str]): The URLs exported for download (``missing_html.txt``
            and ``missing_other.txt``).
    """

    scanned: bool
    missing_count: int
    missing_urls: frozenset[str] = frozenset()


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
    output = config.folder_output
    manifest = output / MANIFEST_FILE  # the merger's bookkeeping, not a site resource
    # Site files only: a leftover `.wmdc-*.tmp` (or any other file) is no reason to scan.
    files = [
        path
        for path in output.rglob("*.*")
        if path.suffix.lower() in SITE_EXT and path.is_file() and path != manifest
    ]
    if not files:
        logger.warning("No site file found in %s -- Aborting", output)
        return FinderResult(scanned=False, missing_count=0)
    fold_case = is_case_insensitive(files)  # read-only, from the files already listed

    html_files_path, html_files_str = get_all_files(files, HTML_EXT)
    _, other_files_str = get_all_files(files, OTHER_EXT)

    parser = WBMHTMLParser(HTML_EXT, OTHER_EXT, site_root=output)
    link_report = find_all_links(parser, html_files_path)

    html_report = sort_data(html_files_str, link_report.html_links, "html", fold_case)
    other_report = sort_data(other_files_str, link_report.other_links, "other", fold_case)

    html_urls = export_missing(config.base_dir / MISSING_HTML_FILE, html_report.missing, config)
    other_urls = export_missing(config.base_dir / MISSING_OTHER_FILE, other_report.missing, config)
    # Kept as written in the page: unspecified.txt is reviewed by hand, never downloaded.
    _ = export_missing(
        config.base_dir / UNSPECIFIED_FILE,
        sorted(link_report.unspecified_links),
        config,
        keep_unresolved=True,
    )

    logger.info("Done")
    return FinderResult(
        scanned=True,
        missing_count=len(html_report.missing) + len(other_report.missing),
        missing_urls=frozenset(html_urls + other_urls),
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
