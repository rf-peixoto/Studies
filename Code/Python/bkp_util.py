# WIP
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
