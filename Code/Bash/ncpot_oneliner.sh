nc -lk -p 3000 -e /bin/bash -c 'while read -r line; do echo "$(date \'+%Y-%m-%d %H:%M:%S\')|$(echo $SSH_CLIENT | awk \'{ print $1 }\')|$line" >> honeypot.log; echo "Command not found."; done'
