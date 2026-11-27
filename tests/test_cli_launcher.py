"""Tests for wayback_machine_downloader_companion.cli_launcher: options, menu and dispatch.

The full run's loop is tested in ``test_cli_launcher_full.py``.
"""

import argparse
import logging
import pathlib
from typing import TYPE_CHECKING

import pytest

from wayback_machine_downloader_companion import (
    _cli,
    cli_launcher,
    downloader,
    finder,
    merger,
)

if TYPE_CHECKING:
    from tests.conftest import MakeConfig


def test_configure_parser_defaults() -> None:
    """Without arguments, the launcher's parser picks the documented defaults."""
    parser = _cli.build_parser("wmdc", "test", configure_parser=cli_launcher.configure_parser)
    args = parser.parse_args([])

    assert args.mode is None
    assert args.force_merge is False
    assert args.max_iterations == cli_launcher._DEFAULT_MAX_ITERATIONS  # pyright: ignore[reportPrivateUsage]  # pylint: disable=protected-access


def test_needs_merge_false_when_snapshot_folder_missing(make_config: "MakeConfig") -> None:
    """No snapshot folder: nothing to merge."""
    config = make_config()
    assert cli_launcher.needs_merge(config) is False


def test_needs_merge_true_with_a_versioned_subfolder(make_config: "MakeConfig") -> None:
    """A versioned snapshot subfolder means a merge is needed."""
    config = make_config()
    (config.folder_snapshots / "20230601000000").mkdir(parents=True)

    assert cli_launcher.needs_merge(config) is True


def test_needs_merge_false_with_only_non_snapshot_subfolders(make_config: "MakeConfig") -> None:
    """Subfolders that aren't snapshots don't trigger a merge."""
    config = make_config()
    (config.folder_snapshots / "backup").mkdir(parents=True)

    assert cli_launcher.needs_merge(config) is False


def test_needs_merge_false_when_snapshot_folder_vanishes_during_check(
    make_config: "MakeConfig",
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: needs_merge() used to let a TOCTOU iterdir() failure propagate."""
    config = make_config()
    config.folder_snapshots.mkdir(parents=True)

    def raise_oserror(_self: pathlib.Path) -> None:
        """Fail like a folder deleted between the check and the listing.

        Args:
            _self: Ignored.

        Raises:
            OSError: Always.
        """
        raise OSError("vanished")

    monkeypatch.setattr(pathlib.Path, "iterdir", raise_oserror)

    assert cli_launcher.needs_merge(config) is False


def test_warn_if_unspecified_remain_logs_when_file_has_entries(
    make_config: "MakeConfig",
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Leftover unspecified links are logged as a warning."""
    config = make_config()
    _ = (config.base_dir / "unspecified.txt").write_text(
        "https://example.com/a.js\n", encoding="utf-8"
    )

    with caplog.at_level(logging.WARNING):
        cli_launcher._warn_if_unspecified_remain(config)  # pyright: ignore[reportPrivateUsage]  # pylint: disable=protected-access

    assert "unclassified link" in caplog.text


def test_warn_if_unspecified_remain_silent_when_file_missing(
    make_config: "MakeConfig",
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No unspecified-links file: nothing is logged."""
    with caplog.at_level(logging.WARNING):
        cli_launcher._warn_if_unspecified_remain(make_config())  # pyright: ignore[reportPrivateUsage]  # pylint: disable=protected-access

    assert caplog.text == ""


def test_run_interactive_returns_one_on_eof(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """End of input in the menu exits with code 1."""

    def raise_eof(_prompt: str = "") -> str:
        """Answer like a closed standard input.

        Args:
            _prompt: Ignored.

        Raises:
            EOFError: Always.
        """
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)

    result = cli_launcher.run_interactive(make_config(), argparse.Namespace())

    assert result == 1


def test_run_interactive_dispatches_selected_step(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """The menu runs the step the user picked."""
    monkeypatch.setattr("builtins.input", lambda _prompt="": "3")
    calls: list[object] = []
    monkeypatch.setattr(finder, "run", lambda *_a, **_k: calls.append(1) or 0)

    result = cli_launcher.run_interactive(make_config(), argparse.Namespace())

    assert result == 0
    assert calls == [1]


def test_run_interactive_quits_on_invalid_choice(
    make_config: "MakeConfig",
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An invalid menu choice exits with an error, running nothing (a typo isn't a success)."""
    monkeypatch.setattr("builtins.input", lambda _prompt="": "9")

    result = cli_launcher.run_interactive(make_config(), argparse.Namespace())

    assert result == 1
    assert "Invalid choice '9'" in capsys.readouterr().out


def test_run_interactive_quit_choice_exits_cleanly(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """Choosing "Quit" ends with code 0."""
    monkeypatch.setattr("builtins.input", lambda _prompt="": "5")

    assert cli_launcher.run_interactive(make_config(), argparse.Namespace()) == 0


@pytest.mark.parametrize(
    ("mode", "module"), [("merge", merger), ("find", finder), ("download", downloader)]
)
def test_run_dispatches_by_mode(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch, mode: str, module: object
) -> None:
    """Each single-step mode runs its own step."""
    calls: list[object] = []
    monkeypatch.setattr(module, "run", lambda *_a, **_k: calls.append(1) or 0)

    result = cli_launcher.run(make_config(), argparse.Namespace(mode=mode))

    assert result == 0
    assert calls == [1]


def test_run_dispatches_full_mode(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `full` mode runs the full loop."""
    calls: list[object] = []
    monkeypatch.setattr(cli_launcher, "run_full", lambda *_a, **_k: calls.append(1) or 0)

    result = cli_launcher.run(make_config(), argparse.Namespace(mode="full"))

    assert result == 0
    assert calls == [1]


def test_run_falls_back_to_interactive_menu_when_mode_is_none(
    make_config: "MakeConfig",
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a mode, the interactive menu is shown."""
    calls: list[object] = []
    monkeypatch.setattr(cli_launcher, "run_interactive", lambda *_a, **_k: calls.append(1) or 0)

    result = cli_launcher.run(make_config(), argparse.Namespace(mode=None))

    assert result == 0
    assert calls == [1]


@pytest.mark.parametrize("value", ["0", "-1", "two"])
def test_max_iterations_must_be_positive(value: str) -> None:
    """`--max-iterations 0` used to skip the loop and then report it reached the limit."""
    parser = argparse.ArgumentParser()
    cli_launcher.configure_parser(parser)

    with pytest.raises(SystemExit):
        _ = parser.parse_args(["--max-iterations", value])


def test_max_iterations_option_is_parsed() -> None:
    """``--max-iterations 3`` is the integer 3."""
    parser = _cli.build_parser("wmdc", "test", configure_parser=cli_launcher.configure_parser)

    assert parser.parse_args(["--max-iterations", "3"]).max_iterations == 3


@pytest.mark.parametrize(
    ("choice", "module", "name"),
    [
        ("1", cli_launcher, "run_full"),
        ("2", merger, "run"),
        (" 3 ", finder, "run"),
        ("4", downloader, "run"),
    ],
)
def test_menu_choice_runs_its_step(
    make_config: "MakeConfig",
    monkeypatch: pytest.MonkeyPatch,
    choice: str,
    module: object,
    name: str,
) -> None:
    """Each menu number runs its own step (surrounding spaces ignored), with its exit code."""
    monkeypatch.setattr("builtins.input", lambda _prompt="": choice)
    calls: list[int] = []
    monkeypatch.setattr(module, name, lambda *_a, **_k: calls.append(1) or 4)

    assert cli_launcher.run_interactive(make_config(), argparse.Namespace()) == 4
    assert calls == [1]


def test_warn_if_unspecified_remain_silent_when_file_is_blank(
    make_config: "MakeConfig", caplog: pytest.LogCaptureFixture
) -> None:
    """An unspecified-links file with only blank lines is nothing to report."""
    config = make_config()
    _ = (config.base_dir / "unspecified.txt").write_text("\n  \n\t\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        cli_launcher._warn_if_unspecified_remain(config)  # pyright: ignore[reportPrivateUsage]  # pylint: disable=protected-access

    assert caplog.text == ""


def test_needs_merge_false_when_web_folder_is_a_file(make_config: "MakeConfig") -> None:
    """A file where the snapshot folder should be has nothing to merge."""
    config = make_config()
    _ = config.folder_snapshots.write_text("not a folder", encoding="utf-8")

    assert cli_launcher.needs_merge(config) is False
