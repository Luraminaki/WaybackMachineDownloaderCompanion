"""Tests for wayback_machine_downloader_companion.downloader."""

import argparse
import shutil
import subprocess
import time
from typing import TYPE_CHECKING

import pytest

from wayback_machine_downloader_companion import downloader
from wayback_machine_downloader_companion.downloader import (
    download_command,
    read_missing_urls,
    run,
    start_process,
)

if TYPE_CHECKING:
    import pathlib

    from tests.conftest import MakeConfig


def finished_with(output: str, returncode: int = 0) -> "subprocess.CompletedProcess[bytes]":
    """Fake a finished wayback_machine_downloader process.

    Args:
        output: What it printed.
        returncode: Its exit code.

    Returns:
        The completed process.
    """
    return subprocess.CompletedProcess([], returncode, stdout=output.encode())


@pytest.mark.parametrize(
    ("output", "returncode", "expected"),
    [
        ("Downloading...\nDownload finished in 1.2s.\n", 0, 0),
        # Regression: the old "Download completed" marker matched only this failure message.
        ("Download completed with errors.\nDownload finished in 1.2s.\n", 0, 1),
        ("Download finished in 1.2s.\n", 1, 1),
        ("Downloading...\n", 0, 1),
        ("\xff garbled\nDownload finished in 0.1s.\n", 0, 0),
    ],
)
def test_start_process_reads_the_forks_verdict(
    tmp_path: "pathlib.Path",
    monkeypatch: pytest.MonkeyPatch,
    output: str,
    returncode: int,
    expected: int,
) -> None:
    """Success needs a clean exit, the fork's "finished" line, and no error summary."""
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: finished_with(output, returncode))

    assert start_process(["wayback_machine_downloader"], cwd=tmp_path) == expected


def test_start_process_gives_up_after_the_timeout(
    tmp_path: "pathlib.Path", monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hung download counts as failed instead of blocking the run forever."""

    def hang(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired("wayback_machine_downloader", 0.1)

    monkeypatch.setattr(subprocess, "run", hang)

    assert start_process(["wayback_machine_downloader", "url"], cwd=tmp_path, timeout=0.1) == 1


def test_download_command_saves_into_the_output_folder(tmp_path: "pathlib.Path") -> None:
    """Each URL is one argument (quotes and spaces are safe) and lands in the scanned folder."""
    url = "https://example.com/it's a page.html"

    assert download_command(url, tmp_path) == [
        "wayback_machine_downloader",
        "-e",
        "-d",
        str(tmp_path),
        url,
    ]


def test_missing_urls_are_read_once_each(make_config: "MakeConfig") -> None:
    """Blank lines are skipped and a URL listed twice is downloaded once."""
    config = make_config()
    _ = (config.base_dir / "missing_html.txt").write_text("https://a/1\n\nhttps://a/2\n", "utf-8")
    _ = (config.base_dir / "missing_other.txt").write_text("https://a/1\nhttps://a/3\n", "utf-8")

    assert read_missing_urls(config) == ["https://a/1", "https://a/2", "https://a/3"]


def test_run_counts_failures_and_pauses_only_between_downloads(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """One failed URL fails the run; the pause separates downloads, none after the last."""
    config = make_config()
    _ = (config.base_dir / "missing_html.txt").write_text("https://a/1\nhttps://a/2\n", "utf-8")
    verdicts = [0, 1]
    pauses: list[float] = []
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/wmd")
    monkeypatch.setattr(downloader, "start_process", lambda *_a, **_k: verdicts.pop(0))
    monkeypatch.setattr(time, "sleep", pauses.append)

    assert run(config, argparse.Namespace()) == 1
    assert pauses == [downloader.DOWNLOAD_THROTTLE_SECONDS]


def test_run_without_the_tool_installed_fails_once(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing wayback_machine_downloader is reported once, not as one error per URL."""
    config = make_config()
    _ = (config.base_dir / "missing_html.txt").write_text("https://a/1\n", "utf-8")
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    assert run(config, argparse.Namespace()) == 1


def test_run_with_nothing_missing_succeeds(make_config: "MakeConfig") -> None:
    """No missing-resource file: nothing to download, success."""
    assert run(make_config(), argparse.Namespace()) == 0
