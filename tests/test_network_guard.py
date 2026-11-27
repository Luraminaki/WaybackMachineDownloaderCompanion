"""Tests for the autouse guards in conftest: no network, no real processes."""

import pathlib
import shutil
import socket
import subprocess
import tempfile
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(name="short_folder")
def fixture_short_folder() -> "Iterator[pathlib.Path]":
    """Give a folder with a short path, removed afterwards.

    A Unix socket path must fit ``sun_path`` (104 bytes on macOS); pytest's ``tmp_path`` there
    is longer than that.

    Yields:
        The folder, under ``/tmp``.
    """
    folder = pathlib.Path(tempfile.mkdtemp(prefix="wmdc-", dir="/tmp"))
    yield folder
    shutil.rmtree(folder)


@pytest.mark.parametrize("method", ["connect", "connect_ex"])
def test_network_connection_is_refused(method: str) -> None:
    """An internet socket can't connect, and the refusal isn't an OSError code could swallow.

    ``connect_ex`` too: it returns an error code instead of raising, and used to get through.
    """
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock,
        pytest.raises(RuntimeError, match="must not use the network"),
    ):
        _ = getattr(sock, method)(("127.0.0.1", 9))


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="no Unix sockets on this platform")
def test_unix_socket_still_connects(short_folder: pathlib.Path) -> None:
    """Local IPC isn't network: a Unix socket connects through the guard."""
    address = str(short_folder / "s")
    with (
        socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server,
        socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client,
    ):
        server.bind(address)
        server.listen(1)

        client.connect(address)

        assert client.getpeername() == address


def test_unpatched_subprocess_run_is_refused() -> None:
    """A real process can't start through ``subprocess.run``."""
    with pytest.raises(RuntimeError, match="must not start real processes"):
        _ = subprocess.run(["true"], check=False)


def test_unpatched_popen_is_refused() -> None:
    """A real process can't start through ``subprocess.Popen`` either."""
    with pytest.raises(RuntimeError, match="must not start real processes"):
        _ = subprocess.Popen(["true"])  # pylint: disable=consider-using-with  # never starts


def test_a_tests_own_patch_replaces_the_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patching ``subprocess.run`` in a test wins over the guard."""
    done = subprocess.CompletedProcess(["fake"], 0)
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: done)

    assert subprocess.run(["fake"], check=False) is done
