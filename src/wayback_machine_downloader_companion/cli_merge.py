#!/usr/bin/env python3
"""Console-script entry point: merge versioned snapshot folders into a single output folder."""

import sys

from wayback_machine_downloader_companion import _cli, merger


def cli() -> None:
    """Runs ``wmdc-merge`` and exits with its return code."""
    sys.exit(_cli.main('wmdc-merge', 'Merge versioned wayback-machine-downloader snapshots.', merger.run))


if __name__ == '__main__':
    cli()
