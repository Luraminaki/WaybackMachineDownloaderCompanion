"""Shared pytest fixtures for the WMDC test suite."""

import json
import logging
import socket
import subprocess
import time
from typing import TYPE_CHECKING, Protocol

import pytest

from wayback_machine_downloader_companion.config import AppConfig

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator

# Unix sockets are local IPC, not network: they may still connect. Absent on Windows.
_LOCAL_FAMILIES: tuple[int, ...] = (socket.AF_UNIX,) if hasattr(socket, "AF_UNIX") else ()


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
        """Write a config.json and load it.

        Args:
            web_folder: The WEB_FOLDER setting.
            web_output: The WEB_OUTPUT setting, omitted if `None`.

        Returns:
            The loaded configuration.
        """
        payload = {"WEB_FOLDER": web_folder}
        if web_output is not None:
            payload["WEB_OUTPUT"] = web_output

        config_path = tmp_path / "config.json"
        _ = config_path.write_text(json.dumps(payload), encoding="utf-8")
        return AppConfig.load(config_path)

    return _make


@pytest.fixture(name="no_network", autouse=True)
def fixture_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any network connection fail loudly: the tests must never reach the network.

    Local (Unix) sockets still connect.

    Args:
        monkeypatch: Replaces ``socket.socket.connect`` and ``socket.socket.connect_ex``.
    """
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def _check_local(sock: socket.socket, address: "tuple[object, ...] | str | bytes") -> None:
        """Refuse a network address.

        Args:
            sock: The socket being connected.
            address: Where to.

        Raises:
            RuntimeError: For a network socket (not an ``OSError``, which code under test may
                catch and carry on: the test must fail, not quietly go on).
        """
        if sock.family not in _LOCAL_FAMILIES:
            raise RuntimeError(f"tests must not use the network (tried to connect to {address!r})")

    def _refuse_network(sock: socket.socket, address: "tuple[object, ...] | str | bytes") -> None:
        """Connect a local socket; refuse anything else (see :func:`_check_local`).

        Args:
            sock: The socket being connected.
            address: Where to.
        """
        _check_local(sock, address)
        real_connect(sock, address)

    def _refuse_network_ex(sock: socket.socket, address: "tuple[object, ...] | str | bytes") -> int:
        """Connect a local socket, returning an error code; refuse anything else.

        Args:
            sock: The socket being connected.
            address: Where to.

        Returns:
            What the real ``connect_ex`` returns.
        """
        _check_local(sock, address)
        return real_connect_ex(sock, address)

    monkeypatch.setattr(socket.socket, "connect", _refuse_network)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse_network_ex)


@pytest.fixture(name="no_subprocess", autouse=True)
def fixture_no_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any real ``subprocess.run``/``Popen`` fail loudly: a test must patch what it runs.

    A test that patches ``subprocess.run`` itself replaces this guard for its own duration.

    Args:
        monkeypatch: Replaces ``subprocess.run`` and ``subprocess.Popen``.
    """

    def _refuse_subprocess(command: object, *_args: object, **_kwargs: object) -> None:
        """Refuse to start a process.

        Args:
            command: What the code tried to run.
            *_args: Ignored.
            **_kwargs: Ignored.

        Raises:
            RuntimeError: Always (not an ``OSError``, which code under test catches).
        """
        raise RuntimeError(f"tests must not start real processes (tried to run {command!r})")

    monkeypatch.setattr(subprocess, "run", _refuse_subprocess)
    monkeypatch.setattr(subprocess, "Popen", _refuse_subprocess)


@pytest.fixture(name="no_sleep")
def fixture_no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record the pauses asked of ``time.sleep`` instead of sleeping.

    Args:
        monkeypatch: Replaces ``time.sleep``.

    Returns:
        The pauses requested, in seconds, in order.
    """
    pauses: list[float] = []
    monkeypatch.setattr(time, "sleep", pauses.append)
    return pauses


@pytest.fixture(name="can_symlink")
def fixture_can_symlink(tmp_path: "pathlib.Path") -> None:
    """Skip the test where symlinks can't be created (Windows without the privilege).

    Args:
        tmp_path: Pytest's per-test temporary directory.
    """
    probe = tmp_path / "symlink-probe"
    try:
        probe.symlink_to(tmp_path, target_is_directory=True)
    except OSError as error:  # creating symlinks is an OS privilege, not ours to check
        pytest.skip(f"symlinks unavailable: {error}")
    probe.unlink()


@pytest.fixture(name="restore_root_logger")
def fixture_restore_root_logger() -> "Iterator[None]":
    """Put the root logger's handlers and level back after a test that configures logging.

    ``configure_logging`` calls ``logging.basicConfig(force=True)``, which replaces the root
    handlers (pytest's capture handlers included); the handlers it added are closed here, so
    no log file stays open.

    Yields:
        Nothing: the test runs in between.
    """
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    yield
    for handler in root.handlers:
        if handler not in saved_handlers:
            handler.close()
    root.handlers = saved_handlers
    root.setLevel(saved_level)
