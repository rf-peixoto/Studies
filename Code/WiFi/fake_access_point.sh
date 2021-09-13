# Configurar DHCP previamente.
# Manter placa em modo de monitoramento.
#
# -c: Canal
# -e: Nome da rede
# [interface] : Interface em monitoramento

airbase-ng -c [CH] -e [SSID] [interface]

# Ativar rede usando configurações DHCP:
# ip: range de ip
systemctl restart isc-dhcp-server

ifconfig at0 [IP] netmask 255.255.255.0 up
