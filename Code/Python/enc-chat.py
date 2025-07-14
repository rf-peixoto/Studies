#!/usr/bin/env python3
# secure_chat.py: Encrypted real-time chat with a clean interface
# Usage:
#   Server: ./secure_chat.py server <PORT> <PASSWORD>
#   Client: ./secure_chat.py client <SERVER_IP> <PORT> <PASSWORD>

import sys
import socket
import threading
import time
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

class SecureChat:
    def __init__(self, mode, host, port, password):
        self.mode = mode
        self.host = host
        self.port = port
        self.password = password
        self.conn = None
        self.running = True
        self.cipher = self.create_cipher()
        
        # Setup socket based on mode
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        if self.mode == "server":
            self.sock.bind(('0.0.0.0', self.port))
            self.sock.listen(1)
            print(f"[*] Server running on port {self.port}. Waiting for connection...")
            self.conn, addr = self.sock.accept()
            print(f"[+] Connected to {addr[0]}:{addr[1]}")
        else:
            print(f"[*] Connecting to {self.host}:{self.port}...")
            self.sock.connect((self.host, self.port))
            self.conn = self.sock
            print("[+] Connection established")
        
        # Start threads
        self.receive_thread = threading.Thread(target=self.receive_messages)
        self.receive_thread.daemon = True
        self.receive_thread.start()
        
        self.print_ui()
        self.send_loop()

    def create_cipher(self):
        """Derive encryption key from password using PBKDF2"""
        salt = b'secure_chat_salt'  # Fixed salt for simplicity
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.password.encode()))
        return Fernet(key)

    def print_ui(self):
        """Print the chat interface"""
        print("\n" + "=" * 50)
        print(f"Secure Chat ({self.mode.capitalize()} Mode)".center(50))
        print(f"Encryption: AES-256".center(50))
        print("=" * 50)
        print("Type your message and press ENTER to send")
        print("Type /quit to exit\n")
        print("-" * 50)

    def receive_messages(self):
        """Thread to receive and decrypt incoming messages"""
        buffer = b""
        while self.running:
            try:
                data = self.conn.recv(1024)
                if not data:
                    break
                    
                buffer += data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        decrypted = self.cipher.decrypt(line).decode()
                        # Move cursor up to rewrite input line
                        sys.stdout.write("\033[F\033[K")  # Move up and clear line
                        print(f"\033[94m[Friend]\033[0m {decrypted}")  # Blue text
                        sys.stdout.write("You: ")
                        sys.stdout.flush()
                    except:
                        sys.stdout.write("\033[F\033[K")  # Move up and clear line
                        print("\033[91m[Error] Bad message received\033[0m")  # Red text
                        sys.stdout.write("You: ")
                        sys.stdout.flush()
            except (ConnectionResetError, BrokenPipeError):
                break
            except BlockingIOError:
                time.sleep(0.1)
                
        print("\n[!] Connection closed")
        self.running = False

    def send_loop(self):
        """Main loop to handle user input and sending"""
        try:
            while self.running:
                msg = input("You: ")
                if not self.running:
                    break
                    
                if msg.lower() == "/quit":
                    self.running = False
                    break
                    
                try:
                    encrypted = self.cipher.encrypt(msg.encode()) + b"\n"
                    self.conn.sendall(encrypted)
                except (BrokenPipeError, ConnectionResetError):
                    print("\n[!] Connection lost")
                    break
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources"""
        self.running = False
        self.conn.close()
        self.sock.close()
        print("\n[+] Secure chat session ended")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage:")
        print("  Server: ./secure_chat.py server <PORT> <PASSWORD>")
        print("  Client: ./secure_chat.py client <SERVER_IP> <PORT> <PASSWORD>")
        sys.exit(1)
        
    mode = sys.argv[1]
    host = "0.0.0.0" if mode == "server" else sys.argv[2]
    port = int(sys.argv[2] if mode == "server" else sys.argv[3])
    password = sys.argv[3] if mode == "server" else sys.argv[4]
    
    chat = SecureChat(mode, host, port, password)
