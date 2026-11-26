"""Tests for wayback_machine_downloader_companion.finder."""

import argparse
from typing import TYPE_CHECKING

from wayback_machine_downloader_companion.finder import (
    HTML_EXT,
    export_missing,
    get_all_files,
    run,
    scan,
    sort_data,
)

if TYPE_CHECKING:
    import pathlib

    from tests.conftest import MakeConfig


def test_get_all_files_matches_exact_suffix(tmp_path: "pathlib.Path") -> None:
    """Files are matched on their exact suffix, not a substring."""
    htm_file = tmp_path / "page.htm"
    htm_file.touch()
    xhtml_file = tmp_path / "page.xhtml"
    xhtml_file.touch()

    matched, matched_str = get_all_files([htm_file, xhtml_file], HTML_EXT)

    assert matched == [htm_file]
    assert matched_str == {htm_file.as_posix()}


def test_sort_data_reports_are_mutually_disjoint() -> None:
    """Missing and never-mentioned resources are set differences of disjoint origin.

    This is the invariant that made the old ``missing.pop(link)`` dead-code branch
    unreachable (and would have raised ``TypeError`` had it ever run).
    """
    local_files = {"a.htm", "b.htm", "orphan.htm"}
    found_links = {"a.htm", "b.htm", "missing.htm"}

    report = sort_data(local_files, found_links, "html")

    assert report.common == ["a.htm", "b.htm"]
    assert report.missing == ["missing.htm"]
    assert report.never_mentioned == ["orphan.htm"]
    assert set(report.missing).isdisjoint(report.never_mentioned)


def test_export_missing_translates_local_paths_to_urls(
    tmp_path: "pathlib.Path", make_config: "MakeConfig"
) -> None:
    """Missing local paths are exported as the URLs to download."""
    config = make_config(web_folder="example.com", web_output="example.com_output")
    missing_path = (config.folder_output / "sub" / "page.htm").as_posix()

    export_file = tmp_path / "missing.txt"
    export_missing(export_file, [missing_path], config)

    content = export_file.read_text(encoding="utf-8")
    assert content == "https://example.com/sub/page.htm\n"


def test_scan_reports_not_scanned_when_output_folder_empty(make_config: "MakeConfig") -> None:
    """An empty output folder is reported as not scanned."""
    config = make_config()
    config.folder_output.mkdir(parents=True)

    result = scan(config)

    assert result.scanned is False
    assert result.missing_count == 0


def test_scan_counts_missing_resources_and_writes_files(make_config: "MakeConfig") -> None:
    """Regression test: cli_launcher used to re-read missing_*.txt to get this same count.

    scan() now returns the count directly so callers don't need a redundant disk round-trip.
    """
    config = make_config()
    config.folder_output.mkdir(parents=True)
    _ = (config.folder_output / "index.htm").write_text(
        '<a href="missing.htm">x</a><img src="missing.png">',
        encoding="utf-8",
    )

    result = scan(config)

    assert result.scanned is True
    assert result.missing_count == 2
    assert (config.base_dir / "missing_html.txt").exists()
    assert (config.base_dir / "missing_other.txt").exists()


def test_run_returns_zero_when_scanned(make_config: "MakeConfig") -> None:
    """A completed scan returns 0."""
    config = make_config()
    config.folder_output.mkdir(parents=True)
    _ = (config.folder_output / "index.htm").write_text(
        '<a href="other.htm">x</a>', encoding="utf-8"
    )

    assert run(config, argparse.Namespace()) == 0


def test_run_returns_one_when_nothing_to_scan(make_config: "MakeConfig") -> None:
    """Nothing to scan returns 1."""
    config = make_config()
    config.folder_output.mkdir(parents=True)

    assert run(config, argparse.Namespace()) == 1


def test_export_builds_urls_from_the_path_inside_the_output(make_config: "MakeConfig") -> None:
    """URLs come from the path inside the output folder, percent-encoded.

    Regression test: a plain text replace turned `out/layout/out.css` into `laysite/site.css`.
    """
    config = make_config(web_folder="site", web_output="out")
    export_file = config.base_dir / "export.txt"
    links = [
        (config.folder_output / "layout" / "out.css").as_posix(),
        (config.folder_output / "my page.htm").as_posix(),
        "https://cdn.example.com/x.js",
        "/etc/passwd",
    ]

    export_missing(export_file, links, config)

    assert export_file.read_text(encoding="utf-8").splitlines() == [
        "https://site/layout/out.css",
        "https://site/my%20page.htm",
        "https://cdn.example.com/x.js",
    ]


def test_unspecified_export_keeps_links_leaving_the_site(make_config: "MakeConfig") -> None:
    """unspecified.txt lists links that escape the site as written; missing lists don't."""
    config = make_config()
    kept, dropped = config.base_dir / "unspecified.txt", config.base_dir / "missing.txt"

    export_missing(kept, ["../../x.htm"], config, keep_unresolved=True)
    export_missing(dropped, ["../../x.htm"], config)

    assert kept.read_text(encoding="utf-8") == "../../x.htm\n"
    assert dropped.read_text(encoding="utf-8") == ""
