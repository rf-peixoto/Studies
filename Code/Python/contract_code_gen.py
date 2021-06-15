import os
import qrcode
import secrets
from random import randint

# Get data:

date = input("Data: 00-00-00 ")
client = input("Email do Destinatário: ").lower()
coin = input("Moeda: ").upper()
amount = input("Quantidade/valor: ")

# Generate unique code:

f_label = secrets.token_urlsafe(8)
s_label =  str(randint(0, 999)).zfill(4)
t_label = secrets.token_urlsafe(8)

unique_code = f_label + "-" + s_label + "-" + t_label

compile_string = """Data: {0}
Remetente: EMAIL
Destinatário: {1}
Moeda: {2}
Valor: {3}
Identificador: {4}""".format(date, client, coin, amount, unique_code)

# Create QR Code:
qr = qrcode.QRCode(version=None, # Int: 1 to 40 that controls the size of the img. Set to None and use the fit parameter when making the code to determine this automatically.
                   error_correction=qrcode.constants.ERROR_CORRECT_L,
                   box_size=10,
                   border=4)
# Generate
qr.add_data(compile_string)
qr.make(fit=True)
# Colors and Image:
img = qr.make_image(fill_color="black", back_color="white")

# Saving:
with open("Recibo_{0}_{1}.png".format(date, unique_code), "wb") as image:
    img.save(image)

# Ending.
print("Done.")
