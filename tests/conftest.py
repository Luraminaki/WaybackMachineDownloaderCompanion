"""Shared pytest fixtures for the WMDC test suite."""

import json
from typing import TYPE_CHECKING, Protocol

import pytest

from wayback_machine_downloader_companion.config import AppConfig

if TYPE_CHECKING:
    import pathlib


class MakeConfig(Protocol):
    """Signature of the `make_config` fixture."""

    def __call__(self, web_folder: str = ..., web_output: str | None = None) -> AppConfig:
        """Write a config.json and load it.

        Args:
            web_folder: The WEB_FOLDER setting.
            web_output: The WEB_OUTPUT setting, omitted if `None`.

        Returns:
            The loaded configuration.
        """
        ...


@pytest.fixture
def make_config(tmp_path: "pathlib.Path") -> MakeConfig:
    """Return a factory that writes a ``config.json`` under ``tmp_path`` and loads it.

    Args:
        tmp_path: Pytest's per-test temporary directory.

    Returns:
        A callable ``(web_folder, web_output=None) -> AppConfig``.
    """

    def _make(web_folder: str = "example.com", web_output: str | None = None) -> AppConfig:
        payload = {"WEB_FOLDER": web_folder}
        if web_output is not None:
            payload["WEB_OUTPUT"] = web_output

        config_path = tmp_path / "config.json"
        _ = config_path.write_text(json.dumps(payload), encoding="utf-8")
        return AppConfig.load(config_path)

    return _make
