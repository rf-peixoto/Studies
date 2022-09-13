#!/usr/python
import smtplib, string
import os, time

# Init sendmail:
print("[*] Starting sendmail")
os.system("/etc/init.d/sendmail start")
time.sleep(5)

HOST = "localhost"
SUBJECT = "Subject"
TO = "target@addr.com"
FROM = "spoofed@addr.com"
TEXT =  "Message body"
BODY = string.join(( "From: %s" % FROM,
                    "To: %s" % TO,
                    "Subject: %s" % SUBJECT,
                    "",
                    TEXT), "\r\n")

# Init server:
print("[*] Starting server & sending")
server = smtplib.SMTP(HOST)
server.sendmail(FROM, [TO]. BODY)
server.quit()

# Close server:
print("[*] Closing sendmail")
time.sleep(5)
os.system("/etc/init.d/sendmail stop")
