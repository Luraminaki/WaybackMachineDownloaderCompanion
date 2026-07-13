"""Tests for wayback_machine_downloader_companion.config."""

import pathlib

import pytest

from wayback_machine_downloader_companion.config import AppConfig, ConfigError


def test_load_valid_config(tmp_path: pathlib.Path) -> None:
    config_path = tmp_path / 'config.json'
    config_path.write_text('{"WEB_FOLDER": "site.example", "WEB_OUTPUT": "site.example_output"}', encoding='utf-8')

    config = AppConfig.load(config_path)

    assert config.web_folder == 'site.example'
    assert config.web_output == 'site.example_output'
    assert config.base_dir == tmp_path.resolve()
    assert config.folder_output == tmp_path.resolve() / 'site.example_output'
    assert config.folder_snapshots == tmp_path.resolve() / 'site.example'


def test_web_output_defaults_from_web_folder(tmp_path: pathlib.Path) -> None:
    config_path = tmp_path / 'config.json'
    config_path.write_text('{"WEB_FOLDER": "site.example"}', encoding='utf-8')

    config = AppConfig.load(config_path)

    assert config.web_output == 'site.example_output'


def test_web_folder_and_output_are_stripped(tmp_path: pathlib.Path) -> None:
    """Regression test: whitespace used to be checked but not removed before storing."""
    config_path = tmp_path / 'config.json'
    config_path.write_text('{"WEB_FOLDER": " site.example ", "WEB_OUTPUT": " out "}', encoding='utf-8')

    config = AppConfig.load(config_path)

    assert config.web_folder == 'site.example'
    assert config.web_output == 'out'


def test_missing_web_folder_raises_config_error(tmp_path: pathlib.Path) -> None:
    config_path = tmp_path / 'config.json'
    config_path.write_text('{"WEB_OUTPUT": "out"}', encoding='utf-8')

    with pytest.raises(ConfigError):
        AppConfig.load(config_path)


def test_malformed_json_raises_config_error(tmp_path: pathlib.Path) -> None:
    config_path = tmp_path / 'config.json'
    config_path.write_text('{not valid json', encoding='utf-8')

    with pytest.raises(ConfigError):
        AppConfig.load(config_path)


def test_missing_file_raises_file_not_found(tmp_path: pathlib.Path) -> None:
    with pytest.raises(FileNotFoundError):
        AppConfig.load(tmp_path / 'nope.json')
