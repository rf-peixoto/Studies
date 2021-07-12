def turn_to_hex(string: str) -> str:
    tmp = ""
    for c in string:
        tmp += "\\" + hex(ord(c))
    return tmp

def hex_to_ascii(string: str) -> str:
    tmp = ""
    prepare = string.split("\\")
    prepare.pop(0)
    for c in prepare:
        try:
            tmp += chr(int(c, 16))
        except Exception as error:
            print(error)
            continue
    return tmp
