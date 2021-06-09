# Simple Python SMTP Client
# Ref: https://pymotw.com/2/smtpd/
import smtplib
import email.utils
from email.mime.text import MIMEText

# =========================================================================== #
# Config:
# =========================================================================== #
message_author = input("Message author: ")
message_target = input("Target address: ")
message_subject = input("Message subject: ")
message_body = ""

# =========================================================================== #
# Compose:
# =========================================================================== #
message = MIMEText(message_body)
message['To'] = email.utils.formataddr(('Recipient', message_target))
message['From'] = email.utils.formataddr(('Author', message_author))
message['Subject'] = message_subject

# =========================================================================== #
# Connect to Server:
# =========================================================================== #
server = smtplib.SMTP('127.0.0.1', 1025)
#server.connect(port=1025)
server.set_debuglevel(False) # Verbose?

# =========================================================================== #
# Send Message:
# =========================================================================== #
try:
    print('Sending message.')
    server.sendmail(message_author, [message_target], message.as_string())
    print('Message sent.')
except Exception as error:
    print(error)
