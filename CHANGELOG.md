# Changelog

All notable changes to this project are documented here. Versioning loosely follows
[Semantic Versioning](https://semver.org/).

The current version lives in [pyproject.toml](pyproject.toml) and is the single source of
truth -- `wayback_machine_downloader_companion.__version__` reads it at runtime instead of
duplicating it.

## 0.4.0 - 2026-11-27

### Fixed

- Merge no longer crashes when one snapshot has a file where another has a folder (or the
  reverse): the newest snapshot's path wins and the older one is skipped with a warning. A file
  whose folder is blocked by a file already in `WEB_OUTPUT` is skipped the same way.
- Merge no longer fails on very long file names (e.g. 250 bytes): each file is written to a
  new, short-named `.wmdc-<random>.tmp` file (created exclusively, so a file of the same name
  is never overwritten) instead of a name derived from the file's.
- The merge manifest is written atomically, and saved even when a copy fails midway, so the
  next merge still recognises the files already written. A manifest, or a record in it, that
  isn't a JSON object gives a warning instead of a crash (existing files are kept as is).
- A `.wmdc-merge.json` at the root of a snapshot is no longer copied over the output's own.
- `wmdc-find` no longer counts the merge manifest as a site resource. An output holding no
  site file (only a leftover `.wmdc-*.tmp`, or files of other types) is "nothing to scan",
  so `wmdc --mode full` no longer reports success on it.
- `wmdc-find` writes nothing in `WEB_OUTPUT`: a read-only output is scanned instead of failing
  with "Unhandled error".
- On Windows, missing local files were exported as raw `C:/...` paths instead of Wayback
  URLs.
- A link to the site root was exported as `https://<host>/.`; it is now `https://<host>/`.
- A UTF-8 byte order mark at the start of a page or of `config.json` (as Windows Notepad
  writes) is accepted.
- `wmdc --mode full` stopped with exit code 1 when downloaded pages revealed more missing
  files than they resolved: it now stops for "no progress" only when every URL missing before
  an iteration is still missing after its downloads (newly found URLs no longer count against
  it). Each iteration uses the URLs the scan exported instead of reading its files back.
- Log pruning deleted other commands' logs (`wmdc` matched `wmdc-merge-*` files), and crashed
  if another run deleted a log at the same time.
- `wmdc-download` runs the full path of `wayback_machine_downloader` (on Windows, RubyGems
  installs a `.bat` the bare name didn't start). When the tool can't be started at all, the
  run stops at once with one error naming it (exit code 1) instead of failing every
  remaining URL in turn, each after a 1 s pause.
- An unusable `logs/` folder gives a one-line error and exit code 1 instead of a traceback.
- A `missing_html.txt` / `missing_other.txt` that isn't UTF-8 (edited by hand) is one clear
  error, exit code 1.

### Changed

- A backslash in a link counts as `/` on every OS, as browsers read it (`images\logo.gif` is
  `images/logo.gif`).
- On a case-insensitive output filesystem (macOS and Windows defaults), `wmdc-find` matches
  links to local files whatever their case (links differing only by case are listed once), and
  the merge treats such names as one file, warning when it skips an older spelling. Case is
  folded as those filesystems do (simple lower case: `straße` and `strasse` stay two files),
  and detected without writing anything. The merge manifest keeps each file's own name, so an
  output moved to a filesystem that handles case differently still takes updates.
- Symlinks inside snapshots are skipped with a warning instead of being followed.
- The merge manifest is no longer rewritten when nothing was written, nor indented.
- Faster merge (6,905-file synthetic site, best of 3: fresh merge 0.430 s -> 0.242 s, re-run
  0.284 s -> 0.068 s, peak memory 33 MiB -> 30 MiB) and `wmdc-find` (3.19 s -> 2.37 s, same
  memory).

### Added

- Development: 400 tests (from 91), passing on Python 3.10, 3.12 and 3.13, including a guard
  that refuses network (`connect` and `connect_ex`) and unpatched subprocess calls, and
  convention tests (docstrings, imports, no string retyping a first-party module name, dead
  and duplicated code, radon complexity, module length).

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
