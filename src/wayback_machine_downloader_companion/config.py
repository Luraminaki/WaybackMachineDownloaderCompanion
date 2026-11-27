#!/usr/bin/env python3
"""Typed configuration loaded from ``config.json``."""

import dataclasses
import json
import pathlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

MISSING_HTML_FILE = "missing_html.txt"
MISSING_OTHER_FILE = "missing_other.txt"
UNSPECIFIED_FILE = "unspecified.txt"


class ConfigError(Exception):
    """Raised when ``config.json`` is missing required data or malformed."""


@dataclasses.dataclass(frozen=True, slots=True)
class AppConfig:
    """Runtime configuration shared by every WMDC command.

    Attributes:
        web_folder (str): The folder wayback-machine-downloader created for the site (named
            after its host, holding the ``-s`` timestamp subfolders); also the host put back
            into exported URLs (see
            :func:`wayback_machine_downloader_companion.finder.export_missing`).
        web_output (str): The folder that is scanned for missing files and receives downloads
            and merges. Defaults to ``f"{web_folder}_output"``; set it to ``web_folder`` for a
            download made without ``-s`` (no merge needed).
        base_dir (pathlib.Path): Directory ``config.json`` lives in (wayback-machine-downloader's
            ``websites/`` folder); both folders above are inside it. Injected by :meth:`load`.
    """

    web_folder: str
    web_output: str
    base_dir: "pathlib.Path"

    @property
    def folder_output(self) -> "pathlib.Path":
        """pathlib.Path: Absolute path to the folder holding downloaded website content."""
        return self.base_dir / self.web_output

    @property
    def folder_snapshots(self) -> "pathlib.Path":
        """pathlib.Path: Absolute path to the folder holding versioned wayback snapshots."""
        return self.base_dir / self.web_folder

    @classmethod
    def load(cls, config_path: "pathlib.Path") -> "AppConfig":
        """Loads and validates configuration from a JSON file.

        Args:
            config_path (pathlib.Path): Path to a ``config.json`` file.

        Returns:
            AppConfig: The parsed and validated configuration.

        Raises:
            FileNotFoundError: ``config_path`` does not exist.
            ConfigError: The file is unreadable (e.g. a folder, or not UTF-8), not valid JSON,
                not a JSON object, or has a missing/invalid ``WEB_FOLDER`` or an invalid
                ``WEB_OUTPUT``.
        """
        try:
            # utf-8-sig also accepts the BOM some editors (Windows Notepad) put at the start.
            raw = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError as error:
            raise FileNotFoundError(f"Config file not found: {config_path}") from error
        except (OSError, UnicodeDecodeError) as error:
            raise ConfigError(f"Can't read {config_path}: {error}") from error
        except json.JSONDecodeError as error:
            raise ConfigError(f"Invalid JSON in {config_path}: {error}") from error

        if not isinstance(raw, dict):
            raise ConfigError(f"{config_path} must contain a JSON object")

        web_folder = _folder_name(raw, "WEB_FOLDER", config_path)
        web_output = (
            f"{web_folder}_output"
            if raw.get("WEB_OUTPUT") is None
            else _folder_name(raw, "WEB_OUTPUT", config_path)
        )
        return cls(
            web_folder=web_folder, web_output=web_output, base_dir=config_path.resolve().parent
        )


def _folder_name(raw: "Mapping[str, object]", key: str, config_path: pathlib.Path) -> str:
    """Reads a folder setting: a plain folder name, next to ``config.json``.

    Args:
        raw (Mapping[str, object]): The parsed ``config.json``.
        key (str): The setting.
        config_path (pathlib.Path): The file, for error messages.

    Returns:
        str: The folder name, stripped.

    Raises:
        ConfigError: The value isn't a non-empty string naming one folder (no ``/``, ``.`` or
            ``..``): anything else could point the merge at folders it must not write into.
    """
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f'{config_path}: "{key}" must be a non-empty string')
    name = value.strip()
    if name in {".", ".."} or pathlib.PurePath(name).name != name or "\\" in name:
        raise ConfigError(f'{config_path}: "{key}" must be a folder name, not a path: {name!r}')
    return name
