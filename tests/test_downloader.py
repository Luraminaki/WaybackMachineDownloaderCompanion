"""Tests for wayback_machine_downloader_companion.downloader."""

import argparse
import logging
import shutil
import subprocess
import time
from typing import TYPE_CHECKING

import pytest

from wayback_machine_downloader_companion import downloader
from wayback_machine_downloader_companion.downloader import (
    ToolStartError,
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
        """Time out like a download that never finishes.

        Args:
            *_args: Ignored.
            **_kwargs: Ignored.

        Raises:
            subprocess.TimeoutExpired: Always.
        """
        raise subprocess.TimeoutExpired("wayback_machine_downloader", 0.1)

    monkeypatch.setattr(subprocess, "run", hang)

    assert start_process(["wayback_machine_downloader", "url"], cwd=tmp_path, timeout=0.1) == 1


def test_download_command_saves_into_the_output_folder(tmp_path: "pathlib.Path") -> None:
    """Each URL is one argument (quotes and spaces are safe) and lands in the scanned folder."""
    url = "https://example.com/it's a page.html"

    assert download_command("/bin/wmd", url, tmp_path) == [
        "/bin/wmd",
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


def test_start_process_runs_in_base_dir_with_the_timeout(
    tmp_path: "pathlib.Path", monkeypatch: pytest.MonkeyPatch
) -> None:
    """The process starts in the given folder and is bounded by the given timeout."""
    seen: dict[str, object] = {}

    def fake_run(_command: list[str], **kwargs: object) -> "subprocess.CompletedProcess[bytes]":
        """Record the options the download runs with, and succeed.

        Args:
            _command: Ignored.
            **kwargs: The options, recorded.

        Returns:
            A finished download.
        """
        seen.update(kwargs)
        return finished_with("Download finished in 1s.\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert start_process(["wmd", "url"], cwd=tmp_path, timeout=12.5) == 0
    assert seen["cwd"] == tmp_path
    assert seen["timeout"] == 12.5


def test_start_process_reports_a_process_that_cannot_start(
    tmp_path: "pathlib.Path", monkeypatch: pytest.MonkeyPatch
) -> None:
    """An OSError from ``subprocess.run`` (bad .bat, no rights) becomes one named error."""

    def cannot_start(*_args: object, **_kwargs: object) -> None:
        """Fail like an executable the user may not run.

        Args:
            *_args: Ignored.
            **_kwargs: Ignored.

        Raises:
            PermissionError: Always.
        """
        raise PermissionError("not executable")

    monkeypatch.setattr(subprocess, "run", cannot_start)

    with pytest.raises(ToolStartError, match="Can't start wmd: not executable"):
        _ = start_process(["wmd", "https://a/1"], cwd=tmp_path)


def test_run_stops_at_the_first_process_that_cannot_start(
    make_config: "MakeConfig",
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    no_sleep: list[float],
) -> None:
    """Regression: each URL went on to fail the same way, with a pause after each one.

    3,000 URLs meant 3,000 certain failures and about 50 minutes of pauses; the run now stops
    with one error naming the executable, and neither tries nor waits for the other URLs.
    """
    config = make_config()
    _ = (config.base_dir / "missing_html.txt").write_text("https://a/1\nhttps://a/2\n", "utf-8")
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/wmd")
    started: list[str] = []

    def fake_run(command: list[str], **_kwargs: object) -> "subprocess.CompletedProcess[bytes]":
        """Fail to start the first download, then (if ever asked again) succeed.

        Args:
            command: The command line; its URL is recorded.
            **_kwargs: Ignored.

        Returns:
            A finished download.

        Raises:
            OSError: On the first call.
        """
        started.append(command[-1])
        if len(started) == 1:
            raise OSError("exec format error")
        return finished_with("Download finished in 1s.\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert run(config, argparse.Namespace()) == 1
    assert started == ["https://a/1"]
    assert no_sleep == []
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert [record.getMessage() for record in errors] == [
        "Can't start /usr/bin/wmd: exec format error -- stopping: the remaining URLs are not "
        + "tried (see INSTALL.md)"
    ]
    assert errors[0].exc_info is None


@pytest.mark.usefixtures("no_sleep")
def test_run_starts_the_executable_which_found(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test: RubyGems installs a ``.bat`` on Windows, which the bare name misses."""
    config = make_config()
    _ = (config.base_dir / "missing_html.txt").write_text("https://a/1\n", "utf-8")
    found = r"C:\Ruby33\bin\wayback_machine_downloader.bat"
    monkeypatch.setattr(shutil, "which", lambda _name: found)
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> "subprocess.CompletedProcess[bytes]":
        """Record the command line, and succeed.

        Args:
            command: The command line, recorded.
            **_kwargs: Ignored.

        Returns:
            A finished download.
        """
        commands.append(command)
        return finished_with("Download finished in 1s.\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert run(config, argparse.Namespace()) == 0
    assert [command[0] for command in commands] == [found]


@pytest.mark.usefixtures("no_sleep")
def test_run_saves_into_the_output_folder_from_base_dir(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each command targets the scanned output folder and runs from the config folder."""
    config = make_config()
    _ = (config.base_dir / "missing_html.txt").write_text("https://a/1\n", "utf-8")
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/wmd")
    calls: list[tuple[list[str], object]] = []
    monkeypatch.setattr(
        downloader, "start_process", lambda command, cwd: calls.append((command, cwd)) or 0
    )

    assert run(config, argparse.Namespace()) == 0
    assert calls == [
        (download_command("/usr/bin/wmd", "https://a/1", config.folder_output), config.base_dir)
    ]


def test_missing_urls_are_stripped_and_html_comes_first(make_config: "MakeConfig") -> None:
    """CRLF line ends and stray spaces don't end up in the URL; pages are fetched first."""
    config = make_config()
    _ = (config.base_dir / "missing_other.txt").write_bytes(b"https://a/x.png\r\n")
    _ = (config.base_dir / "missing_html.txt").write_bytes(b"  https://a/1  \r\n\t\r\n")

    assert read_missing_urls(config) == ["https://a/1", "https://a/x.png"]


def test_run_with_empty_missing_files_does_not_look_for_the_tool(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty lists: success, and no "not installed" error on a machine without the tool."""
    config = make_config()
    for name in downloader.MISSING_FILES:
        _ = (config.base_dir / name).write_text("\n", encoding="utf-8")
    lookups: list[str] = []
    monkeypatch.setattr(shutil, "which", lookups.append)

    assert run(config, argparse.Namespace()) == 0
    assert lookups == []


def test_a_list_that_is_not_utf8_is_one_clear_error(
    make_config: "MakeConfig", caplog: pytest.LogCaptureFixture
) -> None:
    """The finder writes UTF-8: anything else was edited by hand, and is reported, not raised."""
    config = make_config()
    missing = config.base_dir / "missing_html.txt"
    _ = missing.write_bytes(b"https://a/caf\xe9.html\n")  # Latin-1

    assert run(config, argparse.Namespace()) == 1
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert str(missing) in errors[0].getMessage()
    assert errors[0].exc_info is None
