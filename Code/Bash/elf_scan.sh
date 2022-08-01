# Informações gerais:
file $1 
# Tamanho:
du -h $1 || ls -lh $1
# Número de linhas:
wc -l $1
# Dependências de shared object (file.so)
ldd $1 
# Bibliotecas:
ltrace $1
# Hexdump:
hexdump $1
# Extrair strings:
strings $1 
# Extrair informações detalhadas:
readelf $1
# Extrair informações e/ou fazer disassembly:
objdump $1
# Extrair system calss:
strace $1
# Extrair symbols do assembly:
nm $1 
# Debug:
gdb $1
# Interceptar pacotes:
tcpdump 
# Executáveis embutidos:
binwalk
# Analisar memória:
volatility
