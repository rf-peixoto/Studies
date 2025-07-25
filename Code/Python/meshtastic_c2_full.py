# pip install meshtastic cryptography
import subprocess
import meshtastic
import meshtastic.serial_interface
from pubsub import pub
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes, hmac
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import os
import base64
import json
import time
import re

# Security Configuration - Set via environment variables
SECRET_SEED = os.environ.get('MESH_C2_SECRET', '')  # Base secret for key derivation
ALLOWED_NODES = set(map(int, os.environ.get('ALLOWED_NODES', '123456').split(',')))  # Authorized nodes
COMMAND_PREFIX = "cmd:"  # Unchanged for behavioral consistency
ENCRYPTED_PREFIX = "enc:"  # Encrypted payload prefix
MAX_OUTPUT_LENGTH = 180  # Reduced for crypto overhead
TIMEOUT_SECONDS = 30
MAX_PLAINTEXT_LEN = 100  # Max plaintext before encryption
NONCE_SIZE = 12  # AES-GCM nonce size
SALT_SIZE = 16   # Key derivation salt size

class SecureMeshHandler:
    def __init__(self):
        self.interface = None
        self.node_keys = {}  # {node_id: derived_key}
        self.command_nonces = {}  # {node_id: set(used_nonces)}
        self.validate_security_config()
        
    def validate_security_config(self):
        """Ensure security parameters are properly set"""
        if not SECRET_SEED or len(SECRET_SEED) < 16:
            raise ValueError("Secret seed must be 16+ characters")
        if not ALLOWED_NODES:
            raise ValueError("No allowed nodes configured")
        
        # Initialize per-node nonce tracking
        for node in ALLOWED_NODES:
            self.command_nonces[node] = set()
        
        print(f"Security enabled for nodes: {ALLOWED_NODES}")

    def derive_node_key(self, node_id):
        """Derive unique key for each node using PBKDF2"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=f"mesh-c2-node-{node_id}".encode(),
            iterations=100000,
        )
        return kdf.derive(SECRET_SEED.encode())

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
            else:
                print(f"WARNING: Received unencrypted message from {sender}")
                
        except Exception as e:
            print(f"Secure handling error: {str(e)}")

    def handle_secure_command(self, text, sender_id):
        """Process encrypted commands with full security validation"""
        try:
            # Extract and decode encrypted payload
            encrypted_b64 = text[len(ENCRYPTED_PREFIX):]
            encrypted_data = base64.b64decode(encrypted_b64)
            
            # Get node-specific key
            if sender_id not in self.node_keys:
                self.node_keys[sender_id] = self.derive_node_key(sender_id)
            node_key = self.node_keys[sender_id]
            
            # Decrypt with AES-GCM and node binding
            payload = self.aes_decrypt(encrypted_data, node_key, sender_id)
            command_data = json.loads(payload)
            
            # Security validation sequence
            if not self.validate_command(command_data, sender_id):
                return
                
            # Execute command and send secure response
            command = command_data['command']
            print(f"Executing secure command from {sender_id}: {command}")
            output = self.execute_command(command)
            self.send_secure_response(output, sender_id)
            
        except Exception as e:
            error_msg = f"Command processing failed: {str(e)}"
            print(error_msg)
            self.send_secure_response(error_msg, sender_id)

    def validate_command(self, command_data, sender_id):
        """Multi-layer command validation"""
        # 1. Nonce replay check
        nonce = base64.b64decode(command_data['nonce'])
        if nonce in self.command_nonces[sender_id]:
            print(f"Blocked replay attack from {sender_id}")
            return False
        self.command_nonces[sender_id].add(nonce)
        
        # 2. Timestamp freshness (5 minute window)
        current_time = time.time()
        if abs(current_time - command_data['timestamp']) > 300:
            print(f"Blocked stale command from {sender_id}")
            return False
            
        # 3. Sender ID verification
        if command_data['sender'] != sender_id:
            print(f"Blocked sender mismatch: {command_data['sender']} vs {sender_id}")
            return False
            
        # 4. HMAC signature verification
        computed_hmac = self.generate_hmac(
            command_data['command'],
            nonce,
            command_data['timestamp'],
            self.node_keys[sender_id]
        )
        if computed_hmac != command_data['hmac']:
            print(f"Blocked invalid HMAC from {sender_id}")
            return False
            
        return True

    def generate_hmac(self, command, nonce, timestamp, key):
        """Create HMAC signature for command verification"""
        h = hmac.HMAC(key, hashes.SHA256())
        h.update(command.encode())
        h.update(nonce)
        h.update(str(timestamp).encode())
        return base64.b64encode(h.finalize()).decode()

    def aes_encrypt(self, plaintext: str, key: bytes, sender_id: int) -> bytes:
        """Encrypt with AES-GCM and node binding"""
        # Generate random nonce
        nonce = os.urandom(NONCE_SIZE)
        
        # Encrypt with AES-GCM
        cipher = AESGCM(key)
        ciphertext = cipher.encrypt(nonce, plaintext.encode(), str(sender_id).encode())
        
        # Combine nonce + ciphertext
        return nonce + ciphertext

    def aes_decrypt(self, data: bytes, key: bytes, sender_id: int) -> str:
        """Decrypt AES-GCM payload with node binding"""
        # Split nonce and ciphertext
        nonce = data[:NONCE_SIZE]
        ciphertext = data[NONCE_SIZE:]
        
        # Decrypt and verify with AAD
        cipher = AESGCM(key)
        plaintext = cipher.decrypt(nonce, ciphertext, str(sender_id).encode())
        return plaintext.decode()

    def execute_command(self, command):
        """Execute command with strict sandboxing"""
        try:
            # Enhanced command sanitization
            if not re.match(r'^[\w\s\-\.\/]+$', command):
                return "Error: Invalid characters in command"
                
            # Restricted command list
            allowed_commands = ['ls', 'pwd', 'whoami', 'date', 'df', 'ps', 'uname']
            cmd_base = command.split()[0]
            if cmd_base not in allowed_commands:
                return f"Error: Command {cmd_base} not allowed"
                
            result = subprocess.run(
                command.split(),
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS
            )
            return result.stdout.strip() or "[No output]"
        except Exception as e:
            return f"Command error: {str(e)}"

    def send_secure_response(self, text, destination_id):
        """Send encrypted response in chunks"""
        # Chunk plaintext before encryption
        chunks = [text[i:i+MAX_PLAINTEXT_LEN] 
                 for i in range(0, len(text), MAX_PLAINTEXT_LEN)]
        
        # Send first 3 chunks only
        for chunk in chunks[:3]:
            # Prepare encrypted payload
            payload = json.dumps({
                'response': chunk,
                'timestamp': time.time()
            })
            
            # Encrypt and transmit
            encrypted = self.aes_encrypt(payload, self.node_keys[destination_id], destination_id)
            encrypted_b64 = base64.b64encode(encrypted).decode()
            self.interface.sendText(
                ENCRYPTED_PREFIX + encrypted_b64,
                destinationId=destination_id
            )
            
        # Truncation notice
        if len(chunks) > 3:
            notice = json.dumps({
                'response': f"[TRUNCATED: {len(chunks)-3} chunks omitted]",
                'timestamp': time.time()
            })
            encrypted_notice = self.aes_encrypt(notice, self.node_keys[destination_id], destination_id)
            self.interface.sendText(
                ENCRYPTED_PREFIX + base64.b64encode(encrypted_notice).decode(),
                destinationId=destination_id
            )

    def run(self):
        """Main loop with clean exit handling"""
        self.connect()
        print("Secure C2 active. Waiting for commands...")
        try:
            while True: 
                # Periodically clear old nonces (every 5 minutes)
                time.sleep(300)
                self.clear_old_nonces()
                
        except KeyboardInterrupt:
            self.interface.close()
            print("Secure session terminated")
    
    def clear_old_nonces(self):
        """Prevent nonce storage bloat by clearing weekly"""
        for node in self.command_nonces:
            # Keep nonces from last 7 days only
            if len(self.command_nonces[node]) > 1000:
                self.command_nonces[node] = set()

if __name__ == "__main__":
    handler = SecureMeshHandler()
    handler.run()
