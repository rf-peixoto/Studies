# 1) Monitoramento.
# 2) Coletar redes com airodump-ng e capturar
#    pacotes com IVs.

# -n [tamanho da chave]
# wordlist: ex: rockyou

aircrack-ng -a 1 -n 128 -w [wordlist] [arquivo.cap]
