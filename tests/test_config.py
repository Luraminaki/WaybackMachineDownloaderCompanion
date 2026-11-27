"""Tests for wayback_machine_downloader_companion.config."""

import json
from typing import TYPE_CHECKING

import pytest

from wayback_machine_downloader_companion.config import AppConfig, ConfigError

if TYPE_CHECKING:
    import pathlib


def test_load_valid_config(tmp_path: "pathlib.Path") -> None:
    """A complete config file loads with every value as written."""
    config_path = tmp_path / "config.json"
    _ = config_path.write_text(
        '{"WEB_FOLDER": "site.example", "WEB_OUTPUT": "site.example_output"}', encoding="utf-8"
    )

    config = AppConfig.load(config_path)

    assert config.web_folder == "site.example"
    assert config.web_output == "site.example_output"
    assert config.base_dir == tmp_path.resolve()
    assert config.folder_output == tmp_path.resolve() / "site.example_output"
    assert config.folder_snapshots == tmp_path.resolve() / "site.example"


def test_web_output_defaults_from_web_folder(tmp_path: "pathlib.Path") -> None:
    """The web output folder defaults to `<web folder>_output`."""
    config_path = tmp_path / "config.json"
    _ = config_path.write_text('{"WEB_FOLDER": "site.example"}', encoding="utf-8")

    config = AppConfig.load(config_path)

    assert config.web_output == "site.example_output"


def test_web_folder_and_output_are_stripped(tmp_path: "pathlib.Path") -> None:
    """Regression test: whitespace used to be checked but not removed before storing."""
    config_path = tmp_path / "config.json"
    _ = config_path.write_text(
        '{"WEB_FOLDER": " site.example ", "WEB_OUTPUT": " out "}', encoding="utf-8"
    )

    config = AppConfig.load(config_path)

    assert config.web_folder == "site.example"
    assert config.web_output == "out"


def test_missing_web_folder_raises_config_error(tmp_path: "pathlib.Path") -> None:
    """A config without its web folder is a `ConfigError`."""
    config_path = tmp_path / "config.json"
    _ = config_path.write_text('{"WEB_OUTPUT": "out"}', encoding="utf-8")

    with pytest.raises(ConfigError):
        _ = AppConfig.load(config_path)


def test_malformed_json_raises_config_error(tmp_path: "pathlib.Path") -> None:
    """Malformed JSON is a `ConfigError`, not a raw decoding error."""
    config_path = tmp_path / "config.json"
    _ = config_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ConfigError):
        _ = AppConfig.load(config_path)


def test_missing_file_raises_file_not_found(tmp_path: "pathlib.Path") -> None:
    """A missing config file raises `FileNotFoundError`."""
    with pytest.raises(FileNotFoundError):
        _ = AppConfig.load(tmp_path / "nope.json")


@pytest.mark.parametrize("value", [".", "..", "a/b", "../site", "/abs", "a\\b", "C:\\x"])
def test_folder_settings_must_be_plain_names(tmp_path: "pathlib.Path", value: str) -> None:
    """A path instead of a folder name is refused: it could aim the merge anywhere."""
    config_path = tmp_path / "config.json"
    _ = config_path.write_text(json.dumps({"WEB_FOLDER": "site", "WEB_OUTPUT": value}), "utf-8")

    with pytest.raises(ConfigError, match="folder name"):
        _ = AppConfig.load(config_path)


def test_unreadable_config_is_a_config_error(tmp_path: "pathlib.Path") -> None:
    """A folder given as the config file is a readable `ConfigError`, not a traceback."""
    with pytest.raises(ConfigError, match="Can't read"):
        _ = AppConfig.load(tmp_path)


def test_config_with_a_utf8_bom_loads(tmp_path: "pathlib.Path") -> None:
    """Regression test: a config.json saved with a BOM (Windows Notepad) was invalid JSON."""
    config_path = tmp_path / "config.json"
    _ = config_path.write_bytes(b'\xef\xbb\xbf{"WEB_FOLDER": "site.example"}')

    assert AppConfig.load(config_path).web_folder == "site.example"


@pytest.mark.parametrize("text", ['["site.example"]', "null", '"site.example"'])
def test_top_level_must_be_an_object(tmp_path: "pathlib.Path", text: str) -> None:
    """Valid JSON that isn't an object is refused by name, not with a crash on ``.get``."""
    config_path = tmp_path / "config.json"
    _ = config_path.write_text(text, encoding="utf-8")

    with pytest.raises(ConfigError, match="JSON object"):
        _ = AppConfig.load(config_path)


def test_null_web_output_falls_back_to_the_default(tmp_path: "pathlib.Path") -> None:
    """``"WEB_OUTPUT": null`` means "not set"."""
    config_path = tmp_path / "config.json"
    _ = config_path.write_text('{"WEB_FOLDER": "site", "WEB_OUTPUT": null}', encoding="utf-8")

    assert AppConfig.load(config_path).web_output == "site_output"


@pytest.mark.parametrize("value", ["", "  "])
def test_blank_web_output_is_refused(tmp_path: "pathlib.Path", value: str) -> None:
    """A blank output folder would be the config folder itself: refused, not defaulted."""
    config_path = tmp_path / "config.json"
    _ = config_path.write_text(json.dumps({"WEB_FOLDER": "site", "WEB_OUTPUT": value}), "utf-8")

    with pytest.raises(ConfigError, match="non-empty"):
        _ = AppConfig.load(config_path)


@pytest.mark.parametrize("value", [123, ["site"], True])
def test_web_folder_must_be_a_string(tmp_path: "pathlib.Path", value: object) -> None:
    """A number or a list for WEB_FOLDER is a ``ConfigError``, not a later ``TypeError``."""
    config_path = tmp_path / "config.json"
    _ = config_path.write_text(json.dumps({"WEB_FOLDER": value}), encoding="utf-8")

    with pytest.raises(ConfigError, match="non-empty string"):
        _ = AppConfig.load(config_path)


def test_non_utf8_config_is_a_config_error(tmp_path: "pathlib.Path") -> None:
    """A config saved in another encoding gives a readable error, not a traceback."""
    config_path = tmp_path / "config.json"
    _ = config_path.write_bytes(b'{"WEB_FOLDER": "caf\xe9"}')  # Latin-1

    with pytest.raises(ConfigError, match="Can't read"):
        _ = AppConfig.load(config_path)


@pytest.mark.usefixtures("can_symlink")
def test_base_dir_follows_a_symlinked_config(tmp_path: "pathlib.Path") -> None:
    """The site folders sit next to the real config.json, not next to a link to it."""
    real = tmp_path / "websites"
    real.mkdir()
    _ = (real / "config.json").write_text('{"WEB_FOLDER": "site"}', encoding="utf-8")
    link = tmp_path / "config.json"
    link.symlink_to(real / "config.json")

    assert AppConfig.load(link).base_dir == real.resolve()
