"""Tests for wayback_machine_downloader_companion.cli_launcher."""

import argparse
import logging
import pathlib

import pytest

from wayback_machine_downloader_companion import _cli, cli_launcher, downloader, finder, merger
from wayback_machine_downloader_companion.finder import FinderResult


def test_configure_parser_defaults() -> None:
    parser = _cli.build_parser('wmdc', 'test', configure_parser=cli_launcher.configure_parser)
    args = parser.parse_args([])

    assert args.mode is None
    assert args.force_merge is False
    assert args.max_iterations == cli_launcher._DEFAULT_MAX_ITERATIONS


def test_needs_merge_false_when_snapshot_folder_missing(make_config) -> None:
    config = make_config()
    assert cli_launcher.needs_merge(config) is False


def test_needs_merge_true_with_a_versioned_subfolder(make_config) -> None:
    config = make_config()
    (config.folder_snapshots / '20230601000000').mkdir(parents=True)

    assert cli_launcher.needs_merge(config) is True


def test_needs_merge_false_with_only_non_snapshot_subfolders(make_config) -> None:
    config = make_config()
    (config.folder_snapshots / 'backup').mkdir(parents=True)

    assert cli_launcher.needs_merge(config) is False


def test_needs_merge_false_when_snapshot_folder_vanishes_during_check(
    make_config, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: needs_merge() used to let a TOCTOU iterdir() failure propagate."""
    config = make_config()
    config.folder_snapshots.mkdir(parents=True)

    def raise_oserror(_self: pathlib.Path) -> None:
        raise OSError('vanished')

    monkeypatch.setattr(pathlib.Path, 'iterdir', raise_oserror)

    assert cli_launcher.needs_merge(config) is False


def test_run_full_aborts_without_scanning_when_merge_fails(make_config, monkeypatch: pytest.MonkeyPatch) -> None:
    config = make_config()
    (config.folder_snapshots / '20230601000000').mkdir(parents=True)

    monkeypatch.setattr(merger, 'run', lambda *_a, **_k: 1)
    scan_calls: list[object] = []
    monkeypatch.setattr(finder, 'scan', lambda _config: scan_calls.append(1))

    result = cli_launcher.run_full(config, argparse.Namespace(force_merge=False, max_iterations=3))

    assert result == 1
    assert scan_calls == []


def test_run_full_returns_zero_when_nothing_missing_on_first_pass(
    make_config, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config()
    monkeypatch.setattr(finder, 'scan', lambda _config: FinderResult(scanned=True, missing_count=0))
    download_calls: list[object] = []
    monkeypatch.setattr(downloader, 'run', lambda *_a, **_k: download_calls.append(1) or 0)

    result = cli_launcher.run_full(config, argparse.Namespace(force_merge=False, max_iterations=3))

    assert result == 0
    assert download_calls == []


def test_run_full_loops_until_nothing_missing(make_config, monkeypatch: pytest.MonkeyPatch) -> None:
    results = [FinderResult(scanned=True, missing_count=2), FinderResult(scanned=True, missing_count=0)]
    monkeypatch.setattr(finder, 'scan', lambda _config: results.pop(0))
    download_calls: list[object] = []
    monkeypatch.setattr(downloader, 'run', lambda *_a, **_k: download_calls.append(1) or 0)

    result = cli_launcher.run_full(make_config(), argparse.Namespace(force_merge=False, max_iterations=5))

    assert result == 0
    assert len(download_calls) == 1


def test_run_full_returns_one_when_nothing_to_scan(make_config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(finder, 'scan', lambda _config: FinderResult(scanned=False, missing_count=0))

    result = cli_launcher.run_full(make_config(), argparse.Namespace(force_merge=False, max_iterations=3))

    assert result == 1


def test_run_full_returns_one_when_max_iterations_exhausted(make_config, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test: run_full used to always return 0, even when it never converged."""
    monkeypatch.setattr(finder, 'scan', lambda _config: FinderResult(scanned=True, missing_count=1))
    monkeypatch.setattr(downloader, 'run', lambda *_a, **_k: 0)

    result = cli_launcher.run_full(make_config(), argparse.Namespace(force_merge=False, max_iterations=2))

    assert result == 1


def test_run_full_returns_one_when_merge_raises(make_config, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test: an unexpected error from a step used to surface as a single generic
    'Unhandled error' with no indication of which step/iteration was in progress.
    """
    config = make_config()
    (config.folder_snapshots / '20230601000000').mkdir(parents=True)

    def raise_error(*_a: object, **_k: object) -> int:
        raise RuntimeError('boom')

    monkeypatch.setattr(merger, 'run', raise_error)

    result = cli_launcher.run_full(config, argparse.Namespace(force_merge=False, max_iterations=3))

    assert result == 1


def test_run_full_returns_one_when_finder_scan_raises(make_config, monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_error(_config: object) -> FinderResult:
        raise RuntimeError('boom')

    monkeypatch.setattr(finder, 'scan', raise_error)

    result = cli_launcher.run_full(make_config(), argparse.Namespace(force_merge=False, max_iterations=3))

    assert result == 1


def test_run_full_returns_one_when_downloader_raises(make_config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(finder, 'scan', lambda _config: FinderResult(scanned=True, missing_count=1))

    def raise_error(*_a: object, **_k: object) -> int:
        raise RuntimeError('boom')

    monkeypatch.setattr(downloader, 'run', raise_error)

    result = cli_launcher.run_full(make_config(), argparse.Namespace(force_merge=False, max_iterations=3))

    assert result == 1


def test_run_full_checks_for_unspecified_leftovers_when_done(make_config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(finder, 'scan', lambda _config: FinderResult(scanned=True, missing_count=0))
    calls: list[object] = []
    monkeypatch.setattr(cli_launcher, '_warn_if_unspecified_remain', lambda _config: calls.append(1))

    result = cli_launcher.run_full(make_config(), argparse.Namespace(force_merge=False, max_iterations=3))

    assert result == 0
    assert calls == [1]


def test_warn_if_unspecified_remain_logs_when_file_has_entries(
    make_config, caplog: pytest.LogCaptureFixture,
) -> None:
    config = make_config()
    (config.base_dir / 'unspecified.txt').write_text('https://example.com/a.js\n', encoding='utf-8')

    with caplog.at_level(logging.WARNING):
        cli_launcher._warn_if_unspecified_remain(config)

    assert 'unclassified link' in caplog.text


def test_warn_if_unspecified_remain_silent_when_file_missing(
    make_config, caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        cli_launcher._warn_if_unspecified_remain(make_config())

    assert caplog.text == ''


def test_run_interactive_returns_one_on_eof(make_config, monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_eof(_prompt: str = '') -> str:
        raise EOFError

    monkeypatch.setattr('builtins.input', raise_eof)

    result = cli_launcher.run_interactive(make_config(), argparse.Namespace())

    assert result == 1


def test_run_interactive_dispatches_selected_step(make_config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('builtins.input', lambda _prompt='': '3')
    calls: list[object] = []
    monkeypatch.setattr(finder, 'run', lambda *_a, **_k: calls.append(1) or 0)

    result = cli_launcher.run_interactive(make_config(), argparse.Namespace())

    assert result == 0
    assert calls == [1]


def test_run_interactive_quits_on_invalid_choice(
    make_config, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr('builtins.input', lambda _prompt='': '9')

    result = cli_launcher.run_interactive(make_config(), argparse.Namespace())

    assert result == 0
    assert 'Goodbye' in capsys.readouterr().out


@pytest.mark.parametrize(('mode', 'module'), [('merge', merger), ('find', finder), ('download', downloader)])
def test_run_dispatches_by_mode(make_config, monkeypatch: pytest.MonkeyPatch, mode: str, module: object) -> None:
    calls: list[object] = []
    monkeypatch.setattr(module, 'run', lambda *_a, **_k: calls.append(1) or 0)

    result = cli_launcher.run(make_config(), argparse.Namespace(mode=mode))

    assert result == 0
    assert calls == [1]


def test_run_dispatches_full_mode(make_config, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(cli_launcher, 'run_full', lambda *_a, **_k: calls.append(1) or 0)

    result = cli_launcher.run(make_config(), argparse.Namespace(mode='full'))

    assert result == 0
    assert calls == [1]


def test_run_falls_back_to_interactive_menu_when_mode_is_none(
    make_config, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(cli_launcher, 'run_interactive', lambda *_a, **_k: calls.append(1) or 0)

    result = cli_launcher.run(make_config(), argparse.Namespace(mode=None))

    assert result == 0
    assert calls == [1]
