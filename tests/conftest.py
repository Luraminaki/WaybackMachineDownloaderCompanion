"""Shared pytest fixtures for the WMDC test suite."""

import json
import pathlib

import pytest

from wayback_machine_downloader_companion.config import AppConfig


@pytest.fixture
def make_config(tmp_path: pathlib.Path):
    """Return a factory that writes a ``config.json`` under ``tmp_path`` and loads it.

    Args:
        tmp_path: Pytest's per-test temporary directory.

    Returns:
        A callable ``(web_folder, web_output=None) -> AppConfig``.
    """

    def _make(web_folder: str = 'example.com', web_output: str | None = None) -> AppConfig:
        payload = {'WEB_FOLDER': web_folder}
        if web_output is not None:
            payload['WEB_OUTPUT'] = web_output

        config_path = tmp_path / 'config.json'
        config_path.write_text(json.dumps(payload), encoding='utf-8')
        return AppConfig.load(config_path)

    return _make
