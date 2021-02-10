import secrets
from Crypto.Cipher import AES

# ======================================================================================================
key = bytes(secrets.token_urlsafe(12).encode("utf-8")) # Generate a 16bytes key (including b and "")
cipher = AES.new(key, AES.MODE_EAX) # Create object
nonce = cipher.nonce
tag = ""
# ======================================================================================================

def encrypt_file(filename: str) -> str:
    """ Encrypt the file """
    print("Your key is: {0}".format(key))
    with open(filename, "rb") as target:
        filedata = target.read() #Read file bytes
        target.close()
    encrypted_data, tag = cipher.encrypt_and_digest(filedata) # Encrypt they
    with open(filename, "wb") as target:
        target.write(encrypted_data) # Overwrite file
        target.close()
    print("Your target was encrypted!")
    print("Tag: {0}".format(tag)) # Just for checking


# ======================================================================================================

def decrypt_file(filename: str) -> str:
    with open(filename, "rb") as target: # Decrypt data
        filedata = target.read()
        cipher = AES.new(key, AES.MODE_EAX, nonce=nonce)
        decoded_data = cipher.decrypt(filedata)
        verify = input("Verify? <y/n>\n>>> ") # <wip>
        if verify in "Yy":
            try: # Verify
                cipher.verify(tag)
                print("Your file is authentic.")
            except ValueError:
                print("Incorrect or corrupted key.") # </wip>
        target.close()
    with open(filename, "wb") as target: # Saves original content
        target.write(decoded_data)
        target.close()


