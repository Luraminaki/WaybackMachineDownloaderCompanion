"""Tests for the full run of wayback_machine_downloader_companion.cli_launcher.

The merge, then the find/download loop until nothing is missing, with its stop rules.
"""

import argparse
import pathlib
import shutil
import subprocess
from typing import TYPE_CHECKING, NoReturn

import pytest

from wayback_machine_downloader_companion import cli_launcher, downloader, finder, merger
from wayback_machine_downloader_companion.finder import FinderResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.conftest import MakeConfig
    from wayback_machine_downloader_companion.config import AppConfig


def script_scans(monkeypatch: pytest.MonkeyPatch, scans: list[list[str]]) -> None:
    """Replaces ``finder.scan`` with scans that find the given URLs, one list per call.

    Args:
        monkeypatch: Replaces ``finder.scan``.
        scans: The URLs each successive scan finds missing (and exports).
    """

    def fake_scan(_config: "AppConfig") -> FinderResult:
        """Find the next scripted URLs missing.

        Args:
            _config: Ignored.

        Returns:
            A scan that found and exported them.
        """
        urls = scans.pop(0)
        return FinderResult(scanned=True, missing_count=len(urls), missing_urls=frozenset(urls))

    monkeypatch.setattr(finder, "scan", fake_scan)


def explode(*_args: object, **_kwargs: object) -> NoReturn:
    """Stand in for a step that fails unexpectedly.

    Args:
        *_args: Ignored.
        **_kwargs: Ignored.

    Raises:
        RuntimeError: Always.
    """
    raise RuntimeError("boom")


def full_args(max_iterations: int = 10, force_merge: bool = False) -> argparse.Namespace:
    """Builds the arguments ``run_full`` reads.

    Args:
        max_iterations: ``--max-iterations``.
        force_merge: ``--force-merge``.

    Returns:
        The parsed arguments.
    """
    return argparse.Namespace(force_merge=force_merge, max_iterations=max_iterations)


def test_run_full_aborts_without_scanning_when_merge_fails(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed merge stops the full run before any scan."""
    config = make_config()
    (config.folder_snapshots / "20230601000000").mkdir(parents=True)

    monkeypatch.setattr(merger, "run", lambda *_a, **_k: 1)
    scan_calls: list[object] = []
    monkeypatch.setattr(finder, "scan", lambda _config: scan_calls.append(1))

    result = cli_launcher.run_full(config, argparse.Namespace(force_merge=False, max_iterations=3))

    assert result == 1
    assert scan_calls == []


def test_run_full_returns_zero_when_nothing_missing_on_first_pass(
    make_config: "MakeConfig",
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing missing on the first pass: success, no download."""
    config = make_config()
    monkeypatch.setattr(finder, "scan", lambda _config: FinderResult(scanned=True, missing_count=0))
    download_calls: list[object] = []
    monkeypatch.setattr(downloader, "run", lambda *_a, **_k: download_calls.append(1) or 0)

    result = cli_launcher.run_full(config, argparse.Namespace(force_merge=False, max_iterations=3))

    assert result == 0
    assert download_calls == []


def test_run_full_loops_until_nothing_missing(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """The full run alternates scan and download until nothing is missing."""
    results = [
        FinderResult(scanned=True, missing_count=2),
        FinderResult(scanned=True, missing_count=0),
    ]
    monkeypatch.setattr(finder, "scan", lambda _config: results.pop(0))
    download_calls: list[object] = []
    monkeypatch.setattr(downloader, "run", lambda *_a, **_k: download_calls.append(1) or 0)

    result = cli_launcher.run_full(
        make_config(), argparse.Namespace(force_merge=False, max_iterations=5)
    )

    assert result == 0
    assert len(download_calls) == 1


def test_run_full_returns_one_when_nothing_to_scan(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty output folder is an error: there is nothing to scan."""
    monkeypatch.setattr(
        finder, "scan", lambda _config: FinderResult(scanned=False, missing_count=0)
    )

    result = cli_launcher.run_full(
        make_config(), argparse.Namespace(force_merge=False, max_iterations=3)
    )

    assert result == 1


def test_run_full_returns_one_when_max_iterations_exhausted(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Progress every iteration but not done at the limit: code 1, and the log says why.

    Regression test: run_full used to always return 0, even when it never converged.
    """
    config = make_config()
    script_scans(monkeypatch, [["https://a/1", "https://a/2"], ["https://a/2"]])
    downloads: list[int] = []
    monkeypatch.setattr(downloader, "run", lambda *_a, **_k: downloads.append(1) or 0)

    result = cli_launcher.run_full(config, full_args(max_iterations=2))

    assert result == 1
    assert len(downloads) == 2
    assert "Reached --max-iterations=2" in caplog.text


def test_run_full_returns_one_when_merge_raises(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An unexpected error names the step it happened in (the merge runs before any iteration).

    Regression test: it used to surface as a single generic 'Unhandled error'.
    """
    config = make_config()
    (config.folder_snapshots / "20230601000000").mkdir(parents=True)

    monkeypatch.setattr(merger, "run", explode)

    result = cli_launcher.run_full(config, argparse.Namespace(force_merge=False, max_iterations=3))

    assert result == 1
    assert "Merge step raised an unexpected error" in caplog.text
    assert "RuntimeError: boom" in caplog.text


def test_run_full_returns_one_when_finder_scan_raises(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A scan that raises ends the full run with code 1."""
    monkeypatch.setattr(finder, "scan", explode)

    result = cli_launcher.run_full(
        make_config(), argparse.Namespace(force_merge=False, max_iterations=3)
    )

    assert result == 1
    assert "Find step raised an unexpected error during iteration 1" in caplog.text


def test_run_full_returns_one_when_downloader_raises(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A download that raises ends the full run with code 1."""
    monkeypatch.setattr(finder, "scan", lambda _config: FinderResult(scanned=True, missing_count=1))

    monkeypatch.setattr(downloader, "run", explode)

    result = cli_launcher.run_full(
        make_config(), argparse.Namespace(force_merge=False, max_iterations=3)
    )

    assert result == 1
    assert "Download step raised an unexpected error during iteration 1" in caplog.text


def test_run_full_checks_for_unspecified_leftovers_when_done(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """A finished full run reports links it couldn't classify."""
    monkeypatch.setattr(finder, "scan", lambda _config: FinderResult(scanned=True, missing_count=0))
    calls: list[object] = []
    monkeypatch.setattr(
        cli_launcher, "_warn_if_unspecified_remain", lambda _config: calls.append(1)
    )

    result = cli_launcher.run_full(
        make_config(), argparse.Namespace(force_merge=False, max_iterations=3)
    )

    assert result == 0
    assert calls == [1]


def test_run_full_stops_when_an_iteration_makes_no_progress(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """URLs the archive doesn't have aren't re-requested until --max-iterations."""
    config = make_config()
    script_scans(
        monkeypatch,
        [
            ["https://a/1", "https://a/2", "https://a/3"],
            ["https://a/2", "https://a/3"],
            ["https://a/2", "https://a/3"],
        ],
    )
    downloads: list[int] = []
    monkeypatch.setattr(downloader, "run", lambda *_a, **_k: downloads.append(1) or 1)

    result = cli_launcher.run_full(config, full_args())

    assert result == 1
    assert len(downloads) == 2
    assert "No progress in iteration 3 (2 still missing)" in caplog.text


def test_run_full_goes_on_when_new_pages_reveal_more_missing(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """2 missing pages are fetched and reference 3 new images: progress, not a stall.

    Regression test: a higher missing count after downloading was taken for "no progress".
    """
    config = make_config()
    script_scans(
        monkeypatch,
        [
            ["https://a/1.htm", "https://a/2.htm"],
            ["https://a/x.png", "https://a/y.png", "https://a/z.png"],
            [],
        ],
    )
    downloads: list[int] = []
    monkeypatch.setattr(downloader, "run", lambda *_a, **_k: downloads.append(1) or 0)

    assert cli_launcher.run_full(config, full_args(max_iterations=5)) == 0
    assert len(downloads) == 2


def test_run_full_stops_when_nothing_previously_missing_was_resolved(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same URLs still missing, plus new ones: none of the downloads worked, stop."""
    config = make_config()
    script_scans(monkeypatch, [["https://a/1"], ["https://a/1", "https://a/2"]])
    downloads: list[int] = []
    monkeypatch.setattr(downloader, "run", lambda *_a, **_k: downloads.append(1) or 1)

    assert cli_launcher.run_full(config, full_args()) == 1
    assert len(downloads) == 1


def test_run_full_scans_after_a_successful_merge(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """Versioned snapshots are merged, then the loop starts."""
    config = make_config()
    (config.folder_snapshots / "20230601000000").mkdir(parents=True)
    steps: list[str] = []
    monkeypatch.setattr(merger, "run", lambda *_a, **_k: steps.append("merge") or 0)

    def scan(_config: "AppConfig") -> FinderResult:
        """Record the scan and find nothing missing.

        Args:
            _config: Ignored.

        Returns:
            A scan with nothing missing.
        """
        steps.append("scan")
        return FinderResult(scanned=True, missing_count=0)

    monkeypatch.setattr(finder, "scan", scan)

    assert cli_launcher.run_full(config, full_args()) == 0
    assert steps == ["merge", "scan"]


def test_force_merge_merges_even_without_snapshots(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--force-merge`` runs the merger although no versioned folder was detected."""
    config = make_config()
    merges: list[int] = []
    monkeypatch.setattr(merger, "run", lambda *_a, **_k: merges.append(1) or 0)
    monkeypatch.setattr(finder, "scan", lambda _config: FinderResult(scanned=True, missing_count=0))

    assert cli_launcher.run_full(config, full_args(force_merge=True)) == 0
    assert merges == [1]


def fake_wayback_machine_downloader(
    site: dict[str, str],
) -> "Callable[..., subprocess.CompletedProcess[bytes]]":
    """Builds a ``subprocess.run`` stand-in that "downloads" from an in-memory site.

    Args:
        site: Page path -> content, what the archive holds.

    Returns:
        The function: it writes the requested file under the ``-d`` folder and reports success,
        or reports errors for a path the site doesn't have.
    """

    def fake_run(command: list[str], **_kwargs: object) -> "subprocess.CompletedProcess[bytes]":
        """Download the requested URL from the in-memory site.

        Args:
            command: The ``wayback_machine_downloader`` command line.
            **_kwargs: Ignored.

        Returns:
            The tool's success output, or its error summary if the site lacks the path.
        """
        directory, url = pathlib.Path(command[3]), command[4]
        path = url.removeprefix("https://example.com/")
        if path not in site:
            return subprocess.CompletedProcess(
                command, 0, stdout=b"Download completed with errors.\n"
            )
        target = directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(site[path], encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout=b"Download finished in 0.1s.\n")

    return fake_run


@pytest.mark.usefixtures("no_sleep")
def test_full_run_downloads_until_the_site_is_complete(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real finder and downloader: pages fetched in one pass reveal what the next one fetches.

    Two missing, then two others the new page references, then none: progress each time.
    """
    config = make_config()
    config.folder_output.mkdir(parents=True)
    _ = (config.folder_output / "index.html").write_text(
        '<a href="about.html">About</a><img src="logo.png">', encoding="utf-8"
    )
    site = {
        "about.html": '<link rel="stylesheet" href="css/site.css"><script src="js/app.js">',
        "logo.png": "png",
        "css/site.css": "body {}",
        "js/app.js": "",
    }
    started: list[str] = []
    fake_run = fake_wayback_machine_downloader(site)

    def record_run(command: list[str], **kwargs: object) -> "subprocess.CompletedProcess[bytes]":
        """Record which URL a download asks for, then download it.

        Args:
            command: The ``wayback_machine_downloader`` command line.
            **kwargs: Passed on.

        Returns:
            What the fake download returns.
        """
        started.append(command[-1])
        return fake_run(command, **kwargs)

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/wayback_machine_downloader")
    monkeypatch.setattr(subprocess, "run", record_run)

    assert cli_launcher.run_full(config, full_args()) == 0
    assert started == [
        "https://example.com/about.html",
        "https://example.com/logo.png",
        "https://example.com/css/site.css",
        "https://example.com/js/app.js",
    ]
    assert (config.folder_output / "css" / "site.css").read_text(encoding="utf-8") == "body {}"
