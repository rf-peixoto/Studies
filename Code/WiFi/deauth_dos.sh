# Parâmetros:
# --deauth ou -0: tipo de ataque.
# 0: Número de pacotes. 0 para enviar continuamente.
# -a [MAC] : MAC é o BSSID do alvo.
# [interface] : Interface em modo de monitoramento.

aireplay-ng --deauth 0 -a [MAC]	[interface]
