import PyPDF2
import sys

doc = open(sys.argv[1], "rb")
parser = PyPDF2.PdfFileReader(doc)
page = parser.getPage(0)

print(page.extractText())

doc.close()
