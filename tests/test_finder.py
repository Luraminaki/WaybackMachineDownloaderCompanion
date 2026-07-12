"""Tests for wayback_machine_downloader_companion.finder."""

import pathlib

from wayback_machine_downloader_companion.finder import export_missing, get_all_files, scan, sort_data
from wayback_machine_downloader_companion.html_parser import HTML_EXT


def test_get_all_files_matches_exact_suffix(tmp_path: pathlib.Path) -> None:
    htm_file = tmp_path / 'page.htm'
    htm_file.touch()
    xhtml_file = tmp_path / 'page.xhtml'
    xhtml_file.touch()

    matched, matched_str = get_all_files([htm_file, xhtml_file], HTML_EXT)

    assert matched == [htm_file]
    assert matched_str == {htm_file.as_posix()}


def test_sort_data_reports_are_mutually_disjoint() -> None:
    """Missing and never-mentioned resources are set differences of disjoint origin.

    This is the invariant that made the old ``missing.pop(link)`` dead-code branch
    unreachable (and would have raised ``TypeError`` had it ever run).
    """
    local_files = {'a.htm', 'b.htm', 'orphan.htm'}
    found_links = {'a.htm', 'b.htm', 'missing.htm'}

    report = sort_data(local_files, found_links, 'html')

    assert report.common == ['a.htm', 'b.htm']
    assert report.missing == ['missing.htm']
    assert report.never_mentioned == ['orphan.htm']
    assert set(report.missing).isdisjoint(report.never_mentioned)


def test_export_missing_translates_local_paths_to_urls(tmp_path: pathlib.Path, make_config) -> None:
    config = make_config(web_folder='example.com', web_output='example.com_output')
    missing_path = (config.folder_output / 'sub' / 'page.htm').as_posix()

    export_file = tmp_path / 'missing.txt'
    export_missing(export_file, [missing_path], config)

    content = export_file.read_text(encoding='utf-8')
    assert content == 'https://example.com/sub/page.htm\n'


def test_scan_reports_not_scanned_when_output_folder_empty(make_config) -> None:
    config = make_config()
    config.folder_output.mkdir(parents=True)

    result = scan(config)

    assert result.scanned is False
    assert result.missing_count == 0


def test_scan_counts_missing_resources_and_writes_files(make_config) -> None:
    """Regression test: cli_launcher used to re-read missing_*.txt to get this same count.

    scan() now returns the count directly so callers don't need a redundant disk round-trip.
    """
    config = make_config()
    config.folder_output.mkdir(parents=True)
    (config.folder_output / 'index.htm').write_text(
        '<a href="missing.htm">x</a><img src="missing.png">', encoding='utf-8',
    )

    result = scan(config)

    assert result.scanned is True
    assert result.missing_count == 2
    assert (config.base_dir / 'missing_html.txt').exists()
    assert (config.base_dir / 'missing_other.txt').exists()
