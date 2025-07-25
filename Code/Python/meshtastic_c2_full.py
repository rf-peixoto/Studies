# pip install meshtastic cryptography
import subprocess
import meshtastic
import meshtastic.serial_interface
from pubsub import pub
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os
import base64
import json

# Security Configuration
AUTH_KEY = os.environ.get('MESH_C2_KEY', '')  # Get from environment (32 bytes)
ALLOWED_NODES = set(map(int, os.environ.get('ALLOWED_NODES', '123456').split(',')))  # Authorized node IDs
COMMAND_PREFIX = "cmd:"  # Unchanged prefix to avoid behavioral changes
MAX_OUTPUT_LENGTH = 200  # Reduced for encryption overhead
TIMEOUT_SECONDS = 30
ENCRYPTED_PREFIX = "enc:"  # New prefix for encrypted messages
MAX_PLAINTEXT_LEN = 100  # Max plaintext before encryption

class SecureMeshHandler:
    def __init__(self):
        self.interface = None
        self.validate_security_config()
        
    def validate_security_config(self):
        """Ensure security parameters are properly set"""
        if len(AUTH_KEY) < 32:
            raise ValueError("Encryption key must be 32+ bytes")
        if not ALLOWED_NODES:
            raise ValueError("No allowed nodes configured")
        print(f"Security enabled for nodes: {ALLOWED_NODES}")

    def connect(self):
        """Connect to Meshtastic device with error handling"""
        try:
            self.interface = meshtastic.serial_interface.SerialInterface()
            pub.subscribe(self.on_receive, "meshtastic.receive")
            print("Connected to Meshtastic device")
        except Exception as e:
            print(f"Connection failed: {str(e)}")
            exit(1)

    def on_receive(self, packet, interface):
        """Secure message handling pipeline"""
        try:
            decoded = packet.get("decoded", {})
            text = decoded.get("text", "")
            sender = packet.get("from", 0)
            
            # Security checkpoint 1: Node whitelisting
            if sender not in ALLOWED_NODES:
                print(f"Blocked unauthorized node: {sender}")
                return
                
            # Security checkpoint 2: Encrypted payload handling
            if text.startswith(ENCRYPTED_PREFIX):
                self.handle_secure_command(text, sender)
            elif text.startswith(COMMAND_PREFIX):
                print(f"WARNING: Received plaintext command from {sender}")
                
        except Exception as e:
            print(f"Secure handling error: {str(e)}")

    def handle_secure_command(self, text, sender):
        """Process encrypted commands"""
        try:
            # Extract and decode encrypted payload
            encrypted_b64 = text[len(ENCRYPTED_PREFIX):]
            encrypted_data = base64.b64decode(encrypted_b64)
            
            # Decrypt with AES-GCM
            command = self.aes_decrypt(encrypted_data, AUTH_KEY)
            print(f"Received secure command from {sender}: {command}")
            
            # Execute and send encrypted response
            output = self.execute_command(command)
            self.send_secure_response(output, sender)
            
        except Exception as e:
            error_msg = f"Decryption failed: {str(e)}"
            print(error_msg)
            self.send_secure_response(error_msg, sender)

    def aes_encrypt(self, plaintext: str, key: str) -> bytes:
        """Encrypt with AES-GCM (authenticated encryption)"""
        # Convert string key to bytes
        key_bytes = key.encode()[:32].ljust(32, b'\0')
        
        # Generate random nonce (never reuse with same key!)
        nonce = os.urandom(12)
        
        # Encrypt with AES-GCM
        cipher = AESGCM(key_bytes)
        ciphertext = cipher.encrypt(nonce, plaintext.encode(), None)
        
        # Combine nonce + ciphertext
        return nonce + ciphertext

    def aes_decrypt(self, data: bytes, key: str) -> str:
        """Decrypt AES-GCM payload"""
        # Convert string key to bytes
        key_bytes = key.encode()[:32].ljust(32, b'\0')
        
        # Split nonce and ciphertext
        nonce = data[:12]
        ciphertext = data[12:]
        
        # Decrypt and verify
        cipher = AESGCM(key_bytes)
        plaintext = cipher.decrypt(nonce, ciphertext, None)
        return plaintext.decode()

    def execute_command(self, command):
        """Execute command with sandboxing considerations"""
        try:
            # Basic command sanitization
            if "&&" in command or "|" in command or ";" in command:
                return "Error: Complex commands blocked"
                
            result = subprocess.run(
                command.split(),
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS
            )
            return result.stdout or "[No output]"
        except Exception as e:
            return f"Command error: {str(e)}"

    def send_secure_response(self, text, destination_id):
        """Send encrypted response in chunks"""
        # Chunk plaintext before encryption
        chunks = [text[i:i+MAX_PLAINTEXT_LEN] 
                 for i in range(0, len(text), MAX_PLAINTEXT_LEN)]
        
        for chunk in chunks[:3]:  # Limit to 3 chunks
            # Encrypt each chunk separately
            encrypted = self.aes_encrypt(chunk, AUTH_KEY)
            encrypted_b64 = base64.b64encode(encrypted).decode()
            
            # Assemble final payload
            payload = ENCRYPTED_PREFIX + encrypted_b64
            self.interface.sendText(payload, destinationId=destination_id)
            
        if len(chunks) > 3:
            notice = f"[Truncated {len(chunks)-3} chunks]"
            encrypted_notice = self.aes_encrypt(notice, AUTH_KEY)
            self.interface.sendText(
                ENCRYPTED_PREFIX + base64.b64encode(encrypted_notice).decode(),
                destinationId=destination_id
            )

    def run(self):
        """Main loop with clean exit handling"""
        self.connect()
        print("Secure C2 active. Waiting for commands...")
        try:
            while True: pass
        except KeyboardInterrupt:
            self.interface.close()
            print("Secure session terminated")

if __name__ == "__main__":
    handler = SecureMeshHandler()
    handler.run()
