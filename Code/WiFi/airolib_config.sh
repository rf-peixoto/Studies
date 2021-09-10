# Configurando airolib para quebra de senhas:

# 1)
# database: Nome do banco de dados
# essids: Wordlist com SSIDs
airolib-ng [database] --import essid [essids]

# 2)
# database: Nome do banco de dados
# passwords: Wordlist de senhas
airolib-ng [database] --import passwd [passwords]

# 3)
# Verificação:
airolib-ng --stats

# 4)
# database: Nome do banco de dados
# --batch: Configurar SSIDs e Senhas no banco de dados.
airolib-ng [database] --batch

# 5)
# database: Nome do banco de dados
# --clean [all]: Verificar se houve erros
airolib-ng [database] --clean all

# 6)
# database: Nome do banco de dados configurado
aircrack-ng -r [airlib database] [arquivo.cap]
