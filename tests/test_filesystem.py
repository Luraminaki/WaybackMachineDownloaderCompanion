"""Tests for wayback_machine_downloader_companion._filesystem."""

import os
import pathlib
import sys
from typing import TYPE_CHECKING

import pytest

from wayback_machine_downloader_companion._filesystem import (
    fold_key,
    is_case_insensitive,
    replace_atomically,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


def simulate_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``Path.exists`` and ``Path.samefile`` ignore case, as on macOS or Windows.

    Args:
        monkeypatch: Replaces both methods.
    """
    real_exists = pathlib.Path.exists

    def exists(self: pathlib.Path) -> bool:
        """Tell whether a file of that name exists, whatever its case.

        Args:
            self: The path asked for.

        Returns:
            Whether its folder holds a name equal to it but for case.
        """
        folder = self.parent
        wanted = self.name.lower()
        return real_exists(folder) and any(p.name.lower() == wanted for p in folder.iterdir())

    def samefile(self: pathlib.Path, other: pathlib.Path) -> bool:
        """Compare two paths whatever their case.

        Args:
            self: One path.
            other: The other.

        Returns:
            Whether they are equal but for case.
        """
        return str(self).lower() == str(other).lower()

    monkeypatch.setattr(pathlib.Path, "exists", exists)
    monkeypatch.setattr(pathlib.Path, "samefile", samefile)


def test_fold_key_lower_cases_only_when_folding() -> None:
    """Folding lower-cases; without it the text is unchanged."""
    assert fold_key("Dir/Page.HTML", fold_case=True) == "dir/page.html"
    assert fold_key("Dir/Page.HTML", fold_case=False) == "Dir/Page.HTML"


def test_fold_key_keeps_names_that_casefold_would_merge_apart() -> None:
    """Regression: `straße` and `strasse` are two files on NTFS and APFS, not one."""
    assert fold_key("straße.html", fold_case=True) != fold_key("strasse.html", fold_case=True)


def test_probe_is_true_when_the_swapped_name_is_the_same_file(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Page.html` found again as `pAGE.HTML`: the filesystem ignores case."""
    page = tmp_path / "Page.html"
    page.touch()
    simulate_case_insensitive(monkeypatch)

    assert is_case_insensitive([page]) is True


def test_probe_is_false_on_this_case_sensitive_filesystem(tmp_path: pathlib.Path) -> None:
    """Two real files differing only by case are two files: case matters."""
    lower, upper = tmp_path / "page.html", tmp_path / "PAGE.HTML"
    lower.touch()
    upper.touch()
    if len(list(tmp_path.iterdir())) == 1:
        pytest.skip("this filesystem ignores case")

    assert is_case_insensitive([lower]) is False


def test_probe_without_a_usable_name_assumes_case_matters(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No entry, or only names without ASCII letters (`20240101000000`, `ß`): ``False``."""
    simulate_case_insensitive(monkeypatch)
    digits, sharp_s = tmp_path / "20240101000000", tmp_path / "ß"
    digits.mkdir()
    sharp_s.touch()

    assert is_case_insensitive([]) is False
    assert is_case_insensitive([digits, sharp_s]) is False


def test_probe_reads_entries_only_up_to_the_first_usable_one(tmp_path: pathlib.Path) -> None:
    """A lazy listing is not read past the entry the probe uses."""
    read: list[str] = []
    names = ("2024", "page.html", "never-read.html")

    def entries() -> "Iterator[pathlib.Path]":
        """Yield the entries, recording each one read.

        Yields:
            Each entry in turn.
        """
        for name in names:
            read.append(name)
            yield tmp_path / name

    _ = is_case_insensitive(entries())

    assert read == ["2024", "page.html"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX folder permissions")
def test_probe_works_in_a_read_only_folder(tmp_path: pathlib.Path) -> None:
    """Regression: the probe created a temporary file, so a read-only folder made it fail."""
    if os.geteuid() == 0:
        pytest.skip("root writes into read-only folders")
    (tmp_path / "Page.html").touch()
    tmp_path.chmod(0o555)
    try:
        answer = is_case_insensitive(tmp_path.iterdir())
    finally:
        tmp_path.chmod(0o755)

    assert answer is False  # this suite's Linux tmp_path: case matters


def test_atomic_write_never_replaces_an_existing_temporary_name(tmp_path: pathlib.Path) -> None:
    """Regression: the fixed `.wmdc-<pid>.tmp` name overwrote, then moved, a real file."""
    taken = [tmp_path / f".wmdc-{name}.tmp" for name in (os.getpid(), "a", "b")]
    for path in taken:
        _ = path.write_text("mine", encoding="utf-8")

    replace_atomically(tmp_path / "page.htm", lambda t: t.write_text("page", encoding="utf-8"))

    assert [path.read_text(encoding="utf-8") for path in taken] == ["mine"] * 3
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(
        [path.name for path in taken] + ["page.htm"]
    )


def test_atomic_write_that_fails_removes_its_temporary_file(tmp_path: pathlib.Path) -> None:
    """A write that raises leaves neither the destination nor a temporary file."""

    def fail(_temporary: pathlib.Path) -> None:
        """Fail like an interrupted write.

        Args:
            _temporary: Ignored.

        Raises:
            KeyboardInterrupt: Always (not an ``Exception``: cleanup must still happen).
        """
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        replace_atomically(tmp_path / "page.htm", fail)

    assert list(tmp_path.iterdir()) == []
