# Em algumas versões do Linux, é necessário realizar configuraçõess extras:
# Abrir: /etc/NetworkManager/NetworkManager.conf
# Se não houver, adicionar linhas:
#[device]
#wifi.scan-rand-mac-address=no

#[connection]
#ethernet.cloned-mac-address=preserve
#wifi.cloned-mac-address=preserve

## Ataque ##

# 1) Monitorar rede para identificar MACs conectados.
ifconfig [interface] down # Desligar para alterar Endereço MAC
# -r: Endereço aleatório
# -p: Restaura MAC original
macchanger -r [interface]
# Alterar:
macchanger -m [Novo MAC] [interface]
