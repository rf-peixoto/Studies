# Enviar arquivo criptografado:
cat $1 | openssl aes-256-cbc -a -e -pass pass:password | netcat -l -p 8080

# Criar popup em máquina Windows via SMB:
echo "TEXTO" | smbclient -M HOST_WINDOWS

# Criar popup no Gnome:
notify-send ["<Título>"] "Texto"

# Enviar arquivo via icmp com hping:
hping3 $IP --icmp --sign MSGID1 -d 50 -c 1 --file $1

# Monitorar consultas feitas ao MySQL:
watch -n 1 mysqladmin --user=USER --password=PASSWORD processlist

# Listar programas conectados à internet no momento:
lsof -P -i -n | cut -f 1 -d " "| uniq | tail -n +2

# Listar arquivos modificados nos últimos 30 minutos:
# (útil para threat hunting)
sudo find / -mmin 30 -type f

# Encontrar arquivos criados durante determinado período AAAA/MM/DD:
find . -type f -newermt "2022-08-05" ! -newermt "2022-08-09"

# Monitorar o uso de memória.
watch vmstat -sSM

# Enviar comando para vários hosts conectados:
<COMANDO> | tee >(ssh hosta) >(ssh hostb) >(ssh hostc)

# Alternativa ao man para  buscar informações sobre binário:
wtf $1 # Ex: wtf ssh -> SSH: secure shell

# Fechar shell, mantendo os processos em background:
disown -a && exit

# Transforme o último comando em um script:
echo "!!" > script.sh

# Mate o processo que está travando um arquivo (Ex: Antivírus):
fuser -k $1

# Copiar permissões do arquivo 1 para arquivo 2:
chmod --reference $1 $2

# Checar data de validade de certificados ssl.
# (Ex: para monitorar possibilidade de hijacking)
echo | openssl s_client -connect <url>:443 2>/dev/null | openssl x509 -dates -noout

# Incluir timestamp no histórico do bash:
export HISTTIMEFORMAT="%F %T "

# Grep em PDF:
pdftotext $1 | grep <filtros>

# Desligar tela (para sacanear a turma do blue team :v )
xset dpms force standby

# Checar IPv4 externo:
curl iifconfig.me
