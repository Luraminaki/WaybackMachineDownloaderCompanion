"""Tests for wayback_machine_downloader_companion.html_parser."""

import pathlib

from wayback_machine_downloader_companion.finder import HTML_EXT, OTHER_EXT
from wayback_machine_downloader_companion.html_parser import WBMHTMLParser, find_all_links


def make_parser(site_root: pathlib.Path | None = None) -> WBMHTMLParser:
    """Builds a parser with the production extension sets, for concise test setup."""
    return WBMHTMLParser(HTML_EXT, OTHER_EXT, site_root=site_root)


def test_parser_instances_do_not_share_state() -> None:
    """Regression test: link buffers used to be class attributes shared across instances."""
    first = make_parser()
    first.feed('<a href="page.htm">link</a>')
    assert first.html_links == {pathlib.Path("page.htm").resolve().as_posix()}

    second = make_parser()
    assert second.html_links == set()
    assert second.other_links == set()
    assert second.unspecified_links == set()


def test_xhtml_link_is_not_misclassified_as_html() -> None:
    """Regression test: extension matching used to be a naive substring check."""
    parser = make_parser()
    parser.feed('<a href="page.xhtml">link</a>')

    assert parser.html_links == set()
    assert parser.unspecified_links == {pathlib.Path("page.xhtml").resolve().as_posix()}


def test_other_ext_matching_is_exact() -> None:
    """Non-HTML extensions are matched exactly, not by prefix."""
    parser = make_parser()
    parser.feed('<img src="thumbnails.png">')

    assert parser.other_links == {pathlib.Path("thumbnails.png").resolve().as_posix()}


def test_absolute_links_are_unspecified_regardless_of_extension() -> None:
    """Absolute links are classed unspecified, whatever their extension."""
    parser = make_parser()
    parser.feed('<img src="http://cdn.example.com/logo.png">')

    assert parser.other_links == set()
    assert parser.unspecified_links == {"http://cdn.example.com/logo.png"}


def test_protocol_relative_link_is_treated_as_external() -> None:
    """Regression test: only 'http'-prefixed links used to be recognized as external.

    A protocol-relative link (``//cdn.example.com/...``) used to fall through to the local
    resolution branch, producing a bogus nested local path that could never exist on disk.
    """
    parser = make_parser()
    parser.feed('<img src="//cdn.example.com/logo.png">')

    assert parser.other_links == set()
    assert parser.unspecified_links == {"//cdn.example.com/logo.png"}


def test_non_http_scheme_link_is_treated_as_external() -> None:
    """Regression test: mailto:/tel:/javascript: links used to be resolved as local paths."""
    parser = make_parser()
    parser.feed('<a href="mailto:someone@example.com">contact</a>')

    assert parser.unspecified_links == {"mailto:someone@example.com"}


def test_anchor_only_link_is_not_a_resource() -> None:
    """Regression test: href="#top" used to resolve to the containing directory itself."""
    parser = make_parser()
    parser.feed('<a href="#top">Back to top</a>')

    assert parser.html_links == set()
    assert parser.other_links == set()
    assert parser.unspecified_links == set()


def test_query_string_is_stripped_from_resolved_link() -> None:
    """Regression test: the query string used to survive into the stored link path.

    A suffix like '.png?v=2' would never match a real on-disk 'logo.png', so the file was
    reported missing (and re-downloaded) even though it already existed locally.
    """
    parser = make_parser()
    parser.feed('<img src="logo.png?v=2">')

    assert parser.other_links == {pathlib.Path("logo.png").resolve().as_posix()}


def test_unspecified_relative_link_is_resolved() -> None:
    """Regression test: relative links with an unrecognized extension used to be stored raw.

    Storing them unresolved made export_missing's path-translation a no-op for these entries,
    producing a garbage line (the raw href) instead of a usable URL in unspecified.txt.
    """
    parser = make_parser()
    parser.feed('<a href="page.xhtml">link</a>')

    assert parser.unspecified_links == {pathlib.Path("page.xhtml").resolve().as_posix()}


def test_root_relative_link_resolves_against_site_root(tmp_path: pathlib.Path) -> None:
    """Regression test: root-relative links used to resolve under the current page's folder.

    ``href="/css/style.css"`` is relative to the site root, not to whatever subfolder the
    referencing page happens to live in.
    """
    site_root = tmp_path / "example.com_output"
    current_file_dir = site_root / "sub" / "dir"

    parser = WBMHTMLParser(HTML_EXT, OTHER_EXT, site_root=site_root)
    parser.current_path = str(current_file_dir)
    parser.feed('<link href="/css/style.css">')

    assert parser.other_links == {(site_root / "css" / "style.css").resolve().as_posix()}


def test_find_all_links_reports_corrupted_files(tmp_path: pathlib.Path) -> None:
    """Files that can't be read are reported, not silently skipped."""
    good_file = tmp_path / "good.htm"
    _ = good_file.write_text('<a href="other.htm">link</a>', encoding="utf-8")

    bad_file = tmp_path / "vanished.htm"  # listed, but gone before it could be read

    report = find_all_links(make_parser(tmp_path), [good_file, bad_file])

    assert report.corrupted_files == [str(bad_file)]
    assert any(link.endswith("other.htm") for link in report.html_links)


def write_pages(site: pathlib.Path, pages: dict[str, bytes]) -> list[pathlib.Path]:
    """Write pages under a site folder.

    Args:
        site: The site folder.
        pages: Relative path -> raw content.

    Returns:
        The written files, in the given order.
    """
    files = []
    for relative, content in pages.items():
        file = site / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        _ = file.write_bytes(content)
        files.append(file)
    return files


def test_unclosed_script_does_not_swallow_the_next_page(tmp_path: pathlib.Path) -> None:
    """A page ending inside `<script>` used to turn the next page into script text."""
    files = write_pages(
        tmp_path, {"a.htm": b"<script>var x = 1;", "b.htm": b'<a href="next.htm">n</a>'}
    )

    report = find_all_links(make_parser(tmp_path), files)

    assert report.html_links == [(tmp_path / "next.htm").as_posix()]


def test_unclosed_tag_is_resolved_against_its_own_page(tmp_path: pathlib.Path) -> None:
    """A tag cut at the end of a page used to be resolved against the next page's folder."""
    files = write_pages(
        tmp_path, {"b/a.htm": b'<a href="x.htm"', "c/b.htm": b'<a href="y.htm">y</a>'}
    )

    report = find_all_links(make_parser(tmp_path), files)

    assert (tmp_path / "c" / "x.htm").as_posix() not in report.html_links
    assert (tmp_path / "c" / "y.htm").as_posix() in report.html_links


def test_cp1252_page_keeps_its_accented_links(tmp_path: pathlib.Path) -> None:
    """A non-UTF-8 page is decoded, not skipped as corrupted, and its accents survive."""
    files = write_pages(tmp_path, {"page.htm": '<a href="été.htm">é</a>'.encode("cp1252")})

    report = find_all_links(make_parser(tmp_path), files)

    assert report.corrupted_files == []
    assert report.html_links == [(tmp_path / "été.htm").as_posix()]


def test_script_iframe_and_background_links_are_collected(tmp_path: pathlib.Path) -> None:
    """Resource links outside a/img/link/frame are found too."""
    parser = make_parser(tmp_path)
    parser.parse_page(
        '<script src="app.js"></script><iframe src="frame.htm"></iframe>'
        + '<body background="bg.gif"><object data="movie.swf"></object>',
        tmp_path,
    )

    assert parser.html_links == {(tmp_path / "frame.htm").as_posix()}
    assert {(tmp_path / name).as_posix() for name in ("app.js", "bg.gif")} <= parser.other_links


def test_links_leaving_the_site_are_unspecified(tmp_path: pathlib.Path) -> None:
    """`../../x.htm` past the site folder can't be one of its local files."""
    parser = make_parser(tmp_path / "site")
    parser.parse_page('<a href="../../x.htm">x</a>', tmp_path / "site" / "sub")

    assert parser.html_links == set()
    assert parser.unspecified_links == {"../../x.htm"}


def test_percent_encoded_link_matches_the_local_file_name(tmp_path: pathlib.Path) -> None:
    """`my%20page.htm` names the local file `my page.htm`."""
    parser = make_parser(tmp_path)
    parser.parse_page('<a href="my%20page.htm">p</a>', tmp_path)

    assert parser.html_links == {(tmp_path / "my page.htm").as_posix()}
