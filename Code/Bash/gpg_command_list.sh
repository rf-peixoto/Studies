# Generate Key Pair:
gpg --gen-key

# List All Keys:
gpg --list-keys

# List Private Keys:
gpg --list-secret-keys

# Filter Keys:
gpg --list-keys [email or id]

# List Signatures:
gpg --list-sigs

# List Fingerprints:
gpg --fingerprint

# Delete Private Key:
gpg --delete-secret-keys [email or id] 

# Delete Public Keys:
gpg --delete-key [email or id]

# Edit Key:
gpg --edit-key [email or id]

# Revoke Key:
gpg --revoke [email]

# Import Revoke Cert:
gpg --import [cert file]

# Import Public Key:
gpg --import [keyfile.pub]

# Sign Public Key:
gpg --sign-key [email or id]

# Export Public Key:
gpg --armor -o [output.pub] --export [email or id]

# Export Private Key:
gpg --armor -o [private.key] --export-secret-keys [email or id]

# Encrypt File:
gpg --encrypt --sign --armor -r [email] [file.txt]

# Decrypt File:
gpg --decrypt -o [output.txt] [source file]

# Clear Sign File:
gpg --clearsign [file]
