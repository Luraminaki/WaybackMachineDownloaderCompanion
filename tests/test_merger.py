"""Tests for wayback_machine_downloader_companion.merger."""

import argparse
from typing import TYPE_CHECKING

from wayback_machine_downloader_companion.merger import (
    MANIFEST_FILE,
    MergePlan,
    build_merge_plan,
    is_snapshot_folder,
    run,
)

if TYPE_CHECKING:
    import pathlib

    from tests.conftest import MakeConfig
    from wayback_machine_downloader_companion.config import AppConfig


def test_build_merge_plan_returns_empty_plan_when_no_versions(make_config: "MakeConfig") -> None:
    """Regression test: this used to return a bare ``[]``, crashing callers that unpacked it."""
    config = make_config()
    config.folder_snapshots.mkdir(parents=True)

    plan = build_merge_plan(config)

    assert plan == MergePlan()
    assert plan.entries == []


def test_build_merge_plan_missing_snapshot_folder_does_not_raise(make_config: "MakeConfig") -> None:
    """A missing snapshot folder gives an empty plan, not an error."""
    config = make_config()

    plan = build_merge_plan(config)

    assert plan.entries == []


def test_build_merge_plan_prefers_most_recent_version(make_config: "MakeConfig") -> None:
    """When versions overlap, the most recent file wins the merge."""
    config = make_config()

    older = config.folder_snapshots / "20230101000000"
    newer = config.folder_snapshots / "20230601000000"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)

    _ = (older / "page.htm").write_text("old", encoding="utf-8")
    _ = (newer / "page.htm").write_text("new", encoding="utf-8")
    _ = (newer / "only-in-newer.css").write_text("css", encoding="utf-8")

    plan = build_merge_plan(config)

    assert len(plan.entries) == 2
    entry = next(entry for entry in plan.entries if entry.relative == "page.htm")
    assert entry.source.read_text(encoding="utf-8") == "new"
    assert entry.snapshot == "20230601000000"


def test_build_merge_plan_ignores_non_snapshot_folders(make_config: "MakeConfig") -> None:
    """Regression test: build_merge_plan used to merge *any* subfolder, not just real snapshots.

    needs_merge() (cli_launcher.py) only ever triggers a merge for 14-digit timestamp folders,
    but build_merge_plan() used to include every directory regardless of name. A stray folder
    sorting ahead of the real snapshots lexicographically could silently win the merge over
    genuine archived content.
    """
    config = make_config()

    snapshot = config.folder_snapshots / "20230601000000"
    snapshot.mkdir(parents=True)
    _ = (snapshot / "page.htm").write_text("real snapshot content", encoding="utf-8")

    stray = config.folder_snapshots / "zz_backup"
    stray.mkdir(parents=True)
    _ = (stray / "page.htm").write_text("should not be merged", encoding="utf-8")

    plan = build_merge_plan(config)

    assert len(plan.entries) == 1
    assert plan.entries[0].source.read_text(encoding="utf-8") == "real snapshot content"


def test_is_snapshot_folder(tmp_path: "pathlib.Path") -> None:
    """Only timestamp-named folders are snapshot folders."""
    valid = tmp_path / "20230601000000"
    valid.mkdir()

    not_timestamped = tmp_path / "backup"
    not_timestamped.mkdir()

    not_a_dir = tmp_path / "20230601000001.txt"
    _ = not_a_dir.write_text("x", encoding="utf-8")

    assert is_snapshot_folder(valid) is True
    assert is_snapshot_folder(not_timestamped) is False
    assert is_snapshot_folder(not_a_dir) is False


def test_run_merges_snapshot_into_output(make_config: "MakeConfig") -> None:
    """Running the merge copies the snapshot into the output folder."""
    config = make_config()
    snapshot = config.folder_snapshots / "20230601000000"
    snapshot.mkdir(parents=True)
    _ = (snapshot / "page.htm").write_text("content", encoding="utf-8")

    result = run(config, argparse.Namespace())

    assert result == 0
    assert (config.folder_output / "page.htm").read_text(encoding="utf-8") == "content"


def test_run_leaves_existing_output_untouched_when_nothing_to_merge(
    make_config: "MakeConfig",
) -> None:
    """With no snapshot to merge, the existing output folder is left untouched.

    Regression test: run() used to delete folder_output before checking whether there was
    anything to rebuild it from -- a second `wmdc-merge` silently destroyed downloaded content.
    """
    config = make_config()
    config.folder_output.mkdir(parents=True)
    _ = (config.folder_output / "keep-me.txt").write_text("precious", encoding="utf-8")

    result = run(config, argparse.Namespace())

    assert result == 0
    assert (config.folder_output / "keep-me.txt").read_text(encoding="utf-8") == "precious"


def write_snapshot(config: "AppConfig", timestamp: str, files: dict[str, str]) -> None:
    """Write a snapshot folder.

    Args:
        config: The active configuration.
        timestamp: The snapshot's 14-digit name.
        files: Relative path -> content.
    """
    for relative, content in files.items():
        path = config.folder_snapshots / timestamp / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(content, encoding="utf-8")


def output(config: "AppConfig", relative: str) -> str:
    """Read an output file.

    Args:
        config: The active configuration.
        relative: Its path in the output folder.

    Returns:
        Its content.
    """
    return (config.folder_output / relative).read_text(encoding="utf-8")


def test_dotted_folders_and_extensionless_files_are_merged(make_config: "MakeConfig") -> None:
    """`jquery.ui/` is a folder to walk, `robots` a file to copy (both used to break or vanish)."""
    config = make_config()
    write_snapshot(config, "20230601000000", {"jquery.ui/theme.css": "css", "robots": "txt"})

    assert run(config, argparse.Namespace()) == 0

    assert output(config, "jquery.ui/theme.css") == "css"
    assert output(config, "robots") == "txt"


def test_remerge_keeps_downloaded_and_edited_files(make_config: "MakeConfig") -> None:
    """A second merge never overwrites a file it didn't write, nor one edited since."""
    config = make_config()
    write_snapshot(config, "20230601000000", {"page.htm": "archived", "edited.htm": "archived"})
    assert run(config, argparse.Namespace()) == 0
    _ = (config.folder_output / "downloaded.htm").write_text("fetched later", encoding="utf-8")
    _ = (config.folder_output / "edited.htm").write_text("fixed by hand", encoding="utf-8")
    write_snapshot(config, "20240101000000", {"edited.htm": "newer", "downloaded.htm": "newer"})

    assert run(config, argparse.Namespace()) == 0

    assert output(config, "downloaded.htm") == "fetched later"
    assert output(config, "edited.htm") == "fixed by hand"
    assert output(config, "page.htm") == "archived"


def test_newer_snapshot_updates_files_the_merge_wrote(make_config: "MakeConfig") -> None:
    """A file still as the last merge left it takes a newer snapshot's version."""
    config = make_config()
    write_snapshot(config, "20230601000000", {"page.htm": "old"})
    assert run(config, argparse.Namespace()) == 0
    write_snapshot(config, "20240101000000", {"page.htm": "new"})

    assert run(config, argparse.Namespace()) == 0

    assert output(config, "page.htm") == "new"
    assert not list(config.folder_output.glob("*.wmdc-tmp"))
    assert (config.folder_output / MANIFEST_FILE).is_file()


def test_output_inside_the_snapshots_is_refused(make_config: "MakeConfig") -> None:
    """WEB_OUTPUT == WEB_FOLDER: the merge refuses instead of destroying the snapshots."""
    config = make_config(web_output="example.com")
    write_snapshot(config, "20230601000000", {"page.htm": "archived"})

    assert run(config, argparse.Namespace()) == 1

    assert (config.folder_snapshots / "20230601000000" / "page.htm").is_file()


def test_case_folding_keeps_the_newest_spelling(make_config: "MakeConfig") -> None:
    """On a case-insensitive filesystem, `A.html` (newer) and `a.html` (older) are one file."""
    config = make_config()
    write_snapshot(config, "20230101000000", {"a.html": "old"})
    write_snapshot(config, "20240101000000", {"A.html": "new"})

    plan = build_merge_plan(config, fold_case=True)

    assert [(entry.relative, entry.snapshot) for entry in plan.entries] == [
        ("A.html", "20240101000000")
    ]
