"""Tests for wayback_machine_downloader_companion.downloader."""

import argparse
import pathlib
import shlex
import subprocess
from unittest import mock

import pytest

from wayback_machine_downloader_companion import downloader
from wayback_machine_downloader_companion.downloader import run, start_process


class _FakeProcess:
    def __init__(self, lines: list[bytes]) -> None:
        self.stdout = iter(lines)
        self.terminate = mock.Mock()

    def __enter__(self) -> '_FakeProcess':
        return self

    def __exit__(self, *_exc_info: object) -> None:
        return None


def test_repeated_whitespace_does_not_produce_empty_argv_tokens() -> None:
    """Regression test: ``command.split(' ')`` turned runs of whitespace into empty tokens.

    An empty string in the argv list passed to ``subprocess.Popen`` is treated as a real
    (blank) argument, silently corrupting the command line.
    """
    command = 'wayback_machine_downloader -e  http://example.com/'  # accidental double space

    assert shlex.split(command) == ['wayback_machine_downloader', '-e', 'http://example.com/']


def test_start_process_returns_zero_on_completion_marker(tmp_path: pathlib.Path) -> None:
    fake_process = _FakeProcess([b'starting\n', b'Download completed\n'])

    with mock.patch('subprocess.Popen', return_value=fake_process) as popen:
        result = start_process('wayback_machine_downloader -e http://example.com/', cwd=tmp_path)

    assert result == 0
    fake_process.terminate.assert_called_once()
    popen.assert_called_once_with(
        ['wayback_machine_downloader', '-e', 'http://example.com/'],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def test_start_process_returns_one_when_marker_never_seen(tmp_path: pathlib.Path) -> None:
    fake_process = _FakeProcess([b'starting\n', b'still working\n'])

    with mock.patch('subprocess.Popen', return_value=fake_process):
        result = start_process('wayback_machine_downloader -e http://example.com/', cwd=tmp_path)

    assert result == 1


def test_start_process_survives_non_utf8_output(tmp_path: pathlib.Path) -> None:
    """Regression test: a non-UTF-8 byte sequence in subprocess output used to crash the loop.

    strict ``.decode('utf-8')`` raised UnicodeDecodeError on any malformed line, aborting the
    whole download instead of just that one line.
    """
    fake_process = _FakeProcess([b'\xff\xfe garbled\n', b'Download completed\n'])

    with mock.patch('subprocess.Popen', return_value=fake_process):
        result = start_process('wayback_machine_downloader -e http://example.com/', cwd=tmp_path)

    assert result == 0


def test_run_returns_nonzero_when_a_download_fails(make_config, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test: run() used to always return 0 regardless of per-URL failures."""
    config = make_config()
    (config.base_dir / 'missing_html.txt').write_text('http://example.com/a.htm\n', encoding='utf-8')
    (config.base_dir / 'missing_other.txt').write_text('', encoding='utf-8')

    monkeypatch.setattr(downloader, 'start_process', lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(downloader.time, 'sleep', lambda *_args: None)

    result = run(config, argparse.Namespace())

    assert result == 1
