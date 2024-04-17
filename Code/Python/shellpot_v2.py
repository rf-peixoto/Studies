import socket
import datetime
import sys

# Main
def simulate_shell(port):
    # Socket setup
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('0.0.0.0', port))
    server_socket.listen(5)
    print(f"[+] Listening on port {port}...")

    try:
        while True:
            client_socket, client_address = server_socket.accept()
            print(f"  > Connection received from {client_address[0]}")
            log_command(client_address[0], "connection opened")
            # Send banner
            client_socket.send(b"Welcome! You are on PrivateServer v3.7.12\n")

            try:
                while True:
                    command = client_socket.recv(1024).decode('utf-8').strip()
                    if not command:
                        continue
                    # Log the command
                    log_command(client_address[0], command)
                    # Command processing
                    if command == 'exit':
                        client_socket.send(b"Goodbye!\n")
                        log_command(client_address[0], "connection closed")
                        client_socket.close()
                        break
                    response = handle_command(command)
                    client_socket.send(response.encode('utf-8') + b'\n')
            except socket.error:
                client_socket.close()
    except KeyboardInterrupt:
        print("[-] Server is shutting down.")
    finally:
        server_socket.close()
        print("[-] All connections closed.")

# Handle commands
def handle_command(command):
    # There is a bug on echo that could expose your honey pot. 'echo' without args will result in not found
    if command.startswith('echo '):
        return command[5:]
    elif command == 'whoami':
        return 'server'
    elif command == 'id' or command == 'uid':
        return 'uid=1000(server) gid=1000(server) groups=1000(server)'
    elif command == 'pwd':
        return '/home/server/'
    elif command == 'sudo' or command == 'ls' or command == 'cd' or command == 'mkdir' or command == 'sh' or command == 'wget':
        return 'Permission denied'
    else:
        return "command '{0}' not found".format(command.split(' ')[0])

# Log
def log_command(ip, command):
    with open("honeypot.log", "a") as log_file:
        timestamp = datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        log_file.write(f"{timestamp}|{ip}|{command}\n")

# Start
simulate_shell(int(sys.argv[1]))
