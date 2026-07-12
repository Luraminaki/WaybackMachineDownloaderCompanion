#!/usr/bin/env python3
"""Reset logging configuration to a clean slate."""

import logging
import logging.config


def reset_logging(conf: dict | None = None) -> None:
    """Resets logging.

    Removes any configured handlers and filters, then applies `conf` (if provided). Useful
    before (re)configuring logging, to avoid piling up duplicate handlers when a CLI entry
    point's setup runs more than once in the same process (e.g. across tests).

    Args:
        conf (dict | None, optional): A `logging.config.dictConfig`-compatible mapping. Defaults
            to None.
    """
    root = logging.getLogger()
    _ = list(map(root.removeHandler, root.handlers[:]))
    _ = list(map(root.removeFilter, root.filters[:]))

    if conf is not None:
        logging.config.dictConfig(conf)
