# Desativa uma interface para alterar seu canal,reativando-a depois:
# $1 : Interface  $2 : Novo canal
ifconfig $1 down
iwconfig $1 channel $2
ifconfig $1 up
