# WAYBACK-MACHINE-DOWNLOADER-COMPANION

Python 3 scripts that complement the [wayback-machine-downloader](https://github.com/StrawberryMaster/wayback-machine-downloader) software output -- a maintained fork of the original [hartator/wayback-machine-downloader](https://github.com/hartator/wayback-machine-downloader), which looks unmaintained these days.

I made these following scripts at one of my dearest friend's request.
For a bit of context, an (arguably) old website has been decommissioned fairly recently (09/2023 ~ 10/2023), and all its content (as it turned out, 'most' is a better word in that case) can now only be found on the famous [Wayback Machine - Internet Archive](https://archive.org/web/).
This is a good thing because its content still exists (mostly), but somewhat worrying as we don't know for how long, and pretty annoying because browsing through the [Wayback Machine - Internet Archive](https://archive.org/web/) is a slow process (some request give an answer only after 5 seconds or more).

With the use of [wayback-machine-downloader](https://github.com/StrawberryMaster/wayback-machine-downloader), I was able to download what turned out to be about 7% of the whole website with this software alone.
Since [wayback-machine-downloader](https://github.com/StrawberryMaster/wayback-machine-downloader) allows the download of single **URL**, I made the following scripts that helped me with finding all the **URLs** that were 'locally' missing, and fed them to [wayback-machine-downloader](https://github.com/StrawberryMaster/wayback-machine-downloader) to download said missing files. (I had to repeat this process a couple of times).

## VERSION

The current version lives in [pyproject.toml](pyproject.toml). See [CHANGELOG.md](CHANGELOG.md)
for the full version history.

## TABLE OF CONTENT

<!-- TOC -->

- [WAYBACK-MACHINE-DOWNLOADER-COMPANION](#wayback-machine-downloader-companion)
  - [VERSION](#version)
  - [TABLE OF CONTENT](#table-of-content)
  - [INSTALL GUIDE](#install-guide)
  - [START GUIDE](#start-guide)
    - [WORKING DIRECTORY LAYOUT](#working-directory-layout)
    - [RUNNING](#running)
    - [CASE 01](#case-01)
    - [CASE 02](#case-02)
  - [DEVELOPMENT](#development)
  - [WARNINGS](#warnings)

<!-- /TOC -->

## INSTALL GUIDE

See [INSTALL.md](INSTALL.md) for platform-specific setup instructions.

You will also need the [wayback-machine-downloader](https://github.com/StrawberryMaster/wayback-machine-downloader) Ruby gem installed (`gem install wayback_machine_downloader_straw` -- the executable is still called `wayback_machine_downloader`) -- this project only finds and orchestrates missing resources, it doesn't talk to the Wayback Machine itself.

This package has no Python runtime dependencies -- only the standard library.

## START GUIDE

### WORKING DIRECTORY LAYOUT

Open a terminal / command prompt in a working directory and run [wayback-machine-downloader](https://github.com/StrawberryMaster/wayback-machine-downloader) there (see [CASE 01](#case-01) and [CASE 02](#case-02) for the command line).
It creates a `websites/` folder holding one `<host>/` folder per downloaded site.

Put your `config.json` **inside that `websites/` folder** (next to `<host>/`, see [config.json](config.json) for the shape), then run the `wmdc*` commands from `websites/` -- or from the working directory with `-c websites/config.json`.
Once everything has run, it looks like this:

```text
workdir/
├── websites/
│   ├── config.json
│   ├── example.com/            <- WEB_FOLDER, created by wayback-machine-downloader
│   ├── example.com_output/     <- WEB_OUTPUT (merged and downloaded files)
│   ├── missing_html.txt
│   ├── missing_other.txt
│   └── unspecified.txt
└── logs/                       <- in the directory you ran the commands from
```

`config.json` has two keys:

| Key | Required | Meaning |
| --- | --- | --- |
| `WEB_FOLDER` | yes | The `<host>` folder wayback-machine-downloader created (e.g. `example.com`). It is also the host put back into the URLs to download. |
| `WEB_OUTPUT` | no | The folder that is scanned for missing files and receives the downloads (and the merge). Defaults to `<WEB_FOLDER>_output`, which suits a `-s` download ([CASE 02](#case-02)). For a plain download ([CASE 01](#case-01)), set it to the same value as `WEB_FOLDER` (no merge then). |

Both must be plain folder names next to `config.json` (no `/`, `.` or `..`) -- anything else is refused.

### RUNNING

Once resources have been downloaded, the simplest way to run everything is the launcher:

```sh
wmdc
```

It shows a menu: `1`-`4` run a step (full run / merge / find / download), `5` quits (exit code 0), and any other choice exits with code 1.
For scripting, pass `--mode` instead of using the menu.

| Option | Commands | Meaning |
| --- | --- | --- |
| `-c`, `--configuration PATH` | all | Path to `config.json` (default: `./config.json`). |
| `-v`, `--verbose` | all | Debug logging (default: info). |
| `--mode {full,merge,find,download}` | `wmdc` | Run one step (or the full sequence) without the menu, e.g. `wmdc --mode full`. |
| `--force-merge` | `wmdc` | Always merge first in full mode, even if no snapshot folder looks versioned. |
| `--max-iterations N` | `wmdc` | Maximum find/download loops in full mode (default: 10, must be >= 1). |

The full run merges first if `WEB_FOLDER` holds versioned (`-s`) snapshot folders (this detection only happens in full mode), then loops find -> download until nothing is missing.
It also stops (exit code 1) when an iteration makes no progress (every URL missing before the last downloads is still missing -- newly found ones don't count), or after `--max-iterations` loops.

Each step is also its own command: `wmdc-merge`, `wmdc-find`, `wmdc-download`.

- `wmdc-merge` copies the most recent version of every file of the `-s` snapshot folders into `WEB_OUTPUT`. It never deletes anything, and re-running it is safe: a file is only replaced by a newer snapshot, and only if it is unchanged since the last merge, so later downloads and manual edits survive (it keeps track in a `.wmdc-merge.json` file in `WEB_OUTPUT`). It refuses to run when `WEB_OUTPUT` and `WEB_FOLDER` are the same folder or nested in each other.
  - When the newest snapshot has a file where an older one has a folder (or the reverse), the newest wins and the older path is skipped with a warning; so is a file whose folder is blocked by a file already in `WEB_OUTPUT`.
  - Symlinks inside snapshots are skipped with a warning, never followed.
  - On a case-insensitive filesystem (the macOS and Windows defaults), names differing only by case (`A.html`, `a.html`) are one file: the newest snapshot's wins, and the older one is skipped with a warning. Only simple upper/lower case counts, as those filesystems compare it: `straße.html` and `strasse.html` stay two files. `.wmdc-merge.json` records each file under its own name, so the output can move to a filesystem that handles case differently. The case handling is detected without writing anything, from names already in `WEB_OUTPUT` (or in the snapshots when it is empty).
  - Each file is written to a new `.wmdc-<random>.tmp` file next to it, then renamed; an existing file is never used as the temporary one.
- `wmdc-find` parses every downloaded HTML page in `WEB_OUTPUT` and writes the missing resources, as URLs, next to `config.json`:
  - `missing_html.txt` -- missing pages (`.htm`, `.html`);
  - `missing_other.txt` -- missing resources with a known extension (images, CSS, JS, fonts, PDF...);
  - `unspecified.txt` -- external links and links with an unknown extension. **It is never downloaded automatically**: check it by hand. Links that leave the site folder (e.g. too many `../`) are listed there too, as written in the page.

  A backslash in a link counts as `/` on every OS, as browsers read it (`images\logo.gif` is `images/logo.gif`). On a case-insensitive filesystem, a link matches its local file whatever the case of either, and links differing only by case are listed once. Only site files (the extensions above) count: a `WEB_OUTPUT` holding none of them has nothing to scan (exit code 1). The scan writes nothing in `WEB_OUTPUT`, which may be read-only.
- `wmdc-download` feeds every URL of `missing_html.txt` and `missing_other.txt` (each one once) to `wayback_machine_downloader -e -d <WEB_OUTPUT>`, so the files land where `wmdc-find` looks, with a 1 s pause between downloads and a 600 s timeout per URL. A download counts as successful only if the tool exits with code 0, reports `Download finished` and no `Download completed with errors`. The tool retries failed requests itself. If `wayback_machine_downloader` can't be started at all (not executable, a broken `.bat`), the run stops at the first URL with one error naming it, instead of failing every URL in turn. On Windows, RubyGems installs the tool as a `.bat`, which `cmd.exe` runs and parses again: a URL holding `%NAME%`, where `NAME` is an environment variable, can reach the tool altered.

Logs go to `logs/<command>-<pid>.log` under the directory you ran the command from; only the 20 most recent log files of each command are kept. If `logs/` can't be created or written, the command prints a one-line error and exits with code 1.

### CASE 01

Assuming you ran [wayback-machine-downloader](https://github.com/StrawberryMaster/wayback-machine-downloader) with the following basic command line in your working directory:

```sh
wayback_machine_downloader http://example.com
```

- Create `websites/config.json` with `WEB_OUTPUT` set to the same value as `WEB_FOLDER`:

```json
{
    "WEB_FOLDER": "example.com",
    "WEB_OUTPUT": "example.com"
}
```

- From `websites/`, run the following commands until there is nothing else found to download (or just run `wmdc --mode full`, which loops this for you)

```sh
wmdc-find
```

```sh
wmdc-download
```

### CASE 02

If you ran [wayback-machine-downloader](https://github.com/StrawberryMaster/wayback-machine-downloader) with the following command line in your working directory:

```sh
wayback_machine_downloader http://example.com -s
```

- Create `websites/config.json` with only `WEB_FOLDER` (`WEB_OUTPUT` defaults to `example.com_output`):

```json
{
    "WEB_FOLDER": "example.com"
}
```

- From `websites/`, run the following command, and then run `wmdc-find` / `wmdc-download` as in [CASE 01](#case-01) (or just run `wmdc --mode full`, which merges first on its own)

```sh
wmdc-merge
```

## DEVELOPMENT

Linting, type checking, and the test suite are covered in [INSTALL.md](INSTALL.md#optional-development-tools).

## WARNINGS

- Some websites are fairly old, and their 'textual' content may not have been saved with `utf-8` encoding... `wmdc-find` reads such pages anyway (UTF-8 first, then cp1252, then Latin-1), but a page in another encoding may still show some strange characters, and links with such characters in them may not match their local files.
- Where `wayback_machine_downloader -e -d <WEB_OUTPUT> <url>` saves a file (`<WEB_OUTPUT>/<url path>`) was read from the fork's source code, not checked with a real download.
- These scripts 'just worked' for me (albeit with a few tweaks here and there)... So it may not be 100% tailored to your own needs.
- If you already have hartator's original `wayback_machine_downloader` gem installed, the fork's own docs warn it may conflict with it -- you might need to uninstall the original first.

Best of luck, and I hope this helped.
