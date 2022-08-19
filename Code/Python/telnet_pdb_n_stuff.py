# Interagindo com Telnet:
from telnetlib import Telnet

with Telnet('localhost', 23) as telnet_conn:
    telnet_conn.interact()

# Python tem um debugger embutido.
# O módulo 'secrets' é um exemplo de uso.
# Ex: pdb.run(classe.função())
import pdb
import secrets
pdb.run(secrets.token_urlsafe(16))

# Scrappy sem BeautifulSoup:
import urllib.request

req = urllib.request('https://website.com')

# Extrair módulos importados por script.
# Ex: Para análise de malware/shellcode/forense:
from modulefinder import ModuleFinder
import sys # sys.argv[1] = arquivo_à_analisar.py

finder = ModuleFinder()
finder.run_script(sys.argv[1])

print('Loaded modules:')
for name, mod in finder.modules.items():
    print('%s: ' % name, end='')
    print(','.join(list(mod.globalnames.keys())[:3]))
