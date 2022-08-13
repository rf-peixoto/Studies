#!/usr/bin/env python
#
# Code obfuscation using nuitka
# Convert python code to shared object.
#
# Ref: https://varunbpatil.github.io/2019/09/29/nuitka-code-obfuscation.html
import os
import pprint


# Project directories to run nuitka on.
# Edit this to include the directories you want.
PROJECT_DIRS = [
    'src/data',
    'src/drivers',
    'src/features',
    'src/models',
    'src/scripts'
]

EXCLUDE_FILES = [
    '__init__.py'
]


def main():
    """
    Go through each python file in the given project directories and
    convert python code to shared object using nuitka.
    Remove the original .py file as well.
    """
    py_files_processed = []

    for nuitka_dir in PROJECT_DIRS:
        for root, _, files in os.walk(nuitka_dir):
            for file in files:
                if file.endswith('.py'):
                    if file in EXCLUDE_FILES:
                        continue

                    file_path = os.path.join(root, file)

                    print(f'Processing file: {file_path}')
                    py_files_processed.append(file_path)

                    # Remove doc-strings from shared object by passing -OO
                    # flag.
                    cmd = ('python -m nuitka --module --python-flag=-OO '
                           '--remove-output --lto --output-dir={} {}')
                    os.system(cmd.format(root, file_path))

                    # Remove the original .py file.
                    os.remove(file_path)

    print('Processed the following py files:')
    pprint.pprint(py_files_processed)


if __name__ == '__main__':
    main()
