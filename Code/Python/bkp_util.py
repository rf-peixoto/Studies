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
