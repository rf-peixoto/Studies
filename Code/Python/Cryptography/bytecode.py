# ======================================== #
# Bytecode Translator
# ---------------------------------------- #
# v0.1.0
# ======================================== #
import sys

# Argumentos
mode = sys.argv[1] # bta | atb
txt = sys.argv[2] # String

# Métodos
def ascii_to_hex(string: str) -> str:
    # Converte texto ASCII para bytecode
    temp_str = []
    for char in string:
        temp_str.append(str(hex(ord(char)))[2::])
        #print((str(hex(ord(char)))[2::]), end = " ")
        code = ""
        for i in temp_str:
            code += i + " "
    return code

def hex_to_ascii(byte_list: str) -> str:
    # Converte bytecode para texto em ASCII
    temp_char = ""
    temp_string = ""
    for b in byte_list.split(" "):
        temp_char = "0x" + str(b)
        temp_string += chr(int(temp_char, 16))
    return temp_string

# Execução:
if mode == "atb":
    print(ascii_to_hex(txt))
elif mode == "bta":
    print(hex_to_ascii(txt))
