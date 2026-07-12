# Changelog

All notable changes to this project are documented here. Versioning loosely follows
[Semantic Versioning](https://semver.org/).

The current version lives in [pyproject.toml](pyproject.toml) and is the single source of
truth -- `wayback_machine_downloader_companion.__version__` reads it at runtime instead of
duplicating it.

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
