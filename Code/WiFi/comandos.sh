# Administração da interface:
iwconfig

# Informações gerais sobre a(s) interface(s):
ifconfig

# iwlist : Informações sobre (ou acessiveis à) interface:

iwlist [interface] channel
iwlist [interface] scanning | grep ESSID
iwlist [interface] scanning | egrep "ESSID|Channel:|Address:"

# Monitoramento com tcpdump:
tcpdump -vv -i [interface] -n # Incluir opção -c [número] para limitar quantidade de pacotes. Ex: -c 10

# Monitoramento com airmon-ng:
airmon-ng start	[interface]
airmon-ng stop [interface]

# Em caso de falha, finalizar antes processos que impedem o modo de monitoramento com:
airmon-ng check	kill

# Em monitoramento, visualize o tráfego com:
airodump-ng [interface monitorando]

# Para travar monitoramento em canal específico:
# Utilizar opção -w [nome do arquivo] para gerar arquivo.cap
airodump-ng --channel [canal] --essid [SSID (Nome da Rede)] [interface]

# "Quebrando" criptografia com chave compartilhada:
# -w : Opção para criptografia wep. Ver --help.
airdecap-ng -w [chave] [arquivo.cap]


# Ataque WEP SKA:
# 1) Iniciar monitoramento.
# 2) Conseguir dados da rede alvo. (-w para salvar)
# 3) Capturar arquivo XOR forçando com ataque DeAuth
# 4) Gerar autenticação falsa.
