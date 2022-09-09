import socket

# -------------------------------------------- #
# Setup
# -------------------------------------------- #
SKT_ADDRESS = ("127.0.0.1", 1337)

# Payload:
data = "".encode()

# -------------------------------------------- #
# Start
# -------------------------------------------- #
if __name__ == "__main__":
    skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # Change to IPv6
    skt.bind(SKT_ADDRESS)
    # Start:
    skt.listen()
    print("[*] Waiting for connections...")
    conn, addr = skt.accept()
    # Send data:
    print("[*] Sending data...")
    conn.send(data)
    # Close connection:
    conn.close()
