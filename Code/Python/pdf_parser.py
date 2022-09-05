import PyPDF2

doc = open"File.pdf", "rb")
parser = PyPDF2.PdfFileReader(doc)

print(parser.pdf_header)
print(parser.documentInfo)
print(parser.is_encrypted)

for i in parser.getNumPages():
    page = parser.getPage(i)
    print(page.extractText())

doc.close()
