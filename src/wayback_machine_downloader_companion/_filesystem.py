#!/usr/bin/env python3
"""Filesystem helpers: how names compare (the one place deciding case handling), atomic writes.

Case-insensitive filesystems (the macOS and Windows defaults) fold case one character at a
time (``A`` and ``a`` are one name), not the way :meth:`str.casefold` does: ``straße`` and
``strasse`` are two files there. So names are folded with :meth:`str.lower`, which never
changes a name's length, and never with :meth:`str.casefold`.
"""

import logging
import os
import pathlib
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

logger = logging.getLogger(__name__)


def fold_key(text: str, fold_case: bool) -> str:
    """Gives the key a name is compared by.

    Args:
        text (str): A file name or a relative path.
        fold_case (bool): The filesystem ignores case.

    Returns:
        str: ``text`` lower-cased if ``fold_case``, unchanged otherwise.
    """
    return text.lower() if fold_case else text


def _probe_name(name: str) -> bool:
    """Tells whether a name can reveal the filesystem's case handling.

    Only ASCII letters are folded alike by every case-insensitive filesystem, and their
    swapped case swaps back to the same name (``"ß".swapcase()`` is ``"SS"``).

    Args:
        name (str): An entry's name.

    Returns:
        bool: ``True`` if the name is ASCII and has at least one letter.
    """
    return name.isascii() and name.lower() != name.upper()


def is_case_insensitive(entries: "Iterable[pathlib.Path]") -> bool:
    """Tells whether existing entries live on a filesystem that ignores case.

    Read-only: it looks up the first usable entry under its swapped case (``Page.html`` as
    ``pAGE.HTML``) and writes nothing, so it works on a read-only folder. Only entries up to
    the first usable one are read from ``entries``.

    Args:
        entries (Iterable[pathlib.Path]): Existing files or folders on the filesystem to probe.

    Returns:
        bool: ``True`` if the swapped name is the same entry; ``False`` if it isn't, or if no
        entry has an ASCII letter in its name (nothing to tell by: assume case matters).
    """
    probe = next((entry for entry in entries if _probe_name(entry.name)), None)
    if probe is None:
        logger.debug("No entry to probe the case sensitivity with: assuming case matters")
        return False
    swapped = probe.with_name(probe.name.swapcase())
    # On a case-sensitive filesystem the swapped name can be another, real file.
    return swapped.exists() and probe.samefile(swapped)


def replace_atomically(
    destination: "pathlib.Path", write: "Callable[[pathlib.Path], object]"
) -> None:
    """Writes a file through a temporary name, so the destination is never half-written.

    The temporary file is new (created exclusively, so it never replaces an existing file)
    and has a short name (``.wmdc-<random>.tmp``), whatever the destination's name: a name
    derived from it could exceed the filesystem's name length limit. It sits in the
    destination's folder, so the final rename stays atomic.

    Args:
        destination (pathlib.Path): Target path; its folder must exist.
        write (Callable[[pathlib.Path], object]): Writes the content to the path it is given.
    """
    descriptor, name = tempfile.mkstemp(dir=destination.parent, prefix=".wmdc-", suffix=".tmp")
    os.close(descriptor)  # `write` reopens it by path
    temporary = pathlib.Path(name)
    replaced = False
    try:
        _ = write(temporary)
        _ = temporary.replace(destination)
        replaced = True
    finally:
        if not replaced:  # whatever stopped the write, leave no temporary file behind
            temporary.unlink(missing_ok=True)
