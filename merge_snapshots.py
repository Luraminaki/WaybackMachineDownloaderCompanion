#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Oct 13 17:40:26 2023

@author: Luraminaki
"""

#===================================================================================================
import inspect
import pathlib
import shutil

#pylint: disable=wrong-import-order, wrong-import-position

#pylint: enable=wrong-import-order, wrong-import-position
#===================================================================================================


__version__ = '0.1.0'


CWD = pathlib.Path.cwd()

WEB_FOLDER = 'mn-net.pagesperso-orange.fr_command-s'
WEB_OUTPUT = WEB_FOLDER + '_output'

FOLDER_OUTPUT = CWD/WEB_OUTPUT


def rm_tree(pth: pathlib.Path) -> None:
    """Function that deletes a file or a folder and its content.

    Args:
        pth (pathlib.Path): Folder or file to delete.
    """
    for child in pth.glob('*'):
        if child.is_file():
            child.unlink()
        else:
            rm_tree(child)

    pth.rmdir()


def get_all_files(folders_path: pathlib.Path) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """Given a path, returns a list of paths of the most recent version of the file.

    Args:
        folders_path (pathlib.Path): Path of the versioned folders.

    Returns:
        tuple: tuple of list of the path of the most recent files
               (original[pathlib.Path], destination[pathlib.Path])
    """
    curr_func = inspect.currentframe().f_code.co_name

    dest_merge = []
    merge = []

    versions = list(folders_path.glob('*'))
    if not versions:
        print(f"{curr_func} -- Nothing to merge")
        return []

    versions.sort()
    versions = versions[::-1]

    print(f"{curr_func} -- Found {len(versions)} folders to be merged")

    for folder in versions:
        folder_name = folder.stem

        files = list(folder.rglob('*.*'))
        if not files:
            print(f"{curr_func} -- Nothing to merge in {folder_name}")
            continue

        files.sort()
        print(f"{curr_func} -- Found {len(files)} file(s) in folder {folder_name}")

        for file in files:
            dest_file = str(file)
            dest_file = dest_file.replace(f"{folder_name}/", '')
            dest_file = dest_file.replace(WEB_FOLDER, WEB_OUTPUT)
            dest_file = pathlib.Path(dest_file)

            if dest_file not in dest_merge:
                dest_merge.append(dest_file)
                merge.append(file)

    if len(dest_merge) != len(merge):
        print(f"{curr_func} -- Something went terribly wrong here -- Aborting")
        return []

    print(f"{curr_func} -- Found {len(merge)} files for {WEB_FOLDER}")
    return merge, dest_merge


def main() -> int:
    """main
    """
    curr_func = inspect.currentframe().f_code.co_name

    try:
        rm_tree(FOLDER_OUTPUT)
    except Exception as error:
        print(f"{curr_func} -- Nothing to delete : {error}")

    FOLDER_OUTPUT.mkdir(exist_ok=True)

    merge, dest_merge = get_all_files(CWD/WEB_FOLDER)

    for cptr, orig_file_path in enumerate(merge):
        dest_file_path = dest_merge[cptr]
        print(f"{curr_func} -- Copying\n\t{orig_file_path}\nto\n\t{dest_file_path}")
        print("#==================================================================================")

        dest_file_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(orig_file_path, dest_file_path)

    print(f"{curr_func} -- Done")

    return 0


if __name__ == "__main__":
    main()
