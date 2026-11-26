# Changelog

All notable changes to this project are documented here. Versioning loosely follows
[Semantic Versioning](https://semver.org/).

The current version lives in [pyproject.toml](pyproject.toml) and is the single source of
truth -- `wayback_machine_downloader_companion.__version__` reads it at runtime instead of
duplicating it.

## 0.3.0 - 2026-11-26

### Fixed

- Merge no longer loses data: it used to delete the output folder before copying, which wiped
  the snapshots when `WEB_OUTPUT` equalled `WEB_FOLDER`, crashed on folders with a dot in their
  name, skipped extensionless files, and erased every download on each re-merge. It now never
  deletes anything and copies each file atomically (temporary file, then rename).
- Download success was read backwards (the fork prints "Download completed with errors" on
  failure): a download now succeeds only when the tool exits with code 0, prints
  "Download finished" and no error summary.
- Downloads were saved outside the folder `wmdc-find` scans, so `wmdc --mode full` could never
  finish: they are now saved with `-d <WEB_OUTPUT>`, as `<WEB_OUTPUT>/<url path>`.
- Downloads are no longer killed before the tool finishes; a 600 s timeout per URL replaces
  that. URLs with quotes or spaces no longer break the run; a URL listed twice is downloaded
  once; a missing `wayback_machine_downloader` is reported once.
- `wmdc-find` lost links when a page ended inside `<script>` or a cut tag (the parser state
  leaked into the next page): each page is now parsed on its own.
- Pages not in UTF-8 were skipped as corrupted: they are now decoded as UTF-8, then cp1252,
  then Latin-1.
- Percent-encoded links (`my%20page.htm`) now match their local files, and exported URLs are
  built from the path relative to `WEB_OUTPUT`, percent-encoded (a text replace could mangle
  paths containing the `WEB_OUTPUT` name).
- An unreadable `config.json` (e.g. a folder given to `-c`, or non-UTF-8 content) is a readable
  error instead of a traceback.
- An invalid choice in the `wmdc` menu exits with code 1 instead of 0; `5` quits with 0.
- `--max-iterations 0` is refused (it skipped the loop, then reported the limit as reached).

### Changed

- Now targets the maintained [StrawberryMaster fork](https://github.com/StrawberryMaster/wayback-machine-downloader)
  of wayback-machine-downloader (`gem install wayback_machine_downloader_straw`, same
  `wayback_machine_downloader` executable). The fork retries failed requests itself.
- Re-merging is safe: a manifest (`.wmdc-merge.json`, in `WEB_OUTPUT`) records where each
  merged file came from, and a file is replaced only by a newer snapshot and only if it is
  unchanged since the last merge, so downloaded files and manual edits survive. Names differing
  only by case are handled on case-insensitive filesystems (the newest snapshot wins).
- The merge refuses to run when `WEB_OUTPUT` and `WEB_FOLDER` are the same folder or nested.
- `WEB_FOLDER` and `WEB_OUTPUT` must be plain folder names (no `/`, `.` or `..`).
- Links leaving the site folder are no longer reported as missing local files: they are
  listed in `unspecified.txt`, as written in the page.
- `wmdc --mode full` stops when an iteration makes no progress instead of re-requesting the
  same URLs up to `--max-iterations` times.
- The 1 s pause between downloads no longer follows the last one.
- Log files are written to `logs/` (under the working directory), and only the 20 most recent
  per command are kept.
- `wmdc-find` is about 3.4x faster and lighter (2000-page synthetic site: 4.6 s instead of
  16.0 s, peak memory 12.2 MiB instead of 19.7 MiB).

### Added

- More link sources: `script`, `iframe`, `source`, `embed`, `area`, `input` `src`, `object`
  `data`, and `body`/`table`/`td`/`th` `background`.
- Development: `pylint`, `radon` and `vulture` in the `dev` extra; 100-char lines and
  basedpyright "recommended" mode; 90 tests, passing on Python 3.10, 3.12 and 3.13 (3.13
  classifier added).

### Removed

- The internal `logreset` module (`logging.basicConfig(force=True)` does the same).

## 0.2.0

- Restructured into an installable `src/` package (`pyproject.toml`, `pip install -e .`), with
  console scripts `wmdc`, `wmdc-merge`, `wmdc-find`, `wmdc-download` replacing the old flat
  scripts.
- Replaced dict/tuple-based data with dataclasses (`AppConfig`, `LinkReport`,
  `SortedResourceReport`, `MergePlan`, `FinderResult`).
- Added a menu-driven `wmdc` launcher that runs merge/find/download in sequence, looping until
  nothing is missing.
- Switched from `print()` to the standard `logging` module, with console output plus rotating
  per-process log files.
- Fixed several bugs: a crash when merging with no versioned snapshots, dead code in the
  missing-resource diff, `WBMHTMLParser` sharing state across instances, naive substring
  extension matching, `merge_snapshots.py`'s config being disconnected from `config.json`,
  non-`shlex` command splitting, Windows path separators leaking into exported URLs, query
  strings breaking missing-resource matching, two divergent definitions of "snapshot folder"
  between the merge step and the launcher, silent-by-default logging, and CLI exit codes that
  didn't reflect success or failure.
- Added a `pytest` suite (47 tests) and `ruff`/`basedpyright` linting.
- Rewrote `README.md` and added `INSTALL.md` (Windows / Debian / Ubuntu / Arch).

## 0.1.0-alpha

- First release.
