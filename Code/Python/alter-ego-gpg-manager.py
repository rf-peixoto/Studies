import sqlite3
import os
import gnupg
from datetime import datetime

# Setup agent for not hardcoded passwords:
# echo <passphrase> | gpg-connect-agent "PRESET_PASSPHRASE <keygrip> -1 /bye"
# Find <keygrip>:
# gpg --with-keygrip -K

# Configuration
DATABASE_PATH = 'database.db'
SIGNED_KEYS_DIR = 'signed_keys'
REVOCATION_CERTS_DIR = 'revocation_certs'
GPG_HOME_DIR = '/home/user/.gnupg/'
MAIN_KEY_PATH = 'main.pgp'

# Ensure directories exist
os.makedirs(SIGNED_KEYS_DIR, exist_ok=True)
os.makedirs(REVOCATION_CERTS_DIR, exist_ok=True)

# Initialize GPG
gpg = gnupg.GPG(gnupghome=GPG_HOME_DIR)
gpg.encoding = 'utf-8'

# Load the main key
with open(MAIN_KEY_PATH, 'rb') as f:
    main_key_data = f.read()
    main_key_import_result = gpg.import_keys(main_key_data)
    main_key_id = main_key_import_result.fingerprints[0]

class GPGManager:
    def __init__(self):
        self.conn = sqlite3.connect(DATABASE_PATH)
        self.cursor = self.conn.cursor()
        self.initialize_database()

    def initialize_database(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS keys
                               (id INTEGER PRIMARY KEY, username TEXT, public_key TEXT, signature TEXT,
                                revocation_cert_path TEXT, expiration_date TEXT, trust_level INTERGER)''')
        self.conn.commit()

    def add_key(self, username, public_key_path, trust_level="Unknown"):
        with open(public_key_path, 'rb') as f:
            public_key_data = f.read()
        imported_keys = gpg.import_keys(public_key_data)
        if not imported_keys.fingerprints:
            raise ValueError("Invalid public key file.")
        self.cursor.execute("SELECT * FROM keys WHERE public_key=? OR signature=?", (public_key_data.decode(), imported_keys.fingerprints[0]))
        if self.cursor.fetchone():
            raise ValueError("Key or signature already exists in the database.")
        # Sign with hardcoded password:
        signed_data = gpg.sign(public_key_data, passphrase='your_passphrase_here',detach=True)
#        signed_data = gpg.sign(public_key_data, default_key=main_key_id, detach=True)

        key_info = gpg.list_keys(keys=imported_keys.fingerprints[0])[0]
        expiration_date = key_info.get('expires')
        if expiration_date:
            expiration_date = datetime.fromtimestamp(int(expiration_date)).strftime('%Y-%m-%d')
        else:
            expiration_date = "Never"

        self.cursor.execute("INSERT INTO keys (username, public_key, signature, expiration_date, trust_level) VALUES (?, ?, ?, ?, ?)",
                            (username, public_key_data.decode(), signed_data.data.decode(), expiration_date, trust_level))
        self.conn.commit()
        signed_path = os.path.join(SIGNED_KEYS_DIR, f"{username}_signed.gpg")
        with open(signed_path, 'wb') as f:
            f.write(signed_data.data)
        print(f"Key added and signed. Signed key saved to: {signed_path}")

    def submit_revocation_cert(self, username, revocation_cert_path):
        with open(revocation_cert_path, 'rb') as f:
            revocation_cert_data = f.read()
        # Check if the certificate is a valid GPG revocation certificate
        imported_cert = gpg.import_keys(revocation_cert_data)
        if not imported_cert.results or not any('revocation certificate' in result.get('ok', '') for result in imported_cert.results):
            raise ValueError("Invalid revocation certificate.")
        # Generate a safe filename and save the certificate in the revocation certificates directory
        cert_filename = f"{username}_revocation.gpg"
        cert_path = os.path.join(REVOCATION_CERTS_DIR, cert_filename)
        with open(cert_path, 'wb') as f:
            f.write(revocation_cert_data)
        # Update the database record for the user to include the path to the revocation certificate
        self.cursor.execute("UPDATE keys SET revocation_cert_path=? WHERE username=?", (cert_path, username))
        self.conn.commit()
        print(f"Revocation certificate submitted for {username}.")

    def consult_key(self, username):
        self.cursor.execute("SELECT public_key, signature, revocation_cert_path, expiration_date, trust_level FROM keys WHERE username=?", (username,))
        result = self.cursor.fetchone()
        if result:
            public_key, signature, revocation_cert_path, expiration_date, trust_level = result
            now = datetime.now().strftime('%Y-%m-%d')
            if revocation_cert_path:
                print(f"WARNING: A revocation certificate has been submitted for this key.")
            if expiration_date != "Never" and expiration_date < now:
                print(f"WARNING: This key has expired on {expiration_date}. Please use caution.")
            print(f"Public Key:\n{public_key}\n\nSignature:\n{signature}\n\nTrust Level: {trust_level}")
        else:
            print("No such key found.")
            
    def update_trust_level(self, username, new_trust_level):
        """
        Update the trust level of a key associated with a given username.

        :param username: The username associated with the key.
        :param new_trust_level: The new trust level as an integer.
        """
        self.cursor.execute("UPDATE keys SET trust_level=? WHERE username=?", (new_trust_level, username))
        self.conn.commit()
        print(f"Updated trust level for {username} to {new_trust_level}.")


    # You can add additional methods here for managing trust levels, deleting keys, etc., as needed.

if __name__ == "__main__":
    gpg_manager = GPGManager()
    # Example usage:
    gpg_manager.add_key('Username', 'username.pgp', trust_level='0')
    # gpg_manager.consult_key('username')
