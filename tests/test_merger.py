"""Tests for wayback_machine_downloader_companion.merger."""

import pathlib

import pytest

from wayback_machine_downloader_companion.merger import MergePlan, get_all_files, is_snapshot_folder, rm_tree


def test_get_all_files_returns_empty_plan_when_no_versions(make_config) -> None:
    """Regression test: this used to return a bare ``[]``, crashing callers that unpacked it."""
    config = make_config()
    config.folder_snapshots.mkdir(parents=True)

    plan = get_all_files(config)

    assert plan == MergePlan()
    assert plan.sources == []
    assert plan.destinations == []


def test_get_all_files_missing_snapshot_folder_does_not_raise(make_config) -> None:
    config = make_config()

    plan = get_all_files(config)

    assert plan.sources == []


def test_get_all_files_prefers_most_recent_version(make_config) -> None:
    config = make_config()

    older = config.folder_snapshots / '20230101000000'
    newer = config.folder_snapshots / '20230601000000'
    older.mkdir(parents=True)
    newer.mkdir(parents=True)

    (older / 'page.htm').write_text('old', encoding='utf-8')
    (newer / 'page.htm').write_text('new', encoding='utf-8')
    (newer / 'only-in-newer.css').write_text('css', encoding='utf-8')

    plan = get_all_files(config)

    assert len(plan.sources) == len(plan.destinations) == 2
    page_index = next(i for i, dest in enumerate(plan.destinations) if dest.name == 'page.htm')
    assert plan.sources[page_index].read_text(encoding='utf-8') == 'new'


def test_get_all_files_ignores_non_snapshot_folders(make_config) -> None:
    """Regression test: get_all_files used to merge *any* subfolder, not just real snapshots.

    needs_merge() (cli_launcher.py) only ever triggers a merge for 14-digit timestamp folders,
    but get_all_files() used to include every directory regardless of name. A stray folder
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

    plan = get_all_files(config)

    assert len(plan.sources) == 1
    assert plan.sources[0].read_text(encoding='utf-8') == 'real snapshot content'


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


def test_merge_plan_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match='same length'):
        MergePlan(sources=[pathlib.Path('a')], destinations=[])


def test_rm_tree_removes_folder_and_content(tmp_path: pathlib.Path) -> None:
    target = tmp_path / 'to_delete'
    (target / 'nested').mkdir(parents=True)
    (target / 'file.txt').write_text('x', encoding='utf-8')
    (target / 'nested' / 'inner.txt').write_text('y', encoding='utf-8')

    rm_tree(target)

    assert not target.exists()


def test_rm_tree_missing_folder_does_not_raise(tmp_path: pathlib.Path) -> None:
    rm_tree(tmp_path / 'does-not-exist')
