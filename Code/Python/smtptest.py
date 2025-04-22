import smtplib
from email.message import EmailMessage
import socket

# Configuration
SMTP_SERVER = 'smtp.example.com'
SMTP_PORT = 465  # SSL/TLS connection port
SMTP_USERNAME = 'your_username'
SMTP_PASSWORD = 'your_password'
SENDER_EMAIL = 'sender'
RECIPIENT_EMAIL = 'target'
TIMEOUT = 10  # Seconds

# Create the email message
msg = EmailMessage()
msg['Subject'] = 'Test Message'
msg['From'] = SENDER_EMAIL
msg['To'] = RECIPIENT_EMAIL
msg.set_content('This is a test message.')

print("[*] Starting email sending procedure with SSL...")
print(f"[*] SMTP Server: {SMTP_SERVER}:{SMTP_PORT}")
print(f"[*] Sender: {SENDER_EMAIL}")
print(f"[*] Recipient: {RECIPIENT_EMAIL}")
print(f"[*] Connection timeout set to {TIMEOUT} seconds.")

# Attempt to establish SSL connection and send the email
try:
    print("[*] Creating socket connection manually to check server reachability...")
    test_socket = socket.create_connection((SMTP_SERVER, SMTP_PORT), timeout=TIMEOUT)
    print("[+] Socket connection established successfully.")
    test_socket.close()
    print("[*] Socket connection closed. Proceeding with SMTP SSL connection.")

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=TIMEOUT) as server:
        server.set_debuglevel(2)
        print("[*] SMTP SSL connection initiated.")
        
        print("[*] Sending EHLO...")
        server.ehlo()
        print("[+] EHLO completed.")

        print("[*] Attempting login...")
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        print("[+] Login successful.")

        print("[*] Sending the email message...")
        server.send_message(msg)
        print("[+] Email message sent successfully.")

except socket.timeout:
    print("[!] Socket connection timed out.")
except socket.gaierror as e:
    print(f"[!] Address-related error connecting to server: {e}")
except smtplib.SMTPConnectError as e:
    print(f"[!] SMTP connection error: {e}")
except smtplib.SMTPAuthenticationError as e:
    print(f"[!] SMTP authentication error: {e}")
except smtplib.SMTPException as e:
    print(f"[!] General SMTP error: {e}")
except Exception as e:
    print(f"[!] Unexpected error: {e}")
