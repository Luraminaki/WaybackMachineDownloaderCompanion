"""Tests for how wayback_machine_downloader_companion.merger handles case in file names."""

import argparse
import json
import logging
from typing import TYPE_CHECKING

import pytest

from tests.merger_helpers import NEWER_SNAPSHOT, OLDER_SNAPSHOT, manifest, output, write_snapshot
from wayback_machine_downloader_companion import merger
from wayback_machine_downloader_companion._filesystem import is_case_insensitive
from wayback_machine_downloader_companion.merger import MANIFEST_FILE, build_merge_plan, run

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterable

    from tests.conftest import MakeConfig
    from wayback_machine_downloader_companion.config import AppConfig


def set_case_insensitive(monkeypatch: pytest.MonkeyPatch, answer: bool) -> None:
    """Script what the merger's case probe answers.

    Args:
        monkeypatch: Replaces ``merger.is_case_insensitive``.
        answer: ``True`` for an output that ignores case.
    """
    monkeypatch.setattr(merger, "is_case_insensitive", lambda _entries: answer)


# --- the plan ---


def test_case_folding_keeps_the_newest_spelling(make_config: "MakeConfig") -> None:
    """On a case-insensitive filesystem, `A.html` (newer) and `a.html` (older) are one file."""
    config = make_config()
    write_snapshot(config, OLDER_SNAPSHOT, {"a.html": "old"})
    write_snapshot(config, NEWER_SNAPSHOT, {"A.html": "new"})

    plan = build_merge_plan(config, fold_case=True)

    assert [(entry.relative, entry.snapshot) for entry in plan.entries] == [
        ("A.html", NEWER_SNAPSHOT)
    ]


def test_case_folding_keeps_names_only_casefold_would_merge(make_config: "MakeConfig") -> None:
    """Regression: `straße.html` and `strasse.html` merged into one (`str.casefold`)."""
    config = make_config()
    write_snapshot(config, NEWER_SNAPSHOT, {"straße.html": "sharp s"})
    write_snapshot(config, OLDER_SNAPSHOT, {"strasse.html": "double s"})

    plan = build_merge_plan(config, fold_case=True)

    assert sorted(entry.relative for entry in plan.entries) == ["strasse.html", "straße.html"]


def test_respelled_older_file_dropped_by_folding_is_logged(
    make_config: "MakeConfig", caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: an older `a.html` lost to a newer `A.html` was dropped silently."""
    config = make_config()
    write_snapshot(config, OLDER_SNAPSHOT, {"a.html": "old"})
    write_snapshot(config, NEWER_SNAPSHOT, {"A.html": "new"})

    with caplog.at_level(logging.WARNING, logger=merger.logger.name):
        _ = build_merge_plan(config, fold_case=True)

    assert "a newer snapshot has A.html, the same file on a case-insensitive output" in (
        caplog.text
    )


def test_older_version_of_the_same_spelling_is_skipped_quietly(
    make_config: "MakeConfig", caplog: pytest.LogCaptureFixture
) -> None:
    """The usual case, an older copy of a file, is no news: no warning per file."""
    config = make_config()
    write_snapshot(config, OLDER_SNAPSHOT, {"a.html": "old"})
    write_snapshot(config, NEWER_SNAPSHOT, {"a.html": "new"})

    with caplog.at_level(logging.WARNING, logger=merger.logger.name):
        _ = build_merge_plan(config, fold_case=True)

    assert caplog.records == []


# --- the probe ---


def test_merge_probes_the_output_then_the_snapshots(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty output is probed through the snapshots' entries; a merged one, its own."""
    probed: list[pathlib.Path] = []

    def probe(entries: "Iterable[pathlib.Path]") -> bool:
        """Record the folder of the first entry offered to the probe.

        Args:
            entries: The entries, the first one recorded.

        Returns:
            ``False``.
        """
        probed.append(next(iter(entries)).parent)
        return False

    monkeypatch.setattr(merger, "is_case_insensitive", probe)
    config = make_config()
    write_snapshot(config, NEWER_SNAPSHOT, {"Page.html": "page"})

    for _ in range(2):
        assert run(config, argparse.Namespace()) == 0

    assert probed == [config.folder_snapshots / NEWER_SNAPSHOT, config.folder_output]


# --- the manifest ---


def merge_then_respell(config: "AppConfig") -> None:
    """Merge `a.html` from the older snapshot, then the newer snapshot's `A.html`.

    Args:
        config: The active configuration.
    """
    for timestamp, name, content in (
        (OLDER_SNAPSHOT, "a.html", "old"),
        (NEWER_SNAPSHOT, "A.html", "new"),
    ):
        write_snapshot(config, timestamp, {name: content})
        assert run(config, argparse.Namespace()) == 0


def test_respelled_newer_snapshot_leaves_one_record_under_its_spelling(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: on a case-insensitive output, `A.html` got a second record next to `a.html`.

    The one record left is under the spelling written last, not a folded key.
    """
    set_case_insensitive(monkeypatch, True)
    config = make_config()

    merge_then_respell(config)

    assert {key: record["snapshot"] for key, record in manifest(config).items()} == {
        "A.html": NEWER_SNAPSHOT
    }


def test_manifest_keeps_the_original_spelling_on_a_case_insensitive_output(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: keys were stored case-folded (`page.html` for `Page.html`)."""
    set_case_insensitive(monkeypatch, True)
    config = make_config()
    write_snapshot(config, OLDER_SNAPSHOT, {"Dir/Page.html": "old"})

    assert run(config, argparse.Namespace()) == 0

    assert list(manifest(config)) == ["Dir/Page.html"]


def test_output_moved_to_a_case_sensitive_filesystem_still_takes_updates(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: folded keys no longer matched `Page.html`, which then never updated."""
    config = make_config()
    write_snapshot(config, OLDER_SNAPSHOT, {"Page.html": "old"})
    set_case_insensitive(monkeypatch, True)
    assert run(config, argparse.Namespace()) == 0
    write_snapshot(config, NEWER_SNAPSHOT, {"Page.html": "new"})
    set_case_insensitive(monkeypatch, False)

    assert run(config, argparse.Namespace()) == 0

    assert output(config, "Page.html") == "new"


def test_manifest_with_folded_keys_from_an_older_build_still_matches(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """A manifest whose keys were folded (`page.html`) still recognises `Page.html`.

    The rewritten record takes the file's own spelling, and the folded one goes.
    """
    set_case_insensitive(monkeypatch, True)
    config = make_config()
    write_snapshot(config, OLDER_SNAPSHOT, {"Page.html": "old"})
    assert run(config, argparse.Namespace()) == 0
    path = config.folder_output / MANIFEST_FILE
    _ = path.write_text(json.dumps({"page.html": manifest(config)["Page.html"]}), "utf-8")
    write_snapshot(config, NEWER_SNAPSHOT, {"Page.html": "new"})

    assert run(config, argparse.Namespace()) == 0

    assert output(config, "Page.html") == "new"
    assert list(manifest(config)) == ["Page.html"]


def test_case_sensitive_manifest_is_looked_up_whatever_the_case(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record written as `Page.html` matches `page.html` once the output ignores case."""
    config = make_config()
    write_snapshot(config, OLDER_SNAPSHOT, {"Page.html": "old"})
    set_case_insensitive(monkeypatch, False)
    assert run(config, argparse.Namespace()) == 0
    write_snapshot(config, NEWER_SNAPSHOT, {"page.html": "new"})
    set_case_insensitive(monkeypatch, True)

    assert run(config, argparse.Namespace()) == 0

    assert list(manifest(config)) == ["page.html"]


def test_case_sensitive_output_keeps_both_spellings(
    make_config: "MakeConfig", monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without case folding (Linux), `a.html` and `A.html` stay two files and two records."""
    set_case_insensitive(monkeypatch, False)
    config = make_config()
    write_snapshot(config, OLDER_SNAPSHOT, {"a.html": "old"})
    write_snapshot(config, NEWER_SNAPSHOT, {"A.html": "new"})

    assert run(config, argparse.Namespace()) == 0

    assert output(config, "a.html") == "old"
    assert output(config, "A.html") == "new"
    assert sorted(manifest(config)) == ["A.html", "a.html"]


def test_respelled_newer_snapshot_updates_a_case_insensitive_output(
    make_config: "MakeConfig", tmp_path: "pathlib.Path"
) -> None:
    """On a real case-insensitive filesystem, `A.html` (newer) replaces the merged `a.html`."""
    config = make_config()  # writes tmp_path/config.json: an entry to probe
    if not is_case_insensitive(tmp_path.iterdir()):
        pytest.skip("needs a case-insensitive filesystem (macOS, Windows defaults)")

    merge_then_respell(config)

    assert output(config, "a.html") == "new"
