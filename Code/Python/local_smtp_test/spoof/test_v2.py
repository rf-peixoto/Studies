#!/usr/bin/env python3
"""
Quick SMTP Relay Test
"""

import smtplib

def quick_test():
    # Update these values
    smtp_server = "mail.yourdomain.com"
    from_email = "test@yourdomain.com"
    to_email = "your-email@gmail.com"
    
    message = """Subject: SMTP Relay Test
From: test@yourdomain.com
To: your-email@gmail.com

This is a test for open relay vulnerability."""

    try:
        # Try without authentication
        server = smtplib.SMTP(smtp_server, 25)
        server.sendmail(from_email, to_email, message)
        server.quit()
        print("❌ OPEN RELAY - Email sent without auth!")
    except smtplib.SMTPAuthenticationError:
        print("✅ Good - Authentication required")
    except Exception as e:
        print(f"✅ Server blocked request: {e}")

if __name__ == "__main__":
    quick_test()
