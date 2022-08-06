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
