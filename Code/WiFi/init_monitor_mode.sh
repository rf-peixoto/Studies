# Coloca a interface em modo de monitoramento:
# $1 : Interface

ifconfig $1 down
iwconfig $1 mode Monitor
ifconfig $1 up
