#!/usr/bin/env python3
"""Console-script entry point: find missing resources referenced in downloaded HTML."""

import sys

from wayback_machine_downloader_companion import _cli, finder


def cli() -> None:
    """Runs ``wmdc-find`` and exits with its return code."""
    sys.exit(_cli.main('wmdc-find', 'Find missing resources referenced in downloaded HTML.', finder.run))


if __name__ == '__main__':
    cli()
