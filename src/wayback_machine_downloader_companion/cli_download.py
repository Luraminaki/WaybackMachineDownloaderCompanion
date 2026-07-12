#!/usr/bin/env python3
"""Console-script entry point: download every resource listed as missing."""

import sys

from wayback_machine_downloader_companion import _cli, downloader


def cli() -> None:
    """Runs ``wmdc-download`` and exits with its return code."""
    sys.exit(_cli.main(
        'wmdc-download', 'Download every resource listed in the missing-resource files.', downloader.run,
    ))


if __name__ == '__main__':
    cli()
