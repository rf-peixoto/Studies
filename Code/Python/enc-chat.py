#!/usr/bin/env python3
# secure_chat_enhanced.py: Encrypted real-time chat with full conversation history
# Usage:
#   Server: ./secure_chat_enhanced.py server <PORT> <PASSWORD>
#   Client: ./secure_chat_enhanced.py client <SERVER_IP> <PORT> <PASSWORD>

import sys
import socket
import threading
import time
from datetime import datetime
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os

class EnhancedSecureChat:
    def __init__(self, mode, host, port, password):
        self.mode = mode
        self.host = host
        self.port = port
        self.password = password
        self.conn = None
        self.running = True
        self.cipher = self.create_cipher()
        self.messages = []
        self.username = self.get_username()
        self.friend_username = "Friend"
        
        # Setup socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        if self.mode == "server":
            self.sock.bind(('0.0.0.0', self.port))
            self.sock.listen(1)
            print(f"[*] Server running on port {self.port}. Waiting for connection...")
            self.conn, addr = self.sock.accept()
            print(f"[+] Connected to {addr[0]}:{addr[1]}")
            # Exchange usernames
            self.send_username()
            self.receive_username()
        else:
            print(f"[*] Connecting to {self.host}:{self.port}...")
            self.sock.connect((self.host, self.port))
            self.conn = self.sock
            print("[+] Connection established")
            # Exchange usernames
            self.receive_username()
            self.send_username()
        
        # Clear screen and show initial UI
        self.clear_screen()
        self.print_ui()
        
        # Start receiver thread
        self.receive_thread = threading.Thread(target=self.receive_messages)
        self.receive_thread.daemon = True
        self.receive_thread.start()
        
        # Start sender loop
        self.send_loop()

    def clear_screen(self):
        """Clear terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def get_username(self):
        """Prompt user for username"""
        username = input("Enter your username: ")
        return username.strip() or "User"

    def send_username(self):
        """Send username to peer"""
        encrypted = self.cipher.encrypt(self.username.encode()) + b"\n"
        self.conn.sendall(encrypted)

    def receive_username(self):
        """Receive peer's username"""
        data = b""
        while b"\n" not in data:
            chunk = self.conn.recv(1024)
            if not chunk:
                break
            data += chunk
        
        if data:
            try:
                self.friend_username = self.cipher.decrypt(data.strip()).decode()
            except:
                self.friend_username = "Friend"

    def create_cipher(self):
        """Derive encryption key from password"""
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
        print("\n" + "=" * 60)
        print(f"Secure Chat: {self.username} ↔ {self.friend_username}".center(60))
        print(f"Encryption: AES-256 | Port: {self.port}".center(60))
        print("=" * 60)
        print("Type your message and press ENTER to send")
        print("Type /quit to exit\n")
        print("-" * 60)
        
        # Print existing messages
        for timestamp, sender, message in self.messages:
            prefix = f"\033[1;32m{self.username}:\033[0m" if sender == "self" else f"\033[1;34m{self.friend_username}:\033[0m"
            print(f"{timestamp} {prefix} {message}")
        
        print("-" * 60)

    def add_message(self, sender, message):
        """Add message to history with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.messages.append((timestamp, sender, message))
        
        # Clear last 4 lines and reprint UI
        if len(self.messages) > 0:
            sys.stdout.write("\033[F\033[K")  # Move up and clear line
            sys.stdout.write("\033[F\033[K")  # Clear separator
            sys.stdout.write("\033[F\033[K")  # Clear previous message
        
        # Print new message
        prefix = f"\033[1;32m{self.username}:\033[0m" if sender == "self" else f"\033[1;34m{self.friend_username}:\033[0m"
        print(f"{timestamp} {prefix} {message}")
        
        # Reprint separator and prompt
        print("-" * 60)
        sys.stdout.write("You: ")
        sys.stdout.flush()

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
                        self.add_message("friend", decrypted)
                    except:
                        # Handle decryption errors
                        pass
            except (ConnectionResetError, BrokenPipeError):
                break
            except Exception as e:
                print(f"\n[!] Error: {str(e)}")
                break
                
        print("\n[!] Connection closed")
        self.running = False

    def send_loop(self):
        """Main loop to handle user input and sending"""
        try:
            while self.running:
                sys.stdout.write("You: ")
                sys.stdout.flush()
                msg = sys.stdin.readline().strip()
                
                if not self.running:
                    break
                    
                if not msg:
                    continue
                    
                if msg.lower() == "/quit":
                    self.running = False
                    break
                
                # Add to local history
                self.add_message("self", msg)
                
                # Encrypt and send message
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
        print("  Server: ./secure_chat_enhanced.py server <PORT> <PASSWORD>")
        print("  Client: ./secure_chat_enhanced.py client <SERVER_IP> <PORT> <PASSWORD>")
        sys.exit(1)
        
    mode = sys.argv[1]
    host = "0.0.0.0" if mode == "server" else sys.argv[2]
    port = int(sys.argv[2] if mode == "server" else sys.argv[3])
    password = sys.argv[3] if mode == "server" else sys.argv[4]
    
    chat = EnhancedSecureChat(mode, host, port, password)
