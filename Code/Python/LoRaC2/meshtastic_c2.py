# pip install meshtastic
# Grant necessary permissions to access your Meshtastic device (usually /dev/ttyACM0 or /dev/ttyUSB0

import subprocess
import meshtastic
import meshtastic.serial_interface
from pubsub import pub

# Configuration
COMMAND_PREFIX = "cmd:"  # Prefix to trigger command execution
MAX_OUTPUT_LENGTH = 220  # Max characters per Meshtastic message
TIMEOUT_SECONDS = 30     # Command execution timeout

class MeshCommandHandler:
    def __init__(self):
        self.interface = None
        
    def connect(self):
        """Connect to Meshtastic device"""
        try:
            self.interface = meshtastic.serial_interface.SerialInterface()
            print("Connected to Meshtastic device")
            pub.subscribe(self.on_receive, "meshtastic.receive")
        except Exception as e:
            print(f"Connection error: {e}")
            exit(1)

    def on_receive(self, packet, interface):
        """Handle received messages"""
        try:
            decoded = packet.get("decoded", {})
            text = decoded.get("text", "")
            sender = packet.get("from", "")

            if text.startswith(COMMAND_PREFIX):
                command = text[len(COMMAND_PREFIX):].strip()
                print(f"Received command from {sender}: {command}")
                
                # Execute command and get output
                output = self.execute_command(command)
                
                # Send response back to sender
                self.send_response(output, sender)
                
        except Exception as e:
            print(f"Error handling message: {e}")

    def execute_command(self, command):
        """Execute system command and capture output"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS
            )
            output = result.stdout
            if result.stderr:
                output += "\nERROR:\n" + result.stderr
                
            return output.strip() or "[No output]"
            
        except subprocess.TimeoutExpired:
            return "Command timed out"
        except Exception as e:
            return f"Command error: {str(e)}"

    def send_response(self, text, destination_id):
        """Send response in chunks"""
        # Split long output into chunks
        chunks = [text[i:i+MAX_OUTPUT_LENGTH] 
                 for i in range(0, len(text), MAX_OUTPUT_LENGTH)]
        
        # Send first 3 chunks only to prevent flooding
        for chunk in chunks[:3]:
            self.interface.sendText(chunk, destinationId=destination_id)
            
        if len(chunks) > 3:
            self.interface.sendText(
                f"[Output truncated - {len(chunks)-3} chunks remaining]", 
                destinationId=destination_id
            )

    def run(self):
        """Main processing loop"""
        self.connect()
        print("Listening for commands... (Ctrl+C to stop)")
        try:
            while True:
                # Keep the program running
                pass
        except KeyboardInterrupt:
            self.interface.close()
            print("Disconnected")

if __name__ == "__main__":
    handler = MeshCommandHandler()
    handler.run()
