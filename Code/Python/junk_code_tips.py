# Utilizando operações básicas de forma não ortodoxa só pra sacanear analistas.
# Exempĺos em Python, mas a ideia é genérica:
# Operações básicas:
x - -y # Soma. Ex: 1 - -2 = 3
x + -y # Subtração, o inverso da anterior.
x * 0.y # Divisão. Ex: 10 * 0.5 = 5 (Essa operação é mais eficiente que 10 / 2, já que o operador '/' é mais custoso em termos de processamento.

# Usar bytes de um valor como operadores booleanos:
x = bin(4) # 0b100
if x[2] == "1":
    ...
elif x[-1] == "0":
    ...

# Declarando valores com *junk code* junto. Depois de compilado, isso vira um bloco inteiro:
x = "Valor falso" if False else "Valor real"
# O mesmo usando list comprehension:
x = [x // 4 for x in range(ord('2')) if x % 2 == 0][20] # x = 10

# Condição irrelevante:
if True:
    ...

# Código irrelevante:
(if False) ou  (while False):
    ...
