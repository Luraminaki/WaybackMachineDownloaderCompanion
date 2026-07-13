"""Tests for wayback_machine_downloader_companion.merger."""

import argparse
import pathlib

from wayback_machine_downloader_companion.merger import MergePlan, build_merge_plan, is_snapshot_folder, rm_tree, run


def test_build_merge_plan_returns_empty_plan_when_no_versions(make_config) -> None:
    """Regression test: this used to return a bare ``[]``, crashing callers that unpacked it."""
    config = make_config()
    config.folder_snapshots.mkdir(parents=True)

    plan = build_merge_plan(config)

    assert plan == MergePlan()
    assert plan.entries == []


def test_build_merge_plan_missing_snapshot_folder_does_not_raise(make_config) -> None:
    config = make_config()

    plan = build_merge_plan(config)

    assert plan.entries == []


def test_build_merge_plan_prefers_most_recent_version(make_config) -> None:
    config = make_config()

    older = config.folder_snapshots / '20230101000000'
    newer = config.folder_snapshots / '20230601000000'
    older.mkdir(parents=True)
    newer.mkdir(parents=True)

    (older / 'page.htm').write_text('old', encoding='utf-8')
    (newer / 'page.htm').write_text('new', encoding='utf-8')
    (newer / 'only-in-newer.css').write_text('css', encoding='utf-8')

    plan = build_merge_plan(config)

    assert len(plan.entries) == 2
    source, _destination = next(pair for pair in plan.entries if pair[1].name == 'page.htm')
    assert source.read_text(encoding='utf-8') == 'new'


def test_build_merge_plan_ignores_non_snapshot_folders(make_config) -> None:
    """Regression test: build_merge_plan used to merge *any* subfolder, not just real snapshots.

    needs_merge() (cli_launcher.py) only ever triggers a merge for 14-digit timestamp folders,
    but build_merge_plan() used to include every directory regardless of name. A stray folder
    sorting ahead of the real snapshots lexicographically could silently win the merge over
    genuine archived content.
    """
    config = make_config()

    snapshot = config.folder_snapshots / '20230601000000'
    snapshot.mkdir(parents=True)
    (snapshot / 'page.htm').write_text('real snapshot content', encoding='utf-8')

    stray = config.folder_snapshots / 'zz_backup'
    stray.mkdir(parents=True)
    (stray / 'page.htm').write_text('should not be merged', encoding='utf-8')

    plan = build_merge_plan(config)

    assert len(plan.entries) == 1
    assert plan.entries[0][0].read_text(encoding='utf-8') == 'real snapshot content'


def test_is_snapshot_folder(tmp_path: pathlib.Path) -> None:
    valid = tmp_path / '20230601000000'
    valid.mkdir()

    not_timestamped = tmp_path / 'backup'
    not_timestamped.mkdir()

    not_a_dir = tmp_path / '20230601000001.txt'
    not_a_dir.write_text('x', encoding='utf-8')

    assert is_snapshot_folder(valid) is True
    assert is_snapshot_folder(not_timestamped) is False
    assert is_snapshot_folder(not_a_dir) is False


def test_rm_tree_removes_folder_and_content(tmp_path: pathlib.Path) -> None:
    target = tmp_path / 'to_delete'
    (target / 'nested').mkdir(parents=True)
    (target / 'file.txt').write_text('x', encoding='utf-8')
    (target / 'nested' / 'inner.txt').write_text('y', encoding='utf-8')

    rm_tree(target)

    assert not target.exists()


def test_rm_tree_missing_folder_does_not_raise(tmp_path: pathlib.Path) -> None:
    rm_tree(tmp_path / 'does-not-exist')


def test_run_merges_snapshot_into_output(make_config) -> None:
    config = make_config()
    snapshot = config.folder_snapshots / '20230601000000'
    snapshot.mkdir(parents=True)
    (snapshot / 'page.htm').write_text('content', encoding='utf-8')

    result = run(config, argparse.Namespace())

    assert result == 0
    assert (config.folder_output / 'page.htm').read_text(encoding='utf-8') == 'content'


def test_run_leaves_existing_output_untouched_when_nothing_to_merge(make_config) -> None:
    """Regression test: run() used to unconditionally delete folder_output before checking
    whether there was anything to rebuild it from -- a merge with no snapshot folders present
    (e.g. running wmdc-merge a second time) silently destroyed already-downloaded content.
    """
    config = make_config()
    config.folder_output.mkdir(parents=True)
    (config.folder_output / 'keep-me.txt').write_text('precious', encoding='utf-8')

    result = run(config, argparse.Namespace())

    assert result == 0
    assert (config.folder_output / 'keep-me.txt').read_text(encoding='utf-8') == 'precious'
