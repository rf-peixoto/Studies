# https://pypi.org/project/qrcode/
import qrcode

# Create Object
qr = qrcode.QRCode(version=1,
                   error_correction=qrcode.constants.ERROR_CORRECT_L,
                   box_size=10,
                   border=4)

# Get data:
data = input("Enter your data: ")
filename = input("QR Code filename: ")

# Generate
qr.add_data(data)
qr.make(fit=True)
# Colors and Image:
img = qr.make_image(fill_color="black", back_color="white")

# Saving:
with open(filename, "wb") as image:
    img.save(image)

# Ending.
print("Done.")
