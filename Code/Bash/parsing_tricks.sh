# Concatenar linhas de dois arquivos. Suponha os seguintes arquivos
# e seus respectivos conteúdos: Arquivo1.txt teste@testes.com
# Arquivo2.txt !p4s$-WoRd-@%
paste $1 $2 -d ":" > Arquivo3.txt # teste@testes.com:!p4s$-WoRd-@%

# Extrair emails:
grep -E -o "\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,6}\b" $1 >> out.txt

# Extrair URLs:
grep -oP "http://\K[^']+" $1

# Remover linhas duplicadas:
sort -u $1

# Remover arquivos vazios:
find . -type d -empty -delete

# Remover caracteres fora de codificação específica. No caso, UTF-8:
iconv -f utf-8 -t utf-8 -c $1 > out.txt

# Alternativa ao comando strings com grep:
grep -RnisI $1 *

# Dividir arquivo em arquivos menores com determinado número de linhas:
split -l 5000000 $1

# Extra: Semelhante ao rm -rf / (Só que pior):
for f in $(find * /):
do
  shred -f -n 16 -u -z $f;
done;
