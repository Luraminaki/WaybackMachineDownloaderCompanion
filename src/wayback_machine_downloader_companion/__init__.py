"""Companion CLI tools for wayback-machine-downloader (the maintained StrawberryMaster fork)."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("wayback-machine-downloader-companion")
except PackageNotFoundError:
    __version__ = "unknown"
