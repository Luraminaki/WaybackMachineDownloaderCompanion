#!/usr/bin/env python3
"""HTML parsing: extract local resource links referenced by downloaded pages."""

import dataclasses
import logging
import pathlib
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

HTML_EXT = frozenset({'.htm', '.html'})
OTHER_EXT = frozenset({'.css', '.gif', '.jpg', '.jpeg', '.png', '.ico'})


def _strip_query_and_fragment(value: str) -> str:
    """Strips the query string and fragment off a URL or path value.

    Args:
        value (str): A raw ``href``/``src`` attribute value.

    Returns:
        str: ``value`` with any ``?query`` and ``#fragment`` suffix removed.
    """
    return value.split('#', maxsplit=1)[0].split('?', maxsplit=1)[0]


def _clean_suffix(value: str) -> str:
    """Returns the lowercase file extension of a URL or path, ignoring query string and fragment.

    Args:
        value (str): A raw ``href``/``src`` attribute value.

    Returns:
        str: The lowercase suffix (e.g. ``".htm"``), or an empty string if there is none.
    """
    return pathlib.Path(_strip_query_and_fragment(value)).suffix.lower()


class WBMHTMLParser(HTMLParser):
    """HTML parser that collects resource links found in ``<a>``, ``<img>``, ``<link>`` and ``<frame>`` tags."""

    seeked_tags = ('a', 'img', 'link', 'frame')
    seeked_properties = ('href', 'src')

    def __init__(self) -> None:
        """Initializes a parser with empty, per-instance link buffers."""
        super().__init__()
        self.html_links: list[str] = []
        self.other_links: list[str] = []
        self.unspecified_links: list[str] = []
        self.current_path = '.'

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Records any local resource link found in a start tag's ``href``/``src`` attribute.

        Args:
            tag (str): The parsed tag name.
            attrs (list[tuple[str, str | None]]): The tag's ``(name, value)`` attribute pairs;
                ``value`` is ``None`` for valueless attributes (e.g. ``disabled``).
        """
        if tag.lower() not in self.seeked_tags:
            return

        for name, value in attrs:
            if value is None or name.lower() not in self.seeked_properties:
                continue

            if value.lower().startswith('http'):
                self.unspecified_links.append(value)
                continue

            suffix = _clean_suffix(value)
            cleaned_value = _strip_query_and_fragment(value)
            resolved = pathlib.Path(f'{self.current_path}/{cleaned_value}').resolve().as_posix()

            if suffix in HTML_EXT:
                self.html_links.append(resolved)
            elif suffix in OTHER_EXT:
                self.other_links.append(resolved)
            else:
                self.unspecified_links.append(resolved)


@dataclasses.dataclass(slots=True)
class LinkReport:
    """Links found across a batch of parsed HTML files.

    Attributes:
        html_links (list[str]): Sorted, de-duplicated local HTML links.
        other_links (list[str]): Sorted, de-duplicated local non-HTML resource links.
        unspecified_links (list[str]): Sorted, de-duplicated links that could not be classified
            (absolute URLs or links without a recognized extension).
        corrupted_files (list[str]): Sorted paths of HTML files that raised an error while being
            read.
    """

    html_links: list[str]
    other_links: list[str]
    unspecified_links: list[str]
    corrupted_files: list[str]


def _log_corrupted_lines(file: pathlib.Path) -> None:
    """Logs the line numbers of a file that fail strict UTF-8 decoding.

    Args:
        file (pathlib.Path): The file to inspect.
    """
    with file.open('rb') as corrupted_file:
        for line_number, line in enumerate(corrupted_file, start=1):
            try:
                line.decode('utf-8')
            except UnicodeDecodeError:
                logger.warning('%s -- Non UTF-8 bytes on line %d', file, line_number)


def find_all_links(parser: WBMHTMLParser, files_path: list[pathlib.Path]) -> LinkReport:
    """Feeds a batch of HTML files through a parser and collects the links they reference.

    Args:
        parser (WBMHTMLParser): The parser instance links are accumulated into.
        files_path (list[pathlib.Path]): Paths to the HTML files to parse.

    Returns:
        LinkReport: The sorted, de-duplicated links found, plus any files that failed to parse.
    """
    corrupted_files: list[str] = []

    for file in files_path:
        try:
            parser.current_path = str(file.parent)
            parser.feed(file.read_text(encoding='utf-8'))
        except Exception as error:  # one bad/corrupted file must not abort the whole batch
            corrupted_files.append(str(file))
            logger.warning('Error while reading file %s : %s', file, error)
            _log_corrupted_lines(file)

    report = LinkReport(
        html_links=sorted(set(parser.html_links)),
        other_links=sorted(set(parser.other_links)),
        unspecified_links=sorted(set(parser.unspecified_links)),
        corrupted_files=sorted(corrupted_files),
    )

    logger.info('Found %d possibly corrupted html file(s)', len(report.corrupted_files))
    logger.info('Found %d html link(s)', len(report.html_links))
    logger.info('Found %d other link(s)', len(report.other_links))
    logger.info('Found %d unspecified link(s)', len(report.unspecified_links))

    return report
