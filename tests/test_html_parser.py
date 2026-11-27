"""Tests for wayback_machine_downloader_companion.html_parser."""

import pathlib

import pytest

from wayback_machine_downloader_companion import html_parser
from wayback_machine_downloader_companion.finder import HTML_EXT, OTHER_EXT
from wayback_machine_downloader_companion.html_parser import (
    LINK_ATTRIBUTES,
    WBMHTMLParser,
    decode_page,
    find_all_links,
    normalize,
)


def make_parser(site_root: pathlib.Path) -> WBMHTMLParser:
    """Builds a parser with the production extension sets, for concise test setup.

    Args:
        site_root (pathlib.Path): The site folder (always explicit: the default is the CWD).

    Returns:
        WBMHTMLParser: A parser whose current folder is ``site_root``.
    """
    return WBMHTMLParser(HTML_EXT, OTHER_EXT, site_root=site_root)


def parse(site_root: pathlib.Path, html: str) -> WBMHTMLParser:
    """Parses one page located at the site root.

    Args:
        site_root (pathlib.Path): The site folder, also the page's folder.
        html (str): The page's HTML.

    Returns:
        WBMHTMLParser: The parser holding the page's links.
    """
    parser = make_parser(site_root)
    parser.parse_page(html, site_root)
    return parser


def write_pages(site: pathlib.Path, pages: dict[str, bytes]) -> list[pathlib.Path]:
    """Writes pages under a site folder.

    Args:
        site (pathlib.Path): The site folder.
        pages (dict[str, bytes]): Relative path -> raw content.

    Returns:
        list[pathlib.Path]: The written files, in the given order.
    """
    files: list[pathlib.Path] = []
    for relative, content in pages.items():
        file = site / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        _ = file.write_bytes(content)
        files.append(file)
    return files


def test_parser_instances_do_not_share_state(tmp_path: pathlib.Path) -> None:
    """Regression test: link buffers used to be class attributes shared across instances."""
    first = parse(tmp_path, '<a href="page.htm">link</a>')
    assert first.html_links == {(tmp_path / "page.htm").as_posix()}

    second = make_parser(tmp_path)
    assert second.html_links == set()
    assert second.other_links == set()
    assert second.unspecified_links == set()


def test_xhtml_link_is_not_misclassified_as_html(tmp_path: pathlib.Path) -> None:
    """Regression test: extension matching used to be a naive substring check.

    The relative link is stored resolved, so unspecified.txt can turn it into a URL.
    """
    parser = parse(tmp_path, '<a href="page.xhtml">link</a>')

    assert parser.html_links == set()
    assert parser.unspecified_links == {(tmp_path / "page.xhtml").as_posix()}


def test_other_ext_matching_is_exact(tmp_path: pathlib.Path) -> None:
    """Non-HTML extensions are matched exactly, not by prefix."""
    parser = parse(tmp_path, '<img src="thumbnails.png">')

    assert parser.other_links == {(tmp_path / "thumbnails.png").as_posix()}


@pytest.mark.parametrize(
    "link",
    [
        "http://cdn.example.com/logo.png",
        "//cdn.example.com/logo.png",
        "mailto:someone@example.com",
        "javascript:void(0)",
    ],
)
def test_external_links_are_unspecified_as_written(tmp_path: pathlib.Path, link: str) -> None:
    """Regression test: protocol-relative and non-http links used to resolve as local paths."""
    parser = parse(tmp_path, f'<img src="{link}">')

    assert parser.other_links == set()
    assert parser.unspecified_links == {link}


@pytest.mark.parametrize("link", ["#top", "", "?a=1", "?a=1#top"])
def test_links_without_a_path_are_not_resources(tmp_path: pathlib.Path, link: str) -> None:
    """Anchor-only, empty and query-only links point back at the page, not a resource."""
    parser = parse(tmp_path, f'<a href="{link}">x</a><img src="{link}">')

    assert parser.html_links == set()
    assert parser.other_links == set()
    assert parser.unspecified_links == set()


def test_query_string_is_stripped_from_resolved_link(tmp_path: pathlib.Path) -> None:
    """Regression test: '.png?v=2' used to survive and never match the local 'logo.png'."""
    parser = parse(tmp_path, '<img src="logo.png?v=2">')

    assert parser.other_links == {(tmp_path / "logo.png").as_posix()}


def test_root_relative_link_resolves_against_site_root(tmp_path: pathlib.Path) -> None:
    """Regression test: root-relative links used to resolve under the current page's folder."""
    parser = make_parser(tmp_path)
    parser.parse_page('<link href="/css/style.css">', tmp_path / "sub" / "dir")

    assert parser.other_links == {(tmp_path / "css" / "style.css").as_posix()}


def test_backslash_counts_as_a_folder_separator(tmp_path: pathlib.Path) -> None:
    r"""`images\logo.gif` (Windows-made sites) names `images/logo.gif`, as browsers read it.

    It used to stay a single segment on POSIX, exported as `images%5Clogo.gif`.
    """
    parser = make_parser(tmp_path)
    parser.parse_page(r'<img src="images\logo.gif"><a href="..\up.htm">u</a>', tmp_path / "sub")

    assert parser.other_links == {(tmp_path / "sub" / "images" / "logo.gif").as_posix()}
    assert parser.html_links == {(tmp_path / "up.htm").as_posix()}


def test_backslash_protocol_relative_link_is_external(tmp_path: pathlib.Path) -> None:
    r"""`\\cdn.example.com\x.png` is `//cdn.example.com/x.png` to a browser: off-site."""
    link = r"\\cdn.example.com\x.png"
    parser = parse(tmp_path, f'<img src="{link}">')

    assert parser.other_links == set()
    assert parser.unspecified_links == {link}


def test_find_all_links_reports_corrupted_files(tmp_path: pathlib.Path) -> None:
    """Files that can't be read are reported, not silently skipped."""
    good_file = tmp_path / "good.htm"
    _ = good_file.write_text('<a href="other.htm">link</a>', encoding="utf-8")
    bad_file = tmp_path / "vanished.htm"  # listed, but gone before it could be read

    report = find_all_links(make_parser(tmp_path), [good_file, bad_file])

    assert report.corrupted_files == [str(bad_file)]
    assert report.html_links == {(tmp_path / "other.htm").as_posix()}


def test_unclosed_script_does_not_swallow_the_next_page(tmp_path: pathlib.Path) -> None:
    """A page ending inside `<script>` used to turn the next page into script text."""
    files = write_pages(
        tmp_path, {"a.htm": b"<script>var x = 1;", "b.htm": b'<a href="next.htm">n</a>'}
    )

    report = find_all_links(make_parser(tmp_path), files)

    assert report.html_links == {(tmp_path / "next.htm").as_posix()}


def test_unclosed_tag_is_resolved_against_its_own_page(tmp_path: pathlib.Path) -> None:
    """A tag cut at the end of a page used to be resolved against the next page's folder."""
    files = write_pages(
        tmp_path, {"b/a.htm": b'<a href="x.htm"', "c/b.htm": b'<a href="y.htm">y</a>'}
    )

    report = find_all_links(make_parser(tmp_path), files)

    assert report.html_links == {(tmp_path / "c" / "y.htm").as_posix()}


def test_cp1252_page_keeps_its_accented_links(tmp_path: pathlib.Path) -> None:
    """A non-UTF-8 page is decoded, not skipped as corrupted, and its accents survive."""
    files = write_pages(tmp_path, {"page.htm": '<a href="été.htm">é</a>'.encode("cp1252")})

    report = find_all_links(make_parser(tmp_path), files)

    assert report.corrupted_files == []
    assert report.html_links == {(tmp_path / "été.htm").as_posix()}


def test_decode_page_falls_back_to_latin1_for_bytes_cp1252_lacks() -> None:
    """0x81 is undefined in cp1252: Latin-1 takes it rather than failing."""
    assert decode_page(b"caf\xe9\x81") == "caf\xe9\x81"


def test_decode_page_drops_the_utf8_bom() -> None:
    """A UTF-8 BOM is not page text (it used to be kept as U+FEFF before the first tag)."""
    assert decode_page(b"\xef\xbb\xbf<a href='\xc3\xa9.htm'>") == "<a href='é.htm'>"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/../../x", "/x"),
        ("/a/b/../../../c", "/c"),
        ("/a/./b/../c", "/a/c"),
        ("/a/b", "/a/b"),
    ],
)
def test_normalize_folds_dotdot_without_climbing_above_root(path: str, expected: str) -> None:
    """`..` segments are folded lexically and never climb above the root."""
    assert normalize(pathlib.PurePosixPath(path)) == pathlib.PurePosixPath(expected)


@pytest.mark.parametrize(
    ("tag", "attribute"),
    sorted((tag, attribute) for tag, names in LINK_ATTRIBUTES.items() for attribute in names),
)
def test_every_link_attribute_is_collected(
    tmp_path: pathlib.Path, tag: str, attribute: str
) -> None:
    """Each tag/attribute pair of LINK_ATTRIBUTES yields a link."""
    parser = parse(tmp_path, f'<{tag} {attribute}="res.css">')

    assert parser.other_links == {(tmp_path / "res.css").as_posix()}


@pytest.mark.parametrize(
    "html",
    [
        '<div href="x.css">',  # tag not in LINK_ATTRIBUTES
        '<img href="x.css">',  # known tag, attribute it doesn't link with
        "<a href>x</a>",  # valueless attribute
    ],
)
def test_non_link_attributes_are_ignored(tmp_path: pathlib.Path, html: str) -> None:
    """Only the attributes listed in LINK_ATTRIBUTES, with a value, are links."""
    parser = parse(tmp_path, html)

    assert parser.html_links == parser.other_links == parser.unspecified_links == set()


@pytest.mark.parametrize("html", ['<IMG SRC="Logo.PNG">', '<img src="Logo.PNG"/>'])
def test_uppercase_and_self_closing_tags_are_collected(tmp_path: pathlib.Path, html: str) -> None:
    """Tag and attribute names are case-insensitive; `<img/>` counts; the path keeps its case."""
    parser = parse(tmp_path, html)

    assert parser.other_links == {(tmp_path / "Logo.PNG").as_posix()}


def test_same_link_resolves_per_folder(tmp_path: pathlib.Path) -> None:
    """A relative link is resolved against each page's own folder, not a cached one."""
    files = write_pages(
        tmp_path, {"a/1.htm": b'<img src="x.png">', "b/2.htm": b'<img src="x.png">'}
    )

    report = find_all_links(make_parser(tmp_path), files)

    assert report.other_links == {(tmp_path / d / "x.png").as_posix() for d in ("a", "b")}


def test_repeated_link_is_resolved_once_per_folder(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pages of one folder repeating a link resolve it once; another folder resolves again."""
    resolved: list[pathlib.PurePath] = []

    def spy(path: pathlib.PurePath) -> pathlib.PurePath:
        """Record the path, then normalise it as the parser would.

        Args:
            path: The path, recorded.

        Returns:
            The normalised path.
        """
        resolved.append(path)
        return normalize(path)

    monkeypatch.setattr(html_parser, "normalize", spy)
    page = b'<img src="x.png"><img src="x.png?v=2">'
    files = write_pages(tmp_path, {"a/1.htm": page, "a/2.htm": page, "b/3.htm": page})

    _ = find_all_links(make_parser(tmp_path), files)

    assert [path for path in resolved if path.name == "x.png"] == [
        tmp_path / "a" / "x.png",
        tmp_path / "b" / "x.png",
    ]


def test_links_leaving_the_site_are_unspecified_as_written(tmp_path: pathlib.Path) -> None:
    """`../../x.htm` past the site folder is kept raw, each variant as written in the page."""
    parser = make_parser(tmp_path / "site")
    parser.parse_page(
        '<a href="../../x.htm?a">x</a><a href="../../x.htm?b">x</a>', tmp_path / "site" / "sub"
    )

    assert parser.html_links == set()
    assert parser.unspecified_links == {"../../x.htm?a", "../../x.htm?b"}


def test_percent_encoded_link_matches_the_local_file_name(tmp_path: pathlib.Path) -> None:
    """`my%20page.htm` names the local file `my page.htm`."""
    parser = parse(tmp_path, '<a href="my%20page.htm">p</a>')

    assert parser.html_links == {(tmp_path / "my page.htm").as_posix()}
