from stegano import lsb

def codify():
    archive = input("Digite o nome do arquivo, incluindo extensão: ")
    msg = input("Digite a mensagem a ser inserida: ")
    try:
        secret = lsb.hide(archive, msg)
        secret.save("secret-" + archive)
        print("Sucesso!\n")
    except Exception as error:
        print("Ocorreu um erro!")
        print(error)

def decodify():
    archive = input("Digite o nome do arquivo, incluindo extensão: ")
    msg = ""
    try:
        msg = lsb.reveal(archive)
        print("Mensagem encontrada:\n" + msg + "\n")
    except Exception as error:
        print("Erro. Nenhuma mensagem identificada.")


while True:
    print("\nDigite [c] para criptografar imagem.")
    print("Digite [d] para decodificar arquivo.")
    print("Digite [f] para fechar o programa.")
    option = input(">>> ")
    if option in "Cc":
        codify()
    elif option in "Dd":
        decodify()
    elif option in "Ff":
        break
    else:
        print("Entrada incorreta.")

input("Finalizando. Pressione [enter] para sair.")

