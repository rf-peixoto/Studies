# Import:
from cryptography.fernet import Fernet

# Generate key:
new_key = Fernet.generate_key()
key = Fernet(new_key)
print("New key generated.")

# Get plain text:
file = input("Filename: ")
with open(file, "rb") as fl:
    data = fl.read()
print("Original data readed.")

# Encrypt:
token = key.encrypt(data)
with open("dead_{0}".format(file), "wb") as fl:
    fl.write(token)
print("Dead file created.")

# Decrypt
with open("dead_{0}".format(file), "rb") as fl:
    token_data = fl.read()
clean = key.decrypt(token_data)
print("Dead data readed.")


with open("saved_{0}".format(file), "wb") as fl:
    fl.write(clean)
print("Data recovered.")
