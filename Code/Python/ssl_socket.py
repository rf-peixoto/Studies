# Abrindo socket com SSL:
# Client:
import socket
import ssl

hostname = 'www.duckduckgo.com'
context = ssl.create_default_context()

with socket.create_connection((hostname, 443)) as skt:
    with context.wrap_socket(skt, server_hostname = hostname) as sskt:
        print(sskt.version())

# Server:
server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
server_context.load_cert_chain('/path/to/certchain.pem', '/cert/private.key')

with socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0) as sock:
    sock.bind(('127.0.0.1', 8443))
    sock.listen(5)
    with context.wrap_socket(sock, server_side=True) as ssock:
        conn, addr = ssock.accept()
