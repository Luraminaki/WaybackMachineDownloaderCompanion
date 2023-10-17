# Wayback-Machine-Downloader-Companion

## DESCRIPTION

Python 3 scripts that complement the hartator/wayback-machine-downloader software output.

I made these following scripts at one of my dearest friend's request.
For a bit of context, an (arguably) old website has been decommissioned fairly recently (09/2023 ~ 10/2023), and all its content (as it turned out, 'most' is a better word in that case) can now only be found on the famous [Wayback Machine - Internet Archive](https://archive.org/web/).
This is a good thing because its content still exists (mostly), but somewhat worrying as we don't know for how long, and pretty annoying because browsing through the [Wayback Machine - Internet Archive](https://archive.org/web/) is a slow process (some request give an answer only after 5 seconds or more).

With the use of [wayback-machine-downloader](https://github.com/hartator/wayback-machine-downloader), I was able to download what turned out to be about 7% of the whole website with this software alone.
Since [wayback-machine-downloader](https://github.com/hartator/wayback-machine-downloader) allows the download of single **URL**, I made the following scripts that helped me finding all the **URLs** that were 'locally' missing, and fed them to [wayback-machine-downloader](https://github.com/hartator/wayback-machine-downloader) to download said missing files. (I had to repeat this process a couple of times).

## INSTALL GUIDE

Install the [wayback-machine-downloader](https://github.com/hartator/wayback-machine-downloader) software. You will need [RubyGems](https://www.geeksforgeeks.org/how-to-install-rubygems-on-linux/).
You will also need Python 3.10 (No other dependencies needed, I wanted to only use the Python 3 standard library for this small project).

## START GUIDE

- Rename the current folder `Wayback-Machine-Downloader-Companion` into `websites`
- Open a terminal / command prompt

Assuming you ran [wayback-machine-downloader](https://github.com/hartator/wayback-machine-downloader) with the basic command line: `wayback_machine_downloader http://example.com` in the parent directory:

- Run the following commands until there is nothing else found to download

```sh
python3 find_missing_ressource.py
```

```sh
python3 download_missing_ressource.py
```

If you ran [wayback-machine-downloader](https://github.com/hartator/wayback-machine-downloader) with the following command line: `wayback_machine_downloader http://example.com -s` in the parent directory:

- Run the following command

```sh
python3 merge_snapshots.py
```

Don't forget to adjust the names of the folders in each python scripts accordingly to your needs.

## WARNINGS

- As mentionned above, you will have to change / tweak these scripts depending on your needs. For instance, you may want to change the values of `WEB_FOLDER` and / or `WEB_OUTPUT`...
- Some websites are fairly old, and their 'textual' content may not have been saved with `utf-8` encoding... So you can find some strange characters in your files, or get some errors from my scripts because of that.
- These scripts 'just worked' for me... So it may not be 100% tailored to your own needs.

Best of luck, and I hope this helped.
