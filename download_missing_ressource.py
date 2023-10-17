#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Oct 16 19:49:11 2023

@author: Luraminaki
"""

#===================================================================================================
import time
import inspect
import pathlib

import subprocess

#pylint: disable=wrong-import-order, wrong-import-position

#pylint: enable=wrong-import-order, wrong-import-position
#===================================================================================================


__version__ = '0.1.0'


CWD = pathlib.Path.cwd()

FILES = ('missing_html.txt', 'missing_other.txt')
COMMAND = "wayback_machine_downloader -e " # Tailing space in the string is very important


def start_process(command: str) -> int:
    """Function that runs a command with subprocess.

    Args:
        command (str): command to run.

    Returns:
        int: 1 or 0 depending on request success.
    """
    curr_func = inspect.currentframe().f_code.co_name

    print("#==================================================================================")
    print(f"Running command: {command}")
    with subprocess.Popen(command.split(' '),
                          cwd=CWD.parent,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT) as p0:

        for line in p0.stdout:
            line = line.decode('utf-8').replace('\n', '')
            print(f"{line}")
            if "Download completed" in line:
                p0.terminate()
                return 0

    print(f"{curr_func} -- Command did not return expected result")
    return 1


def main() -> int:
    """main
    """
    curr_func = inspect.currentframe().f_code.co_name

    for file in FILES:
        curr_file: pathlib.Path = CWD/file

        if not curr_file.exists():
            print(f"{curr_func} -- File {curr_file} does not exists")
            continue

        with open(curr_file, 'r', encoding='utf-8') as cf:
            for line in cf:
                if line.replace('\n', '') != '':
                    command = COMMAND + line.replace('\n', '')
                    start_process(command)
                    time.sleep(1)

    print(f"{curr_func} -- Done")

    return 0

if __name__ == "__main__":
    main()
