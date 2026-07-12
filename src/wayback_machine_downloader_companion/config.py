#!/usr/bin/env python3
"""Typed configuration loaded from ``config.json``."""

import dataclasses
import json
import pathlib


class ConfigError(Exception):
    """Raised when ``config.json`` is missing required data or malformed."""


@dataclasses.dataclass(frozen=True, slots=True)
class AppConfig:
    """Runtime configuration shared by every WMDC command.

    Attributes:
        web_folder (str): Name of the folder wayback-machine-downloader was pointed at (also
            the URL-path fragment substituted back into exported links by
            :func:`wayback_machine_downloader_companion.finder.export_missing`).
        web_output (str): Name of the folder wayback-machine-downloader wrote its output into.
            Defaults to ``f"{web_folder}_output"`` when omitted from ``config.json``.
        base_dir (pathlib.Path): Directory ``config.json`` lives in; every relative path is
            resolved against it. Not read from JSON -- injected by :meth:`load` from the config
            file's parent directory.
    """

    web_folder: str
    web_output: str
    base_dir: pathlib.Path = dataclasses.field(default_factory=pathlib.Path.cwd)

    @property
    def folder_output(self) -> pathlib.Path:
        """pathlib.Path: Absolute path to the folder holding downloaded website content."""
        return self.base_dir / self.web_output

    @property
    def folder_snapshots(self) -> pathlib.Path:
        """pathlib.Path: Absolute path to the folder holding versioned wayback snapshots."""
        return self.base_dir / self.web_folder

    @classmethod
    def load(cls, config_path: pathlib.Path) -> 'AppConfig':
        """Loads and validates configuration from a JSON file.

        Args:
            config_path (pathlib.Path): Path to a ``config.json`` file.

        Returns:
            AppConfig: The parsed and validated configuration.

        Raises:
            FileNotFoundError: ``config_path`` does not exist.
            ConfigError: The file is not valid JSON, is not a JSON object, or is missing/has an
                invalid ``WEB_FOLDER``/``WEB_OUTPUT``.
        """
        if not config_path.exists():
            raise FileNotFoundError(f'Config file not found: {config_path}')

        try:
            raw = json.loads(config_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as error:
            raise ConfigError(f'Invalid JSON in {config_path}: {error}') from error

        if not isinstance(raw, dict):
            raise ConfigError(f'{config_path} must contain a JSON object')

        web_folder = raw.get('WEB_FOLDER')
        if not isinstance(web_folder, str) or not web_folder.strip():
            raise ConfigError(f'{config_path}: "WEB_FOLDER" must be a non-empty string')

        web_output = raw.get('WEB_OUTPUT')
        if web_output is None:
            web_output = f'{web_folder}_output'
        elif not isinstance(web_output, str) or not web_output.strip():
            raise ConfigError(f'{config_path}: "WEB_OUTPUT" must be a non-empty string when provided')

        return cls(web_folder=web_folder, web_output=web_output, base_dir=config_path.resolve().parent)
