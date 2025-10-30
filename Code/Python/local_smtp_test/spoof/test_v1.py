#!/usr/bin/env python3
"""
SMTP Open Relay Test Script
Tests if your mail server allows unauthenticated email sending
"""

import smtplib
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def test_smtp_relay(smtp_server, smtp_port, from_domain, to_email, test_message=None):
    """
    Test SMTP server for open relay vulnerability
    """
    if test_message is None:
        test_message = """
        This is a test email to check for SMTP open relay vulnerability.
        
        If you received this email, your mail server may be configured as an open relay,
        which allows unauthorized users to send email through your server.
        
        This is a security test - please ensure your SMTP server requires authentication.
        """
    
    # Create message
    msg = MIMEMultipart()
    msg['From'] = f'test@{from_domain}'
    msg['To'] = to_email
    msg['Subject'] = f'SMTP Relay Test - {from_domain}'
    msg.attach(MIMEText(test_message, 'plain'))
    
    try:
        print(f"Testing {smtp_server}:{smtp_port}...")
        
        # Connect to server
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port)
            if smtp_port == 587:
                server.starttls()  # Upgrade to secure connection
        
        # Try to send email WITHOUT authentication
        print("Attempting to send email without authentication...")
        server.sendmail(f'test@{from_domain}', [to_email], msg.as_string())
        server.quit()
        
        print("❌ OPEN RELAY DETECTED!")
        print("Your SMTP server allowed email sending without authentication")
        return False
        
    except smtplib.SMTPAuthenticationError:
        print("✅ SECURE: Server requires authentication")
        return True
    except smtplib.SMTPException as e:
        print(f"✅ SECURE: Server blocked unauthenticated sending - {e}")
        return True
    except Exception as e:
        print(f"⚠️  Connection/Error: {e}")
        return None

def main():
    # Configuration - UPDATE THESE VALUES
    config = {
        'smtp_server': 'mail.yourdomain.com',  # Your mail server
        'smtp_port': 587,                      # Common ports: 25, 587, 465
        'from_domain': 'yourdomain.com',       # Your domain
        'to_email': 'test@gmail.com'          # External email address
    }
    
    print("SMTP Open Relay Vulnerability Test")
    print("=" * 50)
    
    # Test multiple common ports
    ports_to_test = [25, 587, 465]
    
    for port in ports_to_test:
        print(f"\nTesting port {port}:")
        config['smtp_port'] = port
        test_smtp_relay(**config)
    
    print("\n" + "=" * 50)
    print("Test completed. Check your email to see if test messages were received.")

if __name__ == "__main__":
    main()
