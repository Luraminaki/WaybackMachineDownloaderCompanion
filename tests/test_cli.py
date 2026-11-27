"""Tests for the shared CLI plumbing (``_cli.main``) and each console script's ``cli()``."""

import logging
import sys
from typing import TYPE_CHECKING

import pytest

from wayback_machine_downloader_companion import (
    _cli,
    cli_download,
    cli_find,
    cli_launcher,
    cli_merge,
    downloader,
    finder,
    merger,
)

if TYPE_CHECKING:
    import argparse
    import pathlib
    from types import ModuleType

    from wayback_machine_downloader_companion.config import AppConfig

pytestmark = pytest.mark.usefixtures("restore_root_logger")

PROG = "wmdc-test"


@pytest.fixture(name="workdir")
def fixture_workdir(tmp_path: "pathlib.Path", monkeypatch: pytest.MonkeyPatch) -> "pathlib.Path":
    """Run the test from ``tmp_path``, where ``logs/`` and the default config.json live.

    Args:
        tmp_path: Pytest's per-test temporary directory.
        monkeypatch: Changes the working directory.

    Returns:
        The working directory.
    """
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write_config(folder: "pathlib.Path", text: str = '{"WEB_FOLDER": "example.com"}') -> None:
    """Writes ``config.json`` into a folder.

    Args:
        folder: Where.
        text: Its content.
    """
    _ = (folder / "config.json").write_text(text, encoding="utf-8")


def log_text(folder: "pathlib.Path") -> str:
    """Reads every log file the run wrote.

    Args:
        folder: The working directory the run used.

    Returns:
        The logs' text, concatenated.
    """
    return "".join(path.read_text(encoding="utf-8") for path in (folder / "logs").glob("*.log"))


def succeed(_config: "AppConfig", _args: "argparse.Namespace") -> int:
    """A command that does nothing and succeeds.

    Args:
        _config: Ignored.
        _args: Ignored.

    Returns:
        ``0``.
    """
    return 0


def test_missing_config_exits_one_and_says_so(workdir: "pathlib.Path") -> None:
    """No config.json: a logged "not found", exit code 1."""
    assert _cli.main(PROG, "test", succeed, argv=[]) == 1
    assert "not found" in log_text(workdir)


def test_malformed_config_exits_one(workdir: "pathlib.Path") -> None:
    """An invalid config.json is reported, exit code 1, the command never runs."""
    write_config(workdir, "{not json")
    calls: list[object] = []

    assert _cli.main(PROG, "test", lambda *_a: calls.append(1) or 0, argv=[]) == 1
    assert calls == []
    assert "Invalid JSON" in log_text(workdir)


def test_the_commands_exit_code_is_passed_through(workdir: "pathlib.Path") -> None:
    """Whatever the command returns is the process exit code."""
    write_config(workdir)

    assert _cli.main(PROG, "test", lambda *_a: 3, argv=[]) == 3


def test_a_command_that_raises_exits_one_with_the_error_logged(workdir: "pathlib.Path") -> None:
    """An unexpected exception becomes exit code 1 and a logged traceback."""
    write_config(workdir)

    def explode(_config: "AppConfig", _args: "argparse.Namespace") -> int:
        """Fail like a command with a bug.

        Args:
            _config: Ignored.
            _args: Ignored.

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("boom")

    assert _cli.main(PROG, "test", explode, argv=[]) == 1
    assert f"Unhandled error in {PROG}" in log_text(workdir)
    assert "RuntimeError: boom" in log_text(workdir)


@pytest.mark.usefixtures("workdir")
def test_bad_arguments_exit_two() -> None:
    """An unknown option is argparse's usage error, exit code 2."""
    with pytest.raises(SystemExit) as raised:
        _ = _cli.main(PROG, "test", succeed, argv=["--no-such-option"])

    assert raised.value.code == 2


def test_verbose_flag_logs_debug(workdir: "pathlib.Path") -> None:
    """``-v`` switches logging to debug."""
    write_config(workdir)

    assert _cli.main(PROG, "test", succeed, argv=["-v"]) == 0
    assert logging.getLogger().level == logging.DEBUG


def test_an_unusable_log_folder_exits_one_without_a_traceback(
    workdir: "pathlib.Path", capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression test: a file named ``logs`` (or a read-only CWD) crashed ``main``."""
    _ = (workdir / "logs").write_text("a file where the folder should be", encoding="utf-8")
    write_config(workdir)

    assert _cli.main(PROG, "test", succeed, argv=[]) == 1

    err = capsys.readouterr().err
    assert "logs: not a folder" in err
    assert "Traceback" not in err


@pytest.mark.parametrize(
    ("console", "module", "prog"),
    [
        (cli_merge, merger, "wmdc-merge"),
        (cli_find, finder, "wmdc-find"),
        (cli_download, downloader, "wmdc-download"),
        (cli_launcher, cli_launcher, "wmdc"),
    ],
)
def test_console_script_exits_with_mains_code(
    workdir: "pathlib.Path",
    monkeypatch: pytest.MonkeyPatch,
    console: "ModuleType",
    module: "ModuleType",
    prog: str,
) -> None:
    """Each console script runs its own step, logs under its name, and exits with its code."""
    write_config(workdir)
    monkeypatch.setattr(sys, "argv", [prog])
    monkeypatch.setattr(module, "run", lambda *_a: 3)

    with pytest.raises(SystemExit) as raised:
        console.cli()

    assert raised.value.code == 3
    assert [path.name.rsplit("-", 1)[0] for path in (workdir / "logs").iterdir()] == [prog]
