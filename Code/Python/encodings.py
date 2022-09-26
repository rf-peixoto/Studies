import base64

x = "Hello world".encode()

print("String:\tHello World\n")

print("Base16:\t\t{0}".format(base64.b16encode(x).decode()))
print("Base32:\t\t{0}".format(base64.b32encode(x).decode()))
print("Base32Hex:\t{0}".format(base64.b32hexencode(x).decode()))
print("Base64:\t\t{0}".format(base64.b64encode(x).decode()))
print("Base64 URLSAFE:\t\t{0}".format(base64.urlsafe_b64encode(x).decode()))
print("A85:\t\t{0}".format(base64.a85encode(x).decode()))
print("Base85:\t\t{0}".format(base64.b85encode(x).decode()))
