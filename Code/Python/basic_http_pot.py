import socket
import threading
from collections import defaultdict
from time import time

# Function to log data to a file
def log_to_file(logfile, message):
    with open(logfile, 'a') as f:
        f.write(f"{message}\n")

# Global variable to track IP connections
ip_connections = defaultdict(list)

def handle_client(client_socket, client_address, buffer_size, logfile, rate_limit):
    ip, _ = client_address
    current_time = time()

    # Check rate limit
    if len(ip_connections[ip]) >= rate_limit:
        log_to_file(logfile, f"Rate limit exceeded for {ip}. Blocking connection.")
        client_socket.close()
        return

    ip_connections[ip].append(current_time)
    ip_connections[ip] = [t for t in ip_connections[ip] if current_time - t < 60]  # 60 seconds window

    log_to_file(logfile, f"Connection from {client_address}")

    request = client_socket.recv(buffer_size)
    log_to_file(logfile, f"Received: {request.decode('utf-8')}")

    first_line = request.split(b'\n')[0]
    url = first_line.split(b' ')[1]
    http_pos = url.find(b"://")
    temp = url[(http_pos+3):] if http_pos != -1 else url
    port_pos = temp.find(b":")
    webserver_pos = temp.find(b"/")
    if webserver_pos == -1:
        webserver_pos = len(temp)
    webserver = temp[:webserver_pos] if port_pos == -1 or webserver_pos < port_pos else temp[:port_pos]
    port = 80 if port_pos == -1 else int(temp[(port_pos+1):][:webserver_pos-port_pos-1])

    log_to_file(logfile, f"Forwarding request to {webserver}:{port}")

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((webserver, port))
        s.sendall(request)

        while True:
            data = s.recv(buffer_size)
            if len(data) > 0:
                log_to_file(logfile, f"Received data from {webserver}:{port}")
                log_to_file(logfile, data.decode('utf-8', 'ignore'))
                client_socket.send(data)
            else:
                break
    except Exception as e:
        log_to_file(logfile, f"Error: {e}")
    finally:
        client_socket.close()

def main():
    # Setup Section
    listen_port = 9999
    max_connections = 5
    buffer_size = 1024
    logfile = "proxy_log.txt"
    rate_limit = 10  # Max connections per minute per IP

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("0.0.0.0", listen_port))
    server.listen(max_connections)
    log_to_file(logfile, f"Listening on port {listen_port}")

    while True:
        client_socket, addr = server.accept()
        client_thread = threading.Thread(target=handle_client, args=(client_socket, addr, buffer_size, logfile, rate_limit))
        client_thread.start()

if __name__ == "__main__":
    main()
