"""Tests for wayback_machine_downloader_companion.html_parser."""

import pathlib

import pytest

from wayback_machine_downloader_companion.html_parser import WBMHTMLParser, find_all_links


def test_parser_instances_do_not_share_state() -> None:
    """Regression test: link buffers used to be class attributes shared across instances."""
    first = WBMHTMLParser()
    first.feed('<a href="page.htm">link</a>')
    assert first.html_links == [pathlib.Path('page.htm').resolve().as_posix()]

    second = WBMHTMLParser()
    assert second.html_links == []
    assert second.other_links == []
    assert second.unspecified_links == []


def test_xhtml_link_is_not_misclassified_as_html() -> None:
    """Regression test: extension matching used to be a naive substring check."""
    parser = WBMHTMLParser()
    parser.feed('<a href="page.xhtml">link</a>')

    assert parser.html_links == []
    assert parser.unspecified_links == [pathlib.Path('page.xhtml').resolve().as_posix()]


def test_other_ext_matching_is_exact() -> None:
    parser = WBMHTMLParser()
    parser.feed('<img src="thumbnails.png">')

    assert parser.other_links == [pathlib.Path('thumbnails.png').resolve().as_posix()]


def test_absolute_links_are_unspecified_regardless_of_extension() -> None:
    parser = WBMHTMLParser()
    parser.feed('<img src="http://cdn.example.com/logo.png">')

    assert parser.other_links == []
    assert parser.unspecified_links == ['http://cdn.example.com/logo.png']


def test_query_string_is_stripped_from_resolved_link() -> None:
    """Regression test: the query string used to survive into the stored link path.

    A suffix like '.png?v=2' would never match a real on-disk 'logo.png', so the file was
    reported missing (and re-downloaded) even though it already existed locally.
    """
    parser = WBMHTMLParser()
    parser.feed('<img src="logo.png?v=2">')

    assert parser.other_links == [pathlib.Path('logo.png').resolve().as_posix()]


def test_unspecified_relative_link_is_resolved() -> None:
    """Regression test: relative links with an unrecognized extension used to be stored raw.

    Storing them unresolved made export_missing's path-translation a no-op for these entries,
    producing a garbage line (the raw href) instead of a usable URL in unspecified.txt.
    """
    parser = WBMHTMLParser()
    parser.feed('<a href="page.xhtml">link</a>')

    assert parser.unspecified_links == [pathlib.Path('page.xhtml').resolve().as_posix()]


def test_find_all_links_reports_corrupted_files(tmp_path: pathlib.Path) -> None:
    good_file = tmp_path / 'good.htm'
    good_file.write_text('<a href="other.htm">link</a>', encoding='utf-8')

    bad_file = tmp_path / 'bad.htm'
    bad_file.write_bytes(b'\xff\xfe not utf-8')

    report = find_all_links(WBMHTMLParser(), [good_file, bad_file])

    assert report.corrupted_files == [str(bad_file)]
    assert any(link.endswith('other.htm') for link in report.html_links)


def test_find_all_links_survives_unexpected_parser_errors(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: a single file raising any exception must not abort the whole batch.

    The per-file exception handling used to be narrowed to (OSError, UnicodeDecodeError) only,
    so an unanticipated error type from a malformed/corrupted page would propagate and abort
    the whole find run instead of being logged as one corrupted file among many.
    """
    good_file = tmp_path / 'good.htm'
    good_file.write_text('<a href="other.htm">link</a>', encoding='utf-8')

    bad_file = tmp_path / 'bad.htm'
    bad_file.write_text('<a href="bad.htm">link</a>', encoding='utf-8')

    parser = WBMHTMLParser()
    original_feed = parser.feed

    def flaky_feed(data: str) -> None:
        if 'bad.htm' in data:
            raise ValueError('simulated parser failure')
        original_feed(data)

    monkeypatch.setattr(parser, 'feed', flaky_feed)

    report = find_all_links(parser, [good_file, bad_file])

    assert report.corrupted_files == [str(bad_file)]
    assert any(link.endswith('other.htm') for link in report.html_links)
