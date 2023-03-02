import sys

def encode(string: str) -> list:
    tmp = []
    for c in string:
        tmp.append("k" * ord(c))
    tmp_phrase = ""
    for i in tmp:
        tmp_phrase += i + " "
    return tmp_phrase

def decode(chr_list: str) -> str:
    tmp = ""
    for snippet in chr_list.split(" "):
        tmp += chr(len(snippet))
    return tmp

option = sys.argv[1]
data = sys.argv[2]

if option.lower() == "-e":
    print(encode(data))
elif option.lower() == "-d":
    print(decode(data))
