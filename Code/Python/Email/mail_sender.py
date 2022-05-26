import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Receive on:
receivers = ['', '', '', '']

# Connection options:
sender = "SENDER EMAIL"
sender_passwd = "SENDER PASSWD"
server = smtplib.SMTP('smtp.domain.com', 587)

# Email Settings:
subject = 'Test.'
body = 'Test for mail spoofing.'

# Connect:
try:
    server.starttls()
    server.login(sender, sender_passwd)
except Exception as error:
    print(error)

# Send message:
email = MIMEMultipart()
email['From'] = sender
email['Subject'] = subject
email.attach(MIMEText(body, 'plain'))
for addr in receivers:
    email['To'] = addr
    try:
        server.sendmail(sender, addr, email.as_string())
    except Exception as error:
        print("Error on sending to {0}.".format(addr))
        print(error)
