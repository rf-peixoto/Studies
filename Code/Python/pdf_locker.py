import getpass
from PyPDF2 import PdfFileWriter, PdfFileReader

# Logo:
print("\033[93m +-+-+-+ +-+-+-+-+")
print(" |\033[00mP\033[93m|\033[00mD\033[93m|\033[00mF\033[93m| |\033[00mL\033[93m|\033[00mO\033[93m|\033[00mC\033[93m|\033[00mK\033[93m|")
print(" +-+-+-+ +-+-+-+-+\n")

# Get file:
target = input(" PDF to protect:\033[00m ")
if not target.endswith(".pdf"):
    print("\033[93m You must select a PDF file.\033[00m")

# Try to open:
try:
    print("\033[93m Reading file.")
    pdf = PdfFileReader(target)
except Exception as error:
    print("\033[93m{0}\033[00m".format(error))

# Writer:
print("\033[93m Preparing to write.")
writer = PdfFileWriter()
for n in range(pdf.numPages):
    writer.addPage(pdf.getPage(n))

# Password:
passwd = getpass.getpass(" Password: ")
writer.encrypt(passwd)

# Export:
with open(target, "wb") as fl:
    writer.write(fl)

print("\033[93m File protected!\033[00m\n")
