# Install

## Prerequisites

- **Python 3.10+**. Get it from [python.org](https://www.python.org/downloads/) (Windows/macOS)
  or your distro's package manager (Linux).
- **The `wayback-machine-downloader` Ruby gem**, which this project complements rather than
  replaces. Install [Ruby](https://www.ruby-lang.org/en/downloads/) first (it comes with the
  `gem` command), then run `gem install wayback_machine_downloader_straw`
  -- this is the actively maintained [StrawberryMaster fork](https://github.com/StrawberryMaster/wayback-machine-downloader)
  of the original [hartator/wayback-machine-downloader](https://github.com/hartator/wayback-machine-downloader),
  which looks unmaintained. The executable is still called `wayback_machine_downloader`. If you
  already have the original gem installed, see the fork's README for a note about a possible
  conflict between the two.

This project has no Python runtime dependencies -- it only uses the standard library, so there
are no native libraries to worry about on any platform.

## Windows

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install .
```

## Linux -- Debian / Ubuntu

```sh
sudo apt update
sudo apt install -y python3-venv

python3 -m venv .venv
source .venv/bin/activate
pip install .
```

## Linux -- Arch

```sh
sudo pacman -S --needed python

python -m venv .venv
source .venv/bin/activate
pip install .
```

## Optional: development tools

The development tools are provided as an optional dependency group: `ruff` (lint and format),
`basedpyright` (type checking, "recommended" mode), `pylint`, `pytest` (the test suite),
`radon` (complexity) and `vulture` (dead code).

```sh
pip install -U -e ".[dev]"
ruff check . && ruff format --check .
basedpyright
pylint src tests
pytest
```

Lines are limited to 100 characters (ruff and pylint), and ruff and basedpyright check the code
against Python 3.10, the oldest supported version. The tests pass on Python 3.10, 3.12 and
3.13 (two need a case-insensitive filesystem and skip elsewhere, one a case-sensitive one; the
symlink tests skip where symlinks can't be created, as on Windows without the privilege, and
the read-only folder test on Windows or as root). They include convention tests that fail on
a missing docstring section, dead or duplicated code, a function above radon grade B or a
module over 500 lines.

## Verifying the install

```sh
wmdc --help
wmdc-merge --help
wmdc-find --help
wmdc-download --help
```

All four should print their usage text. See [README.md](README.md) for how to configure and run
them.
