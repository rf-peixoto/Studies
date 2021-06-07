# Simple Python SMTP Server
# Ref: https://pymotw.com/2/smtpd/
import smtpd
import asyncore

class SimpleSMTPServer(smtpd.SMTPServer):

    def process_message(self, peer, mailfrom, rcpttos, data, mail_options=None, rcpt_options=None):
        print("Receiving message from {0}.".format(peer))
        print("Message addressed from {0}.".format(mailfrom))
        print("Message addressed to {0}.".format(rcpttos))
        print("Message lenght: {0}.".format(len(data)))
        return

try:
    server = SimpleSMTPServer(('127.0.0.1', 1025), remoteaddr=None)
    asyncore.loop()
except Exception as error:
    print(error)
