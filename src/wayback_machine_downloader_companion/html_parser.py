#!/usr/bin/env python3
r"""HTML parsing: extract local resource links referenced by downloaded pages.

Links are resolved lexically (:func:`normalize`), never through the filesystem: it costs
no system call per link, doesn't follow symlinks, and gives the same form as the local file
paths they are compared with. A link that resolves outside the site folder can't be a local
resource of the site: it is reported as unspecified.

A backslash in a link counts as ``/`` on every OS, the way browsers read the links of old
Windows-made sites (``images\logo.gif`` is ``images/logo.gif``).
"""

import dataclasses
import logging
import pathlib
import re
import urllib.parse
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

# Protocol-relative (``//host``, or ``\\host`` with browsers' backslash folding) or a scheme.
_EXTERNAL = re.compile(r"^(?:[/\\]{2}|[a-zA-Z][a-zA-Z0-9+.\-]*:)")

# Tag -> attributes holding a resource link.
LINK_ATTRIBUTES: dict[str, frozenset[str]] = {
    "a": frozenset({"href"}),
    "area": frozenset({"href"}),
    "link": frozenset({"href"}),
    "img": frozenset({"src"}),
    "frame": frozenset({"src"}),
    "iframe": frozenset({"src"}),
    "script": frozenset({"src"}),
    "source": frozenset({"src"}),
    "embed": frozenset({"src"}),
    "input": frozenset({"src"}),  # <input type="image">
    "object": frozenset({"data"}),
    "body": frozenset({"background"}),
    "table": frozenset({"background"}),
    "td": frozenset({"background"}),
    "th": frozenset({"background"}),
}


def _clean_link(value: str) -> str:
    """Keeps the path of a local link: no query string or fragment, ``/`` separators only.

    Args:
        value (str): A raw link attribute value.

    Returns:
        str: ``value`` with any ``?query`` and ``#fragment`` suffix removed and its
        backslashes turned into ``/``.
    """
    return value.split("#", maxsplit=1)[0].split("?", maxsplit=1)[0].replace("\\", "/")


def is_external(value: str) -> bool:
    r"""Returns whether a link points off-site rather than to a local resource.

    Args:
        value (str): A raw link attribute value.

    Returns:
        bool: ``True`` if ``value`` is protocol-relative (``//host/...``, also written
            ``\\host\...``) or has a URI scheme (``http:``, ``https:``, ``mailto:``,
            ``javascript:``, ...).
    """
    return bool(_EXTERNAL.match(value))


def normalize(path: pathlib.PurePath) -> pathlib.PurePath:
    """Collapses ``..`` segments lexically, without touching the filesystem.

    ``Path.resolve`` would read the disk (and follow symlinks) for every link; pathlib already
    drops ``.`` and repeated separators, so only ``..`` remains to fold. Like a shell, ``..``
    never climbs above the root.

    Args:
        path (pathlib.PurePath): An absolute path.

    Returns:
        pathlib.PurePath: The same path without ``..`` segments.
    """
    if ".." not in path.parts:
        return path
    parts: list[str] = []
    for part in path.parts:
        if part != "..":
            parts.append(part)
        elif len(parts) > 1:  # parts[0] is the root
            _ = parts.pop()
    return type(path)(*parts)


def decode_page(data: bytes) -> str:
    """Decodes a downloaded page whatever its encoding.

    UTF-8 first (a byte order mark is dropped); then cp1252, the usual encoding of older
    Western pages; Latin-1 last, which accepts any byte. Accented file names in links stay
    intact (a lossy decoder would turn them into replacement characters that match no local
    file).

    Args:
        data (bytes): The raw page.

    Returns:
        str: Its text.
    """
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1252")
    except UnicodeDecodeError:
        return data.decode("latin-1")


class WBMHTMLParser(HTMLParser):
    """HTML parser that collects the resource links of pages (see :data:`LINK_ATTRIBUTES`)."""

    def __init__(
        self,
        html_ext: frozenset[str],
        other_ext: frozenset[str],
        site_root: pathlib.Path | None = None,
    ) -> None:
        """Initializes a parser with empty, per-instance link sets.

        Args:
            html_ext (frozenset[str]): Lowercase extensions (with leading dot) classified as
                HTML links (e.g. ``".htm"``).
            other_ext (frozenset[str]): Lowercase extensions (with leading dot) classified as
                other (non-HTML) resource links (e.g. ``".css"``).
            site_root (pathlib.Path | None, optional): The site folder: root-relative links
                (e.g. ``"/css/style.css"``) are resolved against it, and links resolving
                outside it are unspecified. Defaults to the current working directory.
        """
        super().__init__()
        self.html_ext: frozenset[str] = html_ext
        self.other_ext: frozenset[str] = other_ext
        self.site_root: pathlib.PurePath = normalize((site_root or pathlib.Path()).absolute())
        self.html_links: set[str] = set()
        self.other_links: set[str] = set()
        self.unspecified_links: set[str] = set()
        self.current_path: pathlib.PurePath = self.site_root  # until a page sets its own
        # Classified links of the current folder (see :meth:`_classify`): pages of one folder
        # repeat the same links (menus, images), and pages are visited folder by folder.
        # Cleared when the folder changes, so it holds at most one folder's distinct links.
        self._classified: dict[str, tuple[set[str], str | None]] = {}

    def _classify(self, cleaned_value: str) -> tuple[set[str], str | None]:
        """Resolves a cleaned local link and picks the link set it belongs to.

        Args:
            cleaned_value (str): A link value cleaned by :func:`_clean_link`.

        Returns:
            tuple[set[str], str | None]: The link set to store it in, and its resolved
            absolute path, posix style; ``None`` if it leaves the site folder (it is then
            unspecified, and stored as written).
        """
        relative = urllib.parse.unquote(cleaned_value)
        base = self.site_root if relative.startswith("/") else self.current_path
        resolved = normalize(base / relative.lstrip("/"))
        root_parts = self.site_root.parts
        if resolved.parts[: len(root_parts)] != root_parts:
            return self.unspecified_links, None
        suffix = resolved.suffix.lower()
        if suffix in self.html_ext:
            return self.html_links, resolved.as_posix()
        if suffix in self.other_ext:
            return self.other_links, resolved.as_posix()
        return self.unspecified_links, resolved.as_posix()

    def _record(self, value: str) -> None:
        """Classifies one link value and stores it.

        Args:
            value (str): A raw link attribute value.
        """
        if is_external(value):
            self.unspecified_links.add(value)
            return
        cleaned_value = _clean_link(value)
        if not cleaned_value:
            return  # in-page anchor or query only (e.g. href="#top"), not a resource

        classified = self._classified.get(cleaned_value)
        if classified is None:
            classified = self._classified[cleaned_value] = self._classify(cleaned_value)
        links, resolved = classified
        links.add(value if resolved is None else resolved)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Records the resource links of a start tag (``HTMLParser`` lowercases names).

        Args:
            tag (str): The parsed tag name.
            attrs (list[tuple[str, str | None]]): The tag's ``(name, value)`` attribute pairs;
                ``value`` is ``None`` for valueless attributes (e.g. ``disabled``).
        """
        wanted = LINK_ATTRIBUTES.get(tag)
        if wanted is None:
            return
        for name, value in attrs:
            if value is not None and name in wanted:
                self._record(value.strip())

    def parse_page(self, text: str, folder: pathlib.Path) -> None:
        """Parses one whole page, resolving its relative links against its own folder.

        The parser's state is reset after the page, so an unclosed ``<script>`` or tag can't
        swallow or misplace the next page's links.

        Args:
            text (str): The page's HTML.
            folder (pathlib.Path): The folder the page is in.
        """
        folder_path = normalize(folder.absolute())
        if folder_path != self.current_path:
            self.current_path = folder_path
            self._classified.clear()
        try:
            self.feed(text)
            self.close()  # process what the page left buffered
        finally:
            self.reset()


@dataclasses.dataclass(slots=True)
class LinkReport:
    """Links found across a batch of parsed HTML files.

    The link sets are the parser's own (not copies): sort them where an order is needed.

    Attributes:
        html_links (set[str]): Local HTML links.
        other_links (set[str]): Local non-HTML resource links.
        unspecified_links (set[str]): Links that could not be classified (external URLs, links
            leaving the site folder, unrecognized extensions).
        corrupted_files (list[str]): Sorted paths of HTML files that couldn't be read.
    """

    html_links: set[str]
    other_links: set[str]
    unspecified_links: set[str]
    corrupted_files: list[str]


def _parse_file(parser: WBMHTMLParser, file: pathlib.Path) -> bool:
    """Parses one HTML file into the parser's link sets.

    Args:
        parser (WBMHTMLParser): The parser links are accumulated into.
        file (pathlib.Path): The file.

    Returns:
        bool: ``False`` if the file couldn't be read (logged).
    """
    try:
        data = file.read_bytes()
    except OSError as error:  # vanished, unreadable: one bad page must not abort the batch
        logger.warning("Error while reading file %s : %s", file, error)
        return False
    # Neither step raises: decode_page accepts any bytes, HTMLParser any text.
    parser.parse_page(decode_page(data), file.parent)
    return True


def find_all_links(parser: WBMHTMLParser, files_path: list[pathlib.Path]) -> LinkReport:
    """Feeds a batch of HTML files through a parser and collects the links they reference.

    Args:
        parser (WBMHTMLParser): The parser instance links are accumulated into.
        files_path (list[pathlib.Path]): Paths to the HTML files to parse.

    Returns:
        LinkReport: The links found, plus any files that failed to parse.
    """
    corrupted_files = [str(file) for file in files_path if not _parse_file(parser, file)]
    report = LinkReport(
        html_links=parser.html_links,
        other_links=parser.other_links,
        unspecified_links=parser.unspecified_links,
        corrupted_files=sorted(corrupted_files),
    )

    logger.info("Found %d possibly corrupted html file(s)", len(report.corrupted_files))
    logger.info("Found %d html link(s)", len(report.html_links))
    logger.info("Found %d other link(s)", len(report.other_links))
    logger.info("Found %d unspecified link(s)", len(report.unspecified_links))
    return report
