# Este começou como um gerador de senhas.
# Percebi que a probabilidade de ele acertar qualquer
# uma é mínima, então serve como um gerador de
# strings aleatórias para qualquer motivo necessário.


from secrets import randbelow
import string

# Settings:
size = int(input("Password size: ")) # Número de caracteres da senha.
pass_number = int(input("Number of passwords: ")) # Número de senhas.
unique = input("Unique values? <y/n> ") # y: Não aceitar senhas duplicadas no resultado.
file_name = input("Name your file: ") # Nome-do-arquivo sem extensão.

# Character List:
char_list = string.ascii_letters + string.digits + ".~_!@#$%&*"

# Variables used:
pass_list = []
temp_string = ""
n = 0

# Start loop:
while n < pass_number:
    if len(temp_string) < size:
        character = char_list[randbelow(len(char_list))]
        temp_string += character
    else:
        if unique == "y":
            if temp_string not in pass_list:
                pass_list.append(temp_string)
        else:
            pass_list.append(temp_string)    
        print(temp_string)
        temp_string = ""
        n += 1

# Create File:
with open(file_name + ".txt", "w") as file:
    index = 0
    for i in pass_list:
        file.write(str(i) + "\n")
    file.close()

input("\nDone. Press anything to exit.")


