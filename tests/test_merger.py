"""Tests for wayback_machine_downloader_companion.merger."""

import argparse
import logging
from typing import TYPE_CHECKING

import pytest

from tests.merger_helpers import (
    NEWER_SNAPSHOT,
    OLDER_SNAPSHOT,
    manifest,
    output,
    temporaries,
    write_snapshot,
)
from wayback_machine_downloader_companion import merger
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


def test_build_merge_plan_missing_snapshot_folder_does_not_raise(make_config: "MakeConfig") -> None:
    """A missing snapshot folder gives an empty plan, not an error."""
    config = make_config()

    plan = build_merge_plan(config)

    assert plan.entries == []


def test_build_merge_plan_prefers_most_recent_version(make_config: "MakeConfig") -> None:
    """When versions overlap, the most recent file wins the merge."""
    config = make_config()

    older = config.folder_snapshots / OLDER_SNAPSHOT
    newer = config.folder_snapshots / NEWER_SNAPSHOT
    older.mkdir(parents=True)
    newer.mkdir(parents=True)

    _ = (older / "page.htm").write_text("old", encoding="utf-8")
    _ = (newer / "page.htm").write_text("new", encoding="utf-8")
    _ = (newer / "only-in-newer.css").write_text("css", encoding="utf-8")

    plan = build_merge_plan(config)

    assert len(plan.entries) == 2
    entry = next(entry for entry in plan.entries if entry.relative == "page.htm")
    assert entry.source.read_text(encoding="utf-8") == "new"
    assert entry.snapshot == NEWER_SNAPSHOT


def test_build_merge_plan_ignores_non_snapshot_folders(make_config: "MakeConfig") -> None:
    """Regression test: build_merge_plan used to merge *any* subfolder, not just real snapshots.

    needs_merge() (cli_launcher.py) only ever triggers a merge for 14-digit timestamp folders,
    but build_merge_plan() used to include every directory regardless of name. A stray folder
    sorting ahead of the real snapshots lexicographically could silently win the merge over
    genuine archived content.
    """
    config = make_config()

    snapshot = config.folder_snapshots / OLDER_SNAPSHOT
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
    valid = tmp_path / OLDER_SNAPSHOT
    valid.mkdir()

    not_timestamped = tmp_path / "backup"
    not_timestamped.mkdir()

    not_a_dir = tmp_path / f"{OLDER_SNAPSHOT}.txt"
    _ = not_a_dir.write_text("x", encoding="utf-8")

    assert is_snapshot_folder(valid) is True
    assert is_snapshot_folder(not_timestamped) is False
    assert is_snapshot_folder(not_a_dir) is False


def test_run_merges_snapshot_into_output(make_config: "MakeConfig") -> None:
    """Running the merge copies the snapshot into the output folder."""
    config = make_config()
    snapshot = config.folder_snapshots / OLDER_SNAPSHOT
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


def test_dotted_folders_and_extensionless_files_are_merged(make_config: "MakeConfig") -> None:
    """`jquery.ui/` is a folder to walk, `robots` a file to copy (both used to break or vanish)."""
    config = make_config()
    write_snapshot(config, OLDER_SNAPSHOT, {"jquery.ui/theme.css": "css", "robots": "txt"})

    assert run(config, argparse.Namespace()) == 0

    assert output(config, "jquery.ui/theme.css") == "css"
    assert output(config, "robots") == "txt"


def test_remerge_keeps_downloaded_and_edited_files(make_config: "MakeConfig") -> None:
    """A second merge never overwrites a file it didn't write, nor one edited since."""
    config = make_config()
    write_snapshot(config, OLDER_SNAPSHOT, {"page.htm": "archived", "edited.htm": "archived"})
    assert run(config, argparse.Namespace()) == 0
    _ = (config.folder_output / "downloaded.htm").write_text("fetched later", encoding="utf-8")
    _ = (config.folder_output / "edited.htm").write_text("fixed by hand", encoding="utf-8")
    write_snapshot(config, NEWER_SNAPSHOT, {"edited.htm": "newer", "downloaded.htm": "newer"})

    assert run(config, argparse.Namespace()) == 0

    assert output(config, "downloaded.htm") == "fetched later"
    assert output(config, "edited.htm") == "fixed by hand"
    assert output(config, "page.htm") == "archived"


def test_newer_snapshot_updates_files_the_merge_wrote(make_config: "MakeConfig") -> None:
    """A file still as the last merge left it takes a newer snapshot's version."""
    config = make_config()
    write_snapshot(config, OLDER_SNAPSHOT, {"page.htm": "old"})
    assert run(config, argparse.Namespace()) == 0
    write_snapshot(config, NEWER_SNAPSHOT, {"page.htm": "new"})

    assert run(config, argparse.Namespace()) == 0

    assert output(config, "page.htm") == "new"
    assert temporaries(config) == []
    assert (config.folder_output / MANIFEST_FILE).is_file()


def test_output_inside_the_snapshots_is_refused(make_config: "MakeConfig") -> None:
    """WEB_OUTPUT == WEB_FOLDER: the merge refuses instead of destroying the snapshots."""
    config = make_config(web_output="example.com")
    write_snapshot(config, OLDER_SNAPSHOT, {"page.htm": "archived"})

    assert run(config, argparse.Namespace()) == 1

    assert (config.folder_snapshots / OLDER_SNAPSHOT / "page.htm").is_file()


# --- file/folder collisions across snapshots ---


def merge_file_against_folder(
    config: "AppConfig", caplog: pytest.LogCaptureFixture, file_merged_first: bool
) -> None:
    """Merge a file `about` and, from the other snapshot, `about/team.htm` and `index.htm`.

    The file `about` must stay, and `index.htm` be merged, whichever way they meet.

    Args:
        config: The active configuration.
        caplog: Captures the second merge's warnings.
        file_merged_first: The file is in the older snapshot and merged on its own first;
            otherwise it is in the newer one and both snapshots merge together.
    """
    file_snapshot, folder_snapshot = (
        (OLDER_SNAPSHOT, NEWER_SNAPSHOT) if file_merged_first else (NEWER_SNAPSHOT, OLDER_SNAPSHOT)
    )
    write_snapshot(config, file_snapshot, {"about": "page"})
    if file_merged_first:
        assert run(config, argparse.Namespace()) == 0
    write_snapshot(config, folder_snapshot, {"about/team.htm": "team", "index.htm": "index"})

    with caplog.at_level(logging.WARNING, logger=merger.logger.name):
        assert run(config, argparse.Namespace()) == 0

    assert output(config, "about") == "page"
    assert output(config, "index.htm") == "index"


def test_newer_file_wins_over_an_older_folder_of_the_same_name(
    make_config: "MakeConfig", caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: newer file `about` vs older `about/team.htm` crashed with FileExistsError."""
    config = make_config()

    merge_file_against_folder(config, caplog, file_merged_first=False)

    assert sorted(manifest(config)) == ["about", "index.htm"]
    assert "a newer snapshot has about as a file" in caplog.text


def test_newer_folder_wins_over_an_older_file_of_the_same_name(
    make_config: "MakeConfig", caplog: pytest.LogCaptureFixture
) -> None:
    """Newer `about/team.htm` vs older file `about`: the folder wins, with a warning."""
    config = make_config()
    write_snapshot(config, NEWER_SNAPSHOT, {"about/team.htm": "team"})
    write_snapshot(config, OLDER_SNAPSHOT, {"about": "page"})

    with caplog.at_level(logging.WARNING, logger=merger.logger.name):
        assert run(config, argparse.Namespace()) == 0

    assert output(config, "about/team.htm") == "team"
    assert sorted(manifest(config)) == ["about/team.htm"]
    assert "a newer snapshot has about as a folder" in caplog.text


def test_build_merge_plan_skips_paths_below_a_newer_file(make_config: "MakeConfig") -> None:
    """A newer file shadows an older folder at any depth, and only what lies below it."""
    config = make_config()
    write_snapshot(config, NEWER_SNAPSHOT, {"a/b": "file"})
    write_snapshot(config, OLDER_SNAPSHOT, {"a/b/c/d.htm": "deep", "a/e.htm": "sibling"})

    plan = build_merge_plan(config)

    assert sorted(entry.relative for entry in plan.entries) == ["a/b", "a/e.htm"]


def test_output_file_in_the_way_of_a_newer_folder_is_kept(
    make_config: "MakeConfig", caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: a merged file `about`, then a newer `about/team.htm`, crashed the re-merge."""
    config = make_config()

    merge_file_against_folder(config, caplog, file_merged_first=True)

    assert "in the way of its folder" in caplog.text


def test_output_folder_where_a_file_should_go_is_kept(make_config: "MakeConfig") -> None:
    """A folder sitting where a snapshot has a file is left alone, its content too."""
    config = make_config()
    mine = config.folder_output / "page.htm" / "mine.txt"
    mine.parent.mkdir(parents=True)
    _ = mine.write_text("mine", encoding="utf-8")
    write_snapshot(config, NEWER_SNAPSHOT, {"page.htm": "archived"})

    assert run(config, argparse.Namespace()) == 0

    assert mine.read_text(encoding="utf-8") == "mine"


# --- symlinks ---


@pytest.mark.usefixtures("can_symlink")
def test_symlinked_file_in_a_snapshot_is_skipped(
    make_config: "MakeConfig", tmp_path: "pathlib.Path", caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: a symlinked file was followed, copying whatever it pointed at."""
    config = make_config()
    outside = tmp_path / "outside.txt"
    _ = outside.write_text("outside", encoding="utf-8")
    write_snapshot(config, NEWER_SNAPSHOT, {"page.htm": "page"})
    (config.folder_snapshots / NEWER_SNAPSHOT / "link.htm").symlink_to(outside)

    with caplog.at_level(logging.WARNING, logger=merger.logger.name):
        assert run(config, argparse.Namespace()) == 0

    assert output(config, "page.htm") == "page"
    assert not (config.folder_output / "link.htm").exists()
    assert "Skipping symlink" in caplog.text


@pytest.mark.usefixtures("can_symlink")
def test_symlinked_folder_in_a_snapshot_is_not_walked(
    make_config: "MakeConfig", tmp_path: "pathlib.Path"
) -> None:
    """A symlinked folder's content stays out of the plan."""
    config = make_config()
    outside = tmp_path / "outside"
    outside.mkdir()
    _ = (outside / "inner.htm").write_text("outside", encoding="utf-8")
    write_snapshot(config, NEWER_SNAPSHOT, {"page.htm": "page"})
    (config.folder_snapshots / NEWER_SNAPSHOT / "linked").symlink_to(
        outside, target_is_directory=True
    )

    plan = build_merge_plan(config)

    assert [entry.relative for entry in plan.entries] == ["page.htm"]


@pytest.mark.usefixtures("can_symlink")
def test_output_symlinked_into_the_snapshots_is_refused(make_config: "MakeConfig") -> None:
    """A WEB_OUTPUT that is a symlink into WEB_FOLDER counts as nested: nothing is written."""
    config = make_config(web_output="merged")
    write_snapshot(config, NEWER_SNAPSHOT, {"page.htm": "page"})
    inside = config.folder_snapshots / "merged"
    inside.mkdir()
    config.folder_output.symlink_to(inside, target_is_directory=True)

    assert run(config, argparse.Namespace()) == 1

    assert list(inside.iterdir()) == []


# --- the merge manifest ---


def test_manifest_at_a_snapshot_root_does_not_replace_the_output_manifest(
    make_config: "MakeConfig", caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: a snapshot's own `.wmdc-merge.json` was copied over the output's, as a file.

    The merge then recorded the manifest as one of its own outputs.
    """
    config = make_config()
    write_snapshot(config, OLDER_SNAPSHOT, {"page.htm": "old"})
    write_snapshot(config, NEWER_SNAPSHOT, {MANIFEST_FILE: '{"forged": {}}', "news.htm": "news"})

    with caplog.at_level(logging.INFO, logger=merger.logger.name):
        assert run(config, argparse.Namespace()) == 0

    assert {key: record["snapshot"] for key, record in manifest(config).items()} == {
        "news.htm": NEWER_SNAPSHOT,
        "page.htm": OLDER_SNAPSHOT,
    }
    assert "a merge manifest, not a site file" in caplog.text


def test_manifest_name_below_a_snapshot_root_is_a_site_file(make_config: "MakeConfig") -> None:
    """Only the root path is the manifest: the same name in a subfolder is merged."""
    config = make_config()
    write_snapshot(
        config, NEWER_SNAPSHOT, {MANIFEST_FILE: "{}", f"docs/{MANIFEST_FILE}": "site file"}
    )

    plan = build_merge_plan(config)

    assert [entry.relative for entry in plan.entries] == [f"docs/{MANIFEST_FILE}"]
