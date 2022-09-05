import PyPDF2
import sys, re

# Open file:
doc = open(sys.argv[1], "rb")

# Generate object:
parser = PyPDF2.PdfFileReader(doc)

# Extract:
emails = []
n_pages = parser.getNumPages()

for i in range(n_pages):
    # Open page:
    page = parser.getPage(i)
    content = page.extractText()
    # Extract:
    tmp = re.findall("([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", content)
    # Save:
    for mail in tmp:
        if mail.lower() not in emails:
            emails.append(mail.lower())

# Close PDF:
doc.close()

# Output:
print("Found {0} address(es) in {1} pages.".format(len(emails), n_pages))
for i in emails:
    print(i)
