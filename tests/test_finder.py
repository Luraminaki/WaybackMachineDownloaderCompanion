"""Tests for wayback_machine_downloader_companion.finder."""

import argparse
import logging
import os
import pathlib
import sys
from typing import TYPE_CHECKING

import pytest

from wayback_machine_downloader_companion import finder
from wayback_machine_downloader_companion._filesystem import is_case_insensitive
from wayback_machine_downloader_companion.config import AppConfig
from wayback_machine_downloader_companion.finder import (
    HTML_EXT,
    export_missing,
    get_all_files,
    run,
    scan,
    sort_data,
    to_wayback_url,
)
from wayback_machine_downloader_companion.merger import MANIFEST_FILE

if TYPE_CHECKING:
    from collections.abc import Iterable

    from tests.conftest import MakeConfig


def write_site(config: AppConfig, files: dict[str, str]) -> None:
    """Writes files into the output folder of a configuration.

    Args:
        config (AppConfig): The configuration whose ``folder_output`` receives the files.
        files (dict[str, str]): Path relative to the output folder -> text content.
    """
    for relative, content in files.items():
        file = config.folder_output / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        _ = file.write_text(content, encoding="utf-8")


def read_exports(config: AppConfig) -> tuple[str, str, str]:
    """Reads the three files a scan exports.

    Args:
        config (AppConfig): The configuration the scan ran with.

    Returns:
        tuple[str, str, str]: missing_html.txt, missing_other.txt and unspecified.txt.
    """
    names = ("missing_html.txt", "missing_other.txt", "unspecified.txt")
    texts = [(config.base_dir / name).read_text(encoding="utf-8") for name in names]
    return texts[0], texts[1], texts[2]


@pytest.fixture(name="case_insensitive")
def fixture_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """Forces what the finder's filesystem case detection answers.

    Args:
        monkeypatch (pytest.MonkeyPatch): Pytest's monkeypatch fixture.

    Returns:
        list[bool]: A one-item list; set item 0 to ``True`` to make the output folder
        case-insensitive (``False``, case-sensitive, by default).
    """
    answer = [False]

    def probe(_entries: "Iterable[pathlib.Path]") -> bool:
        """Answer the scripted case sensitivity.

        Args:
            _entries: Ignored.

        Returns:
            The current scripted answer.
        """
        return answer[0]

    monkeypatch.setattr(finder, "is_case_insensitive", probe)
    return answer


def test_get_all_files_matches_exact_suffix(tmp_path: pathlib.Path) -> None:
    """Files are matched on their exact suffix, not a substring."""
    htm_file = tmp_path / "page.htm"
    htm_file.touch()
    xhtml_file = tmp_path / "page.xhtml"
    xhtml_file.touch()

    matched, matched_str = get_all_files([htm_file, xhtml_file], HTML_EXT)

    assert matched == [htm_file]
    assert matched_str == {htm_file.as_posix()}


def test_sort_data_splits_common_missing_and_never_mentioned() -> None:
    """Local files and links split into common, missing and never-mentioned, sorted."""
    report = sort_data({"b.htm", "a.htm", "orphan.htm"}, {"a.htm", "b.htm", "missing.htm"}, "x")

    assert report.common == ["a.htm", "b.htm"]
    assert report.missing == ["missing.htm"]
    assert report.never_mentioned == ["orphan.htm"]


def test_sort_data_is_case_sensitive_by_default() -> None:
    """On a case-sensitive filesystem, `Page.HTM` is not the local `page.htm`."""
    report = sort_data({"/o/page.htm"}, {"/o/Page.HTM"}, "html")

    assert report.common == []
    assert report.missing == ["/o/Page.HTM"]
    assert report.never_mentioned == ["/o/page.htm"]


def test_sort_data_fold_case_matches_names_differing_by_case() -> None:
    """With fold_case, a link matches a local file whatever the case; local names are kept."""
    report = sort_data(
        {"/o/page.htm", "/o/orphan.htm"}, {"/o/Page.HTM", "/o/Gone.htm"}, "html", fold_case=True
    )

    assert report.common == ["/o/page.htm"]
    assert report.missing == ["/o/Gone.htm"]
    assert report.never_mentioned == ["/o/orphan.htm"]


def test_export_missing_translates_local_paths_to_urls(
    tmp_path: pathlib.Path, make_config: "MakeConfig"
) -> None:
    """Missing local paths are exported as the URLs to download."""
    config = make_config(web_folder="example.com", web_output="example.com_output")
    missing_path = (config.folder_output / "sub" / "page.htm").as_posix()

    export_file = tmp_path / "missing.txt"
    _ = export_missing(export_file, [missing_path], config)

    assert export_file.read_text(encoding="utf-8") == "https://example.com/sub/page.htm\n"


def test_to_wayback_url_of_the_output_folder_is_the_site_root(make_config: "MakeConfig") -> None:
    """A link to the site folder itself (`href="/"`) used to become `https://host/.`."""
    config = make_config(web_folder="example.com")

    assert to_wayback_url(config.folder_output.as_posix(), config) == "https://example.com/"


def test_scan_reports_not_scanned_when_output_folder_empty(make_config: "MakeConfig") -> None:
    """An empty output folder is reported as not scanned."""
    config = make_config()
    config.folder_output.mkdir(parents=True)

    result = scan(config)

    assert result.scanned is False
    assert result.missing_count == 0


def test_scan_reports_not_scanned_when_output_folder_missing(make_config: "MakeConfig") -> None:
    """A missing output folder is reported as not scanned, not raised."""
    config = make_config()

    assert scan(config).scanned is False


def test_scan_counts_missing_resources_and_writes_files(make_config: "MakeConfig") -> None:
    """Regression test: cli_launcher used to re-read missing_*.txt to get this same count."""
    config = make_config(web_folder="example.com")
    write_site(config, {"index.htm": '<a href="missing.htm">x</a><img src="missing.png">'})

    result = scan(config)

    assert result.scanned is True
    assert result.missing_count == 2
    assert read_exports(config) == (
        "https://example.com/missing.htm\n",
        "https://example.com/missing.png\n",
        "",
    )


def test_scan_exports_exact_file_contents(make_config: "MakeConfig") -> None:
    """Each export lists its links sorted, one URL per line; found files are left out."""
    config = make_config(web_folder="example.com")
    write_site(
        config,
        {
            "index.htm": (
                '<a href="sub/b.htm">b</a><a href="a.htm">a</a><a href="here.htm">h</a>'
                + '<img src="img/x.gif"><img src="ok.png"><a href="my%20doc.pdf">d</a>'
                + '<a href="http://ext.example.org/x">e</a><a href="data.xyz">u</a>'
                + '<a href="/">root</a><a href="../../out.htm">o</a>'
            ),
            "here.htm": "",
            "ok.png": "",
        },
    )

    result = scan(config)

    assert result.missing_count == 4
    assert read_exports(config) == (
        "https://example.com/a.htm\nhttps://example.com/sub/b.htm\n",
        "https://example.com/img/x.gif\nhttps://example.com/my%20doc.pdf\n",
        # Sorted as stored: raw, then resolved local paths (absolute), then external links.
        "../../out.htm\nhttps://example.com/\nhttps://example.com/data.xyz\n"
        + "http://ext.example.org/x\n",
    )


def test_scan_finds_backslash_links_locally(make_config: "MakeConfig") -> None:
    r"""`images\logo.gif` finds the local `images/logo.gif`: nothing is reported missing."""
    config = make_config()
    write_site(config, {"index.htm": r'<img src="images\logo.gif">', "images/logo.gif": ""})

    result = scan(config)

    assert result.missing_count == 0
    assert read_exports(config) == ("", "", "")


def test_scan_on_case_insensitive_output_matches_links_whatever_the_case(
    make_config: "MakeConfig", case_insensitive: list[bool]
) -> None:
    """`Page.HTM` next to a local `page.htm` is not missing when the filesystem ignores case."""
    case_insensitive[0] = True
    config = make_config()
    write_site(config, {"index.htm": '<a href="Page.HTM">p</a><img src="LOGO.gif">'})
    write_site(config, {"page.htm": "", "logo.GIF": ""})

    assert scan(config).missing_count == 0


def test_scan_on_case_sensitive_output_reports_case_mismatches(
    make_config: "MakeConfig", case_insensitive: list[bool]
) -> None:
    """On a case-sensitive filesystem (Linux), `Page.HTM` is still not `page.htm`."""
    case_insensitive[0] = False
    config = make_config(web_folder="example.com")
    write_site(config, {"index.htm": '<a href="Page.HTM">p</a>', "page.htm": ""})

    assert scan(config).missing_count == 1
    assert read_exports(config)[0] == "https://example.com/Page.HTM\n"


def test_scan_probes_the_filesystem_case_once(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """Case sensitivity is detected once per scan, from the files already listed, not per link."""
    probed: list[list[str]] = []

    def probe(entries: "Iterable[pathlib.Path]") -> bool:
        """Record the names of the probed entries and say case matters.

        Args:
            entries: The entries offered to the probe, recorded.

        Returns:
            ``False``.
        """
        probed.append(sorted(entry.name for entry in entries))
        return False

    monkeypatch.setattr(finder, "is_case_insensitive", probe)
    config = make_config()
    write_site(config, {f"p{i}.htm": '<a href="a.htm"><img src="b.png">' for i in range(3)})

    _ = scan(config)

    assert probed == [["p0.htm", "p1.htm", "p2.htm"]]


def test_scan_matches_case_on_a_real_case_insensitive_filesystem(
    tmp_path: pathlib.Path, make_config: "MakeConfig"
) -> None:
    """End to end, with the real detection (macOS and Windows default filesystems)."""
    config = make_config()
    write_site(config, {"index.htm": '<a href="Page.HTM">p</a>', "page.htm": ""})
    if not is_case_insensitive(tmp_path.iterdir()):
        pytest.skip("needs a case-insensitive filesystem")

    assert scan(config).missing_count == 0


def test_scan_ignores_the_merge_manifest(
    make_config: "MakeConfig", caplog: pytest.LogCaptureFixture
) -> None:
    """The merger's manifest is not a site resource: never reported as 'never called'."""
    config = make_config()
    write_site(config, {"index.htm": "", MANIFEST_FILE: "{}"})

    with caplog.at_level(logging.INFO, logger=finder.__name__):
        _ = scan(config)

    assert "Found 0 existing but never 'called' other resource(s)" in caplog.messages


def test_scan_of_only_the_merge_manifest_has_nothing_to_scan(make_config: "MakeConfig") -> None:
    """An output folder holding nothing but the manifest has nothing to scan."""
    config = make_config()
    write_site(config, {MANIFEST_FILE: "{}"})

    assert scan(config).scanned is False


def test_run_returns_zero_when_scanned(make_config: "MakeConfig") -> None:
    """A completed scan returns 0."""
    config = make_config()
    write_site(config, {"index.htm": '<a href="other.htm">x</a>'})

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

    _ = export_missing(export_file, links, config)

    assert export_file.read_text(encoding="utf-8").splitlines() == [
        "https://site/layout/out.css",
        "https://site/my%20page.htm",
        "https://cdn.example.com/x.js",
    ]


def test_export_translates_windows_drive_paths(tmp_path: pathlib.Path) -> None:
    """A `C:/...` local path is a URL to build, not a link with a `c:` scheme to keep as is."""
    config = AppConfig(web_folder="example.com", web_output="out", base_dir=pathlib.Path("C:/w"))
    export_file = tmp_path / "missing.txt"

    _ = export_missing(export_file, [(config.folder_output / "a.htm").as_posix()], config)

    assert export_file.read_text(encoding="utf-8") == "https://example.com/a.htm\n"


def test_unspecified_export_keeps_links_leaving_the_site(make_config: "MakeConfig") -> None:
    """unspecified.txt lists links that escape the site as written; missing lists don't."""
    config = make_config()
    kept, dropped = config.base_dir / "unspecified.txt", config.base_dir / "missing.txt"

    _ = export_missing(kept, ["../../x.htm"], config, keep_unresolved=True)
    _ = export_missing(dropped, ["../../x.htm"], config)

    assert kept.read_text(encoding="utf-8") == "../../x.htm\n"
    assert dropped.read_text(encoding="utf-8") == ""


def test_sort_data_fold_case_keeps_names_only_casefold_would_merge() -> None:
    """Regression: `strasse.html` matched the local `straße.html` (`str.casefold`)."""
    report = sort_data({"/o/straße.html"}, {"/o/strasse.html"}, "html", fold_case=True)

    assert report.common == []
    assert report.missing == ["/o/strasse.html"]


def test_sort_data_fold_case_lists_spellings_of_one_missing_file_once() -> None:
    """Regression: `A.htm` and `a.htm`, both missing, were exported (and downloaded) twice."""
    report = sort_data(set(), {"/o/a.htm", "/o/A.htm"}, "html", fold_case=True)

    assert report.missing == ["/o/A.htm"]


@pytest.mark.parametrize("name", [".wmdc-k3j2x9.tmp", "notes.docx"])
def test_scan_of_only_non_site_files_has_nothing_to_scan(
    make_config: "MakeConfig", name: str
) -> None:
    """Regression: a leftover merge temporary, or any non-site file, counted as "scanned"."""
    config = make_config()
    write_site(config, {name: "x"})

    assert scan(config).scanned is False


def test_scan_returns_the_exported_urls(make_config: "MakeConfig") -> None:
    """The result carries what missing_html.txt and missing_other.txt list, unspecified aside."""
    config = make_config(web_folder="example.com")
    write_site(config, {"index.htm": '<a href="a.htm">a</a><img src="b.png"><a href="x.xyz">'})

    result = scan(config)

    assert result.missing_urls == {"https://example.com/a.htm", "https://example.com/b.png"}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX folder permissions")
def test_scan_of_a_read_only_output_works(make_config: "MakeConfig") -> None:
    """Regression: the case probe wrote a file in the output, so a read-only one crashed."""
    if os.geteuid() == 0:
        pytest.skip("root writes into read-only folders")
    config = make_config(web_folder="example.com")
    write_site(config, {"index.htm": '<a href="Gone.htm">g</a>'})
    config.folder_output.chmod(0o555)
    try:
        result = scan(config)
    finally:
        config.folder_output.chmod(0o755)

    assert result.scanned is True
    assert result.missing_urls == {"https://example.com/Gone.htm"}
