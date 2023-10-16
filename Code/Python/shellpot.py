import socket
import datetime
import sys

def handle_client(client_socket, addr):
    while True:
        command = client_socket.recv(1024).decode('utf-8').strip()
        if command.lower() == 'exit':
            client_socket.close()
            return
        log_entry = f"{datetime.datetime.now()}|{addr[0]}|{command}\n"
        with open("honeypot.log", "a") as log_file:
            log_file.write(log_entry)
        client_socket.send("{0}: command not found\n".format(command.split(" ")[0]).encode())

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('0.0.0.0', int(sys.argv[1])))
    server.listen()
    
    print("[*] Listening on 0.0.0.0:{0}".format(sys.argv[1]))

    while True:
        client_socket, addr = server.accept()
        print(f"[*] Accepted connection from: {addr[0]}:{addr[1]}")
        handle_client(client_socket, addr)

if __name__ == "__main__":
    main()
