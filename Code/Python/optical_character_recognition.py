import sys
import pytesseract
from PIL import Image

try:
    image = Image.open(sys.argv[1])
except Exception as error:
    print(error)

text = pytesseract.image_to_string(image)

print(text)
