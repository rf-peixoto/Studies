import os
import zipfile
from pathlib import Path

home = Path.home()

# Openning file:
compressed_data = zipfile.ZipFile("file.zip")
print(compressed_data.namelist()) # Show contents
#.file_size and .compress_size for info

# Extract:
compressed_data.extractall("destination/path")
compressed_file.close()

# Create and Compress (Add files):
backup = zipfile.ZipFile("backup.zip", "w") # Use mode "a" to add files
backup.write("folder", compress_type=zipfile.ZIP_DEFLATED)
backup.close()

# Complete method:
def make_backup(folder):
    filename = os.path.abspath(folder) # Get absolute path
    counter = 1
    while True:
        backup = os.path.basename(folder) + "_" + str(number) + ".zip"
        if not os.path.exists(backup):
            break
    backup_zip = zipfile.ZipFile(filename, "w")

    print("Backup done")
