import hashlib
import getpass

print("Digite sua senha:")
passwd = getpass.getpass()
with open("password.txt", "w") as fl:
    fl.write(hashlib.md5(passwd.encode()).hexdigest())
    fl.close()

