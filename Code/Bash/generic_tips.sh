# Enviar saída do microfone para áudio de máquina externa:
arecord -f dat | ssh user@host aplay -f dat

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
curl ifconfig.me

# Você pode usar padrões ao passar uma url para o curl:
# Exemplos tirados direto do man curl
curl "http://sub.{domain1,domain2,domain3}.com"
curl "ftp://ftp.domain.com/file[1-99].txt"
curl "http://domain.com/logs/[a-z].txt"

# Para visualizar headers ao usar o wget use o argumento --debug
# O --max-redirect é pra evitar ruídos de redirecionamento.
wget --max-redirect 0 --debug $1

# O framework do metasploit vem com dois programas
# para análise de binários:
msfelfscan || msfpescan
msfbinscan # Misto, podendo analisar vários tipos.

# É comum deixarmos o netcat aguardando uma conexão para enviar
# um comando automaticamente. Porém, se o socket for descoberto,
# alguém pode injetar comandos ao manipular a conexão. Evite isto
# fazendo com que o netcat ignore dados recebidos:
nc --send-only [...]

# Tornar arquivo imutável / impedir edições:
sudo chattr +i $1

# Enviar mensagens para outros usuários da máquina:
wall "Texto"

# Executar um comando quando um arquivo for modificado:
while inotifywait -e modify /pathto/file; do [COMMAND]; done

# Descobrir modelo da máquina:
sudo dmidecode | grep Product

# Verificar se há outros sistemas instalados na máquina:
sudo os-prober

# Alternativa ao traceroute || ping:
mtr $1

# Visualizar árvore de processos ativos:
tree || pstree

# Colocar um espaço antes de um comando faz com
# que eles não sejam registrados no histórico:
 echo "Find me if you can."

# Visualizar metadados de arquivo. (permissões, tamanho, data de criação, etc)
stat $1

# Executar comando em determinado horário:
# Ex: ping 8.8.8.8 at midnight
[COMMDAND] at [TIME]

# Consultar dados geográficos de IP:
curl ipinfo.io

# Filtrar arquivos por usuário:
find . -user $1

# Filtrar processos por usuário:
ps -LF -u $1

# Testar servidor SMTP:
swaks --to [EMAIL] # --server smtp.gmail.com

# Checar registros SSL:
sslscan domain.com:443 || sslyzer domain.com
