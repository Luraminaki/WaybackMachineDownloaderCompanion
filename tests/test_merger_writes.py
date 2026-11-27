"""Tests for how wayback_machine_downloader_companion.merger writes files and its manifest."""

import argparse
import json
import logging
import os
import pathlib
import shutil
import sys
from typing import TYPE_CHECKING

import pytest

from tests.merger_helpers import (
    NEWER_SNAPSHOT,
    OLDER_SNAPSHOT,
    fail_with_a_full_disk,
    manifest,
    output,
    temporaries,
    write_snapshot,
)
from wayback_machine_downloader_companion import merger
from wayback_machine_downloader_companion.merger import MANIFEST_FILE, run

if TYPE_CHECKING:
    from tests.conftest import MakeConfig

#: Windows refuses longer paths unless long paths are enabled system-wide.
_WINDOWS_MAX_PATH = 260


# --- temporary names ---


def test_a_file_name_near_the_length_limit_merges(make_config: "MakeConfig") -> None:
    """Regression: a 250-byte name is valid, but `.<name>.wmdc-tmp` exceeded NAME_MAX."""
    config = make_config()
    name = "p" * 245 + ".html"
    if sys.platform == "win32" and len(str(config.folder_output / name)) >= _WINDOWS_MAX_PATH:
        pytest.skip("the full path exceeds MAX_PATH on a stock Windows")
    write_snapshot(config, NEWER_SNAPSHOT, {name: "long"})

    assert run(config, argparse.Namespace()) == 0

    assert output(config, name) == "long"
    assert temporaries(config) == []


def test_a_users_file_named_like_a_temporary_survives_a_merge(make_config: "MakeConfig") -> None:
    """Regression: the merge wrote through `.wmdc-<pid>.tmp`, clobbering a real file so named."""
    config = make_config()
    write_snapshot(config, NEWER_SNAPSHOT, {"page.htm": "page"})
    config.folder_output.mkdir(parents=True)
    mine = config.folder_output / f".wmdc-{os.getpid()}.tmp"
    _ = mine.write_text("mine", encoding="utf-8")

    assert run(config, argparse.Namespace()) == 0

    assert mine.read_text(encoding="utf-8") == "mine"
    assert output(config, "page.htm") == "page"
    assert temporaries(config) == [mine]


def test_failed_copy_keeps_the_previous_file_and_no_temporary(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """A copy dying halfway leaves the previous output file intact and no temporary file."""
    config = make_config()
    write_snapshot(config, OLDER_SNAPSHOT, {"page.htm": "old"})
    assert run(config, argparse.Namespace()) == 0
    write_snapshot(config, NEWER_SNAPSHOT, {"page.htm": "new"})

    def copy_half_then_fail(source: "pathlib.Path", target: "pathlib.Path") -> object:
        """Write part of the copy, then fail like a full disk.

        Args:
            source: The file copied.
            target: Where its start is written.

        Raises:
            OSError: Always (``ENOSPC``).
        """
        _ = pathlib.Path(target).write_text(source.read_text(encoding="utf-8")[:1], "utf-8")
        raise fail_with_a_full_disk()

    monkeypatch.setattr(shutil, "copy2", copy_half_then_fail)

    with pytest.raises(OSError, match="No space left"):
        _ = run(config, argparse.Namespace())

    assert output(config, "page.htm") == "old"
    assert temporaries(config) == []


# --- manifest ---


def test_files_written_before_a_failed_copy_stay_in_the_manifest(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: a failed copy lost the manifest, so the next merge took merged files as own."""
    config = make_config()
    write_snapshot(config, NEWER_SNAPSHOT, {"a.htm": "a", "b.htm": "b"})
    real_copy = shutil.copy2
    copied: list[pathlib.Path] = []

    def copy_then_fail(source: "pathlib.Path", target: "pathlib.Path") -> object:
        """Copy the first file, then fail like a full disk.

        Args:
            source: The file copied.
            target: Where it goes.

        Returns:
            What the real copy returns.

        Raises:
            OSError: From the second call on (``ENOSPC``).
        """
        if copied:
            raise fail_with_a_full_disk()
        copied.append(source)
        return real_copy(source, target)

    monkeypatch.setattr(shutil, "copy2", copy_then_fail)

    with pytest.raises(OSError, match="No space left"):
        _ = run(config, argparse.Namespace())

    assert list(manifest(config)) == [copied[0].name]
    assert temporaries(config) == []


def test_interrupted_manifest_write_keeps_the_previous_manifest(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: the manifest was written in place, so a failed write left it torn."""
    config = make_config()
    write_snapshot(config, OLDER_SNAPSHOT, {"page.htm": "old"})
    assert run(config, argparse.Namespace()) == 0
    previous = (config.folder_output / MANIFEST_FILE).read_text(encoding="utf-8")
    write_snapshot(config, NEWER_SNAPSHOT, {"page.htm": "new"})
    real_write_text = pathlib.Path.write_text

    def write_half_then_fail(self: pathlib.Path, data: str, encoding: str | None = None) -> int:
        """Write half the text, then fail like a full disk.

        Args:
            self: The file written.
            data: The text, half of it written.
            encoding: Its encoding.

        Raises:
            OSError: Always (``ENOSPC``).
        """
        _ = real_write_text(self, data[: len(data) // 2], encoding=encoding)
        raise fail_with_a_full_disk()

    monkeypatch.setattr(pathlib.Path, "write_text", write_half_then_fail)

    with pytest.raises(OSError, match="No space left"):
        _ = run(config, argparse.Namespace())

    monkeypatch.undo()
    assert (config.folder_output / MANIFEST_FILE).read_text(encoding="utf-8") == previous
    assert temporaries(config) == []


@pytest.mark.parametrize(
    "content",
    ['{"page.htm": {"snapsh', "[]", "42"],
    ids=["torn", "a list", "a number"],
)
def test_unusable_manifest_warns_and_keeps_existing_files(
    make_config: "MakeConfig", caplog: pytest.LogCaptureFixture, content: str
) -> None:
    """Regression (non-object case was silent): warn, keep merged files, merge the new ones."""
    config = make_config()
    write_snapshot(config, OLDER_SNAPSHOT, {"page.htm": "old"})
    assert run(config, argparse.Namespace()) == 0
    _ = (config.folder_output / MANIFEST_FILE).write_text(content, encoding="utf-8")
    write_snapshot(config, NEWER_SNAPSHOT, {"page.htm": "new", "added.htm": "added"})

    with caplog.at_level(logging.WARNING, logger=merger.logger.name):
        assert run(config, argparse.Namespace()) == 0

    assert output(config, "page.htm") == "old"  # no record: kept like a hand-edited file
    assert output(config, "added.htm") == "added"
    assert f"merge manifest {config.folder_output / MANIFEST_FILE}" in caplog.text


def test_manifest_record_that_is_not_an_object_is_ignored(make_config: "MakeConfig") -> None:
    """Regression: a record that isn't a JSON object crashed the merge (`str.get`)."""
    config = make_config()
    write_snapshot(config, OLDER_SNAPSHOT, {"page.htm": "old"})
    assert run(config, argparse.Namespace()) == 0
    _ = (config.folder_output / MANIFEST_FILE).write_text('{"page.htm": "?"}', encoding="utf-8")
    write_snapshot(config, NEWER_SNAPSHOT, {"page.htm": "new"})

    assert run(config, argparse.Namespace()) == 0

    assert output(config, "page.htm") == "old"


def test_immediate_rerun_writes_nothing_and_leaves_the_manifest_alone(
    make_config: "MakeConfig", caplog: pytest.LogCaptureFixture
) -> None:
    """Regression (perf): a re-run with nothing new used to rewrite the manifest anyway."""
    config = make_config()
    write_snapshot(config, NEWER_SNAPSHOT, {"page.htm": "page", "css/site.css": "css"})
    assert run(config, argparse.Namespace()) == 0
    path = config.folder_output / MANIFEST_FILE
    # Same records, another layout: any rewrite would show.
    reformatted = json.dumps(manifest(config), indent=4)
    _ = path.write_text(reformatted, encoding="utf-8")

    with caplog.at_level(logging.INFO, logger=merger.logger.name):
        assert run(config, argparse.Namespace()) == 0

    assert path.read_text(encoding="utf-8") == reformatted
    assert "0 file(s) written, 2 kept as is" in caplog.text


def test_older_snapshot_never_replaces_a_newer_merged_file(make_config: "MakeConfig") -> None:
    """With the newer snapshot gone, an older one doesn't overwrite what it gave."""
    config = make_config()
    write_snapshot(config, NEWER_SNAPSHOT, {"page.htm": "new"})
    assert run(config, argparse.Namespace()) == 0
    shutil.rmtree(config.folder_snapshots / NEWER_SNAPSHOT)
    write_snapshot(config, OLDER_SNAPSHOT, {"page.htm": "old"})

    assert run(config, argparse.Namespace()) == 0

    assert output(config, "page.htm") == "new"
    assert manifest(config)["page.htm"]["snapshot"] == NEWER_SNAPSHOT


def test_empty_snapshot_folders_merge_nothing(make_config: "MakeConfig") -> None:
    """Snapshot folders with no file give an empty output and no manifest."""
    config = make_config()
    (config.folder_snapshots / OLDER_SNAPSHOT).mkdir(parents=True)
    (config.folder_snapshots / NEWER_SNAPSHOT / "empty-dir").mkdir(parents=True)

    assert run(config, argparse.Namespace()) == 0

    assert list(config.folder_output.iterdir()) == []
