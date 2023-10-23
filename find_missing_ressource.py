#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Oct 13 18:40:32 2023

@author: Luraminaki
"""

#===================================================================================================
import inspect
import pathlib
from html.parser import HTMLParser

#pylint: disable=wrong-import-order, wrong-import-position

#pylint: enable=wrong-import-order, wrong-import-position
#===================================================================================================


__version__ = '0.1.0'


CWD = pathlib.Path.cwd()

WEB_FOLDER = 'mn-net.pagesperso-orange.fr'
WEB_OUTPUT = WEB_FOLDER + ''

FOLDER_OUTPUT = CWD/WEB_OUTPUT

HTML_EXT = ['htm']
OTHER_EXT = ['css', 'gif', 'jpg',
             'jpeg', 'png', 'ico']


class WBMHTMLParser(HTMLParser):
    """Basic HTML Parser class from html.parser.HTMLParser.
    """
    seeked_tags = ('a', 'img', 'link', 'frame')
    seeked_properties = ('href', 'src')

    hreflinkshtml: list[str] = []
    hreflinksother: list[str] = []
    hreflinksunspec: list[str] = []

    current_path = ''

    def handle_starttag(self, tag :str, attrs: list[str, str]):
        """Find valid link in <a></a>, <img></img>, <link></link>, <frame></frame> tags.

        Args:
            tag (str): Parsed tag.
            attrs (list): Tag's attributes (property and value).
        """
        if tag.lower() in self.seeked_tags:
            for name, value in attrs:
                if name.lower() in self.seeked_properties:
                    lvalue = value.lower()

                    if any(ext in lvalue for ext in HTML_EXT):
                        if not lvalue.startswith('http'):
                            value = pathlib.Path(self.current_path + '/' + value).resolve()
                            self.hreflinkshtml.append(str(value).split('#', maxsplit=1)[0])

                        else:
                            self.hreflinksunspec.append(value)

                    elif any(ext in lvalue for ext in OTHER_EXT):
                        value = pathlib.Path(self.current_path + '/' + value).resolve()
                        self.hreflinksother.append(str(value).split('#', maxsplit=1)[0])

                    else:
                        self.hreflinksunspec.append(value)


def flatten(a: list | set) -> list:
    """Function that flattens either a list or a set.

    Args:
        a (list | set): Itterable to flatten.

    Returns:
        list: Flattened itterable.
    """
    return [c for b in a for c in flatten(b)] if isinstance(a, (list, set)) else [a]


def get_all_files(files: list[pathlib.Path], exts: list[str]) -> tuple[list[pathlib.Path], set[str]]:
    """Given a path, returns a list and set of paths of all the 'ext' files found.

    Args:
        folder_path (list[pathlib.Path]): All files path of the folder to search.
        ext (list[str]): Files extentions.

    Returns:
        tuple[list[pathlib.Path], set[str]]: list and set of the path to the ext files.
    """
    curr_func = inspect.currentframe().f_code.co_name

    all_files: list[pathlib.Path] = []

    for ext in exts:
        all_files = all_files + [file for file in files if ext in file.suffix.lower()]

    print(f"{curr_func} -- Found {len(all_files)} {exts} file(s) in folder {FOLDER_OUTPUT}")
    return all_files, {str(file) for file in all_files}


def find_all_links(wbm_parser: WBMHTMLParser, files_path: list[pathlib.Path]) -> tuple[list[str], list[str], list[str]]:
    """Function that returns all the links found in 'href' properties in html files.

    Args:
        wbm_parser (WBMHTMLParser): HTML parser class.
        files_path (list[pathlib.Path]): Path to the html files to parse.

    Returns:
        tuple[list[str], list[str], list[str]]: html links, other links,
                                                html file that triggered an error during parsing.
    """
    curr_func = inspect.currentframe().f_code.co_name

    err_html_files_path: list[str] = []

    for file in files_path:
        try:
            wbm_parser.current_path = str(file.parent)
            wbm_parser.feed(file.read_text(encoding='utf-8'))
        except Exception as error:
            err_html_files_path.append(str(file))
            print(f"{curr_func} -- Error while reading file {str(file)} : {error}")

            with file.open('rb') as corrupted_file:
                cptr_line = 1
                for line in corrupted_file:
                    try:
                        _ = str(line.decode('utf-8'))
                        cptr_line = cptr_line + 1
                    except Exception:
                        print(f"{curr_func} -- \tError on line {cptr_line}")

    html = sorted(set(wbm_parser.hreflinkshtml))
    other = sorted(set(wbm_parser.hreflinksother))
    unspec = sorted(set(wbm_parser.hreflinksunspec))
    err_html_files_path.sort()

    print(f"{curr_func} -- Found {len(err_html_files_path)} possibly corrupted html files")
    print(f"{curr_func} -- Found {len(html)} html link(s)")
    print(f"{curr_func} -- Found {len(other)} other link(s)")
    print(f"{curr_func} -- Found {len(unspec)} unspecified link(s)")

    return html, other, unspec, err_html_files_path


def sort_data(local_file: set[str], found_links: set[str], ressource_name: str) -> tuple[list[str], list[str], list[str]]:
    """Function that returns the overall status of the ressources between what's been found,
       missing, or never mentionned.

    Args:
        local_file (set[str]): set of path (str) of each file.
        found_links (set[str]): set of link (ressource) found in all the files.
        ressource_name (str): name of the ressource found.

    Returns:
        tuple[list[str], list[str], list[str]]: Locally existing files, Missing files,
                                                Locally existsing files never mensionned.
    """
    curr_func = inspect.currentframe().f_code.co_name

    common = sorted(local_file.intersection(found_links))
    never_mentionned = sorted(local_file.difference(found_links))
    missing = sorted(found_links.difference(local_file))

    for link in never_mentionned:
        if link in missing:
            missing.pop(link)

    print(f"{curr_func} -- Found {len(common)} existing {ressource_name} ressource(s)")
    print(f"{curr_func} -- Found {len(missing)} missing {ressource_name} ressource(s)")
    print(f"{curr_func} -- Found {len(never_mentionned)} existing but never 'called' {ressource_name} ressource(s)")

    return common, missing, never_mentionned


def export_missing(file_path: str | pathlib.Path, missing: list[str]) -> None:
    """Function that exports the list of missing ressource into a writable file.

    Args:
        file_path (str | pathlib.Path): file path.
        missing (list[str]): list of missing ressources.
    """
    curr_func = inspect.currentframe().f_code.co_name

    print(f"{curr_func} -- Saving {file_path}")
    with open(file_path, 'w', encoding='utf-8') as mf:
        for link in missing:
            line = link.replace(str(CWD), 'https:/')
            line = line.replace(str(WEB_OUTPUT), str(WEB_FOLDER))
            mf.write(line + '\n')


def main() -> int:
    """main
    """
    curr_func = inspect.currentframe().f_code.co_name

    wbm_parser = WBMHTMLParser()
    wbm_parser.hreflinkshtml: list[str] = []
    wbm_parser.hreflinksother: list[str] = []

    files: list[pathlib.Path] = list(FOLDER_OUTPUT.rglob('*.*'))
    if not files:
        print(f"{curr_func} -- Nothing found in {FOLDER_OUTPUT} -- Aborting")
        return 1
    files.sort()

    html_files_path, html_files_path_str = get_all_files(files, HTML_EXT)
    _, other_files_path_str = get_all_files(files, OTHER_EXT)

    print("\n")
    html, other, unspec, _ = find_all_links(wbm_parser, html_files_path)
    print("\n")
    _, missing_h, _ = sort_data(html_files_path_str, set(html), 'html')
    print("\n")
    _, missing_o, _ = sort_data(other_files_path_str, set(other), 'other')
    print("\n")

    export_missing('missing_html.txt', missing_h)
    export_missing('missing_other.txt', missing_o)
    export_missing('unspecified.txt', unspec)

    print(f"{curr_func} -- Done")
    return 0


if __name__ == "__main__":
    main()
