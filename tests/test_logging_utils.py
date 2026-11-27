"""Tests for wayback_machine_downloader_companion.logging_utils."""

import logging
import os
import pathlib

import pytest

from wayback_machine_downloader_companion import logging_utils


def make_logs(logs: pathlib.Path, names: list[str]) -> None:
    """Writes log files, the first one oldest.

    Args:
        logs: The log folder (created if needed).
        names: The file names, oldest first; each gets the mtime of its index.
    """
    logs.mkdir(exist_ok=True)
    for index, name in enumerate(names):
        old = logs / name
        _ = old.write_text("x", encoding="utf-8")
        os.utime(old, (index, index))  # pathlib has no API to set a file's times


@pytest.mark.usefixtures("restore_root_logger")
def test_logs_go_to_a_folder_and_old_ones_are_pruned(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each run's log lands in logs/, and only the most recent files are kept."""
    monkeypatch.chdir(tmp_path)
    logs = tmp_path / "logs"
    make_logs(logs, [f"wmdc-{index}.log" for index in range(logging_utils.KEPT_LOG_FILES + 5)])

    logging_utils.configure_logging("wmdc")

    assert len(list(logs.glob("wmdc-*.log*"))) == logging_utils.KEPT_LOG_FILES
    assert (logs / f"wmdc-{os.getpid()}.log").exists()
    assert not (logs / "wmdc-0.log").exists()


@pytest.mark.parametrize(
    ("verbosity", "level"), [(0, logging.INFO), (1, logging.DEBUG), (5, logging.DEBUG)]
)
@pytest.mark.usefixtures("restore_root_logger")
def test_verbosity_sets_the_root_level(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, verbosity: int, level: int
) -> None:
    """No ``-v`` logs info; one or more log debug (extra ``-v`` don't go out of range)."""
    monkeypatch.chdir(tmp_path)

    logging_utils.configure_logging("wmdc", verbosity)

    assert logging.getLogger().level == level


def test_pruning_wmdc_leaves_the_other_programs_logs_alone(tmp_path: pathlib.Path) -> None:
    """Regression test: ``wmdc-*.log*`` also matched (and deleted) ``wmdc-merge-*.log``."""
    others = [
        f"wmdc-{prog}-{index}.log" for prog in ("merge", "find", "download") for index in (1, 2)
    ]
    make_logs(tmp_path, [*others, "wmdc-7.log", "wmdc-8.log"])

    logging_utils._prune_old_logs(tmp_path, "wmdc", 1)  # pyright: ignore[reportPrivateUsage]  # pylint: disable=protected-access

    assert sorted(path.name for path in tmp_path.iterdir()) == sorted([*others, "wmdc-8.log"])


def test_rotated_files_count_toward_the_budget(tmp_path: pathlib.Path) -> None:
    """``.log.1`` backups are the program's logs too: they use up the files kept."""
    make_logs(tmp_path, ["wmdc-1.log", "wmdc-2.log.1", "wmdc-2.log"])

    logging_utils._prune_old_logs(tmp_path, "wmdc", 2)  # pyright: ignore[reportPrivateUsage]  # pylint: disable=protected-access

    assert sorted(path.name for path in tmp_path.iterdir()) == ["wmdc-2.log", "wmdc-2.log.1"]


def test_pruning_tolerates_a_log_deleted_by_another_process(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test: a file another run deleted between glob and stat crashed the pruning."""
    make_logs(tmp_path, ["wmdc-1.log", "wmdc-2.log", "wmdc-3.log"])
    real_glob = pathlib.Path.glob

    def glob_then_vanish(self: pathlib.Path, pattern: str) -> list[pathlib.Path]:
        """List the matches, then delete the newest as another process would.

        Args:
            self: The folder searched.
            pattern: The glob pattern.

        Returns:
            The matches, the deleted one included.
        """
        found = sorted(real_glob(self, pattern))
        found[-1].unlink()  # the other process wins the race for the newest file
        return found

    monkeypatch.setattr(pathlib.Path, "glob", glob_then_vanish)

    logging_utils._prune_old_logs(tmp_path, "wmdc", 1)  # pyright: ignore[reportPrivateUsage]  # pylint: disable=protected-access

    assert [path.name for path in tmp_path.iterdir()] == ["wmdc-2.log"]


def test_a_log_the_os_refuses_to_delete_is_kept(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file still open elsewhere (Windows) stays for a later run, without an error."""
    make_logs(tmp_path, ["wmdc-1.log", "wmdc-2.log"])

    def refuse(_self: pathlib.Path, missing_ok: bool = False) -> None:
        """Fail like a file another process holds open (Windows).

        Args:
            _self: Ignored.
            missing_ok: Ignored.

        Raises:
            PermissionError: Always.
        """
        del missing_ok
        raise PermissionError("in use")

    monkeypatch.setattr(pathlib.Path, "unlink", refuse)

    logging_utils._prune_old_logs(tmp_path, "wmdc", 1)  # pyright: ignore[reportPrivateUsage]  # pylint: disable=protected-access

    assert (tmp_path / "wmdc-1.log").exists()
