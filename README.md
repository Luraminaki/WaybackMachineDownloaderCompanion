# WAYBACK-MACHINE-DOWNLOADER-COMPANION

Python 3 scripts that complements the [hartator/wayback-machine-downloader]((https://github.com/hartator/wayback-machine-downloader)) software output.

I made these following scripts at one of my dearest friend's request.
For a bit of context, an (arguably) old website has been decommissioned fairly recently (09/2023 ~ 10/2023), and all its content (as it turned out, 'most' is a better word in that case) can now only be found on the famous [Wayback Machine - Internet Archive](https://archive.org/web/).
This is a good thing because its content still exists (mostly), but somewhat worrying as we don't know for how long, and pretty annoying because browsing through the [Wayback Machine - Internet Archive](https://archive.org/web/) is a slow process (some request give an answer only after 5 seconds or more).

With the use of [wayback-machine-downloader](https://github.com/hartator/wayback-machine-downloader), I was able to download what turned out to be about 7% of the whole website with this software alone.
Since [wayback-machine-downloader](https://github.com/hartator/wayback-machine-downloader) allows the download of single **URL**, I made the following scripts that helped me with finding all the **URLs** that were 'locally' missing, and fed them to [wayback-machine-downloader](https://github.com/hartator/wayback-machine-downloader) to download said missing files. (I had to repeat this process a couple of times).

## VERSIONS

- 0.1.0-alpha: First release

## TABLE OF CONTENT

<!-- TOC -->

- [WAYBACK-MACHINE-DOWNLOADER-COMPANION](#wayback-machine-downloader-companion)
  - [VERSIONS](#versions)
  - [TABLE OF CONTENT](#table-of-content)
  - [INSTALL GUIDE](#install-guide)
  - [START GUIDE](#start-guide)
    - [CASE 01](#case-01)
    - [CASE 02](#case-02)
  - [WARNINGS](#warnings)

<!-- /TOC -->

## INSTALL GUIDE

Install the [wayback-machine-downloader](https://github.com/hartator/wayback-machine-downloader) software. You will need [RubyGems](https://www.geeksforgeeks.org/how-to-install-rubygems-on-linux/).

For `Python 3` installation, consult the following [link](https://www.python.org/downloads/)
No other dependencies needed, I wanted to only use the Python 3 standard library for this small project.

## START GUIDE

Don't forget to adjust the variables `WEB_FOLDER` and `WEB_OUTPUT` in the config file `config.json` accordingly to your needs.

- Rename the current folder `Wayback-Machine-Downloader-Companion` into `websites`
- Open a terminal / command prompt, go in the parent's directory of the freshly renamed folder `websites`, and run [wayback-machine-downloader](https://github.com/hartator/wayback-machine-downloader)

### CASE 01

Assuming you ran [wayback-machine-downloader](https://github.com/hartator/wayback-machine-downloader) with the following basic command line in the parent directory:

```sh
wayback_machine_downloader http://example.com
```

- Run the following commands until there is nothing else found to download

```sh
python3 find_missing_ressource.py
```

```sh
python3 download_missing_ressource.py
```

### CASE 02

If you ran [wayback-machine-downloader](https://github.com/hartator/wayback-machine-downloader) with the following command line in the parent directory:

```sh
wayback_machine_downloader http://example.com -s
```

- Run the following command, and then proceed to [CASE 01](#case-01)

```sh
python3 merge_snapshots.py
```

## WARNINGS

- Some websites are fairly old, and their 'textual' content may not have been saved with `utf-8` encoding... So you can find some strange characters in your files, or get some errors from my scripts because of that.
- These scripts 'just worked' for me (albeit with a few tweaks here and there)... So it may not be 100% tailored to your own needs.

Best of luck, and I hope this helped.
