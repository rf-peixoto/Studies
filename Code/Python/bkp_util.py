# ================================================== #
# Backup Util
# ================================================== #
import sys
import zipfile
from datetime import datetime
# -------------------------------------------------- #
if len(sys.argv) <= 1:
    print("Usage: {0} [folder_name]".format(sys.argv[0]))
    sys.exit()
# -------------------------------------------------- #
folder_name = str(sys.argv[1])

# Get Date:
time = datetime.now()
time_string = "{0}{1}{2}".format(str(time.month).zfill(2), str(time.day).zfill(2), str(time.year).zfill(4))
# -------------------------------------------------- #
# Save file:
print("Compressing.")

backup = zipfile.ZipFile(file="{0}_{1}.bkp".format(folder_name, time_string), mode="w", compresslevel=9)
backup.write(folder_name, compress_type=zipfile.ZIP_DEFLATED)
backup.close()

# -------------------------------------------------- #
print("Done.")

""" [WIP]

# ===================================== #
# Backup Folder
# ===================================== #
import zipfile
import os

# Input folder:
folder_name = input("Folder name: ")
directory = os.path.abspath(folder_name)
zip_name = "{0}.bkp.zip".format(directory)

# Create File:
backup = zipfile.ZipFile(file=zip_name, mode="w", compresslevel=9)
for foldername, subfolder, files in os.walk(directory):
    backup.write(foldername, compress_type=zipfile.ZIP_DEFLATED)
for f in files:
    tmp_name = os.path.basename(folder_name) + '_'
    if f.startswith(tmp_name) and f.endswith('.zip'):
        continue
    backup.write(os.path.join(foldername, f), compress_type=zipfile.ZIP_DEFLATED)
backup.close()


#backup.write(folder_name, compress_type = zipfile.ZIP_DEFLATED)

"""
