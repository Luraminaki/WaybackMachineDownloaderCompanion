"""Companion CLI tools for hartator/wayback-machine-downloader."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version('wayback-machine-downloader-companion')
except PackageNotFoundError:
    __version__ = 'unknown'
