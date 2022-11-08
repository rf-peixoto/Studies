from string import ascii_letters
from string import digits
from string import punctuation
from urllib.parse import quote_plus

class Sanitizer:
    def __init__(self):
        print("Staring sanitization module.")

    def clean(self, data: str) -> str:
        tmp = ""
        for c in data:
            if c in ascii_letters or c in digits:
                tmp += c
            elif c in punctuation or c == " ":
                tmp += quote_plus(c)
        return tmp
