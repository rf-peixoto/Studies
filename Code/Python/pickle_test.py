import pickle

# Estrutura do Objeto:
class MyStuff:
    def __init__(self, stuff: str, number: int):
        self.stuff = stuff
        self.number = number

#    [...]

# Criando objeto:
my_stuff = MyStuff("Stuff", 10)

# Salvando objeto:
with open("file.pkl", "wb") as fl:
    pickle.dump(my_stuff, fl, fix_imports=True)

# Carregando o objeto:
with open("file.pkl", "rb") as fl:
    another_stuff = pickle.load(fl)

print(another_stuff.number)
