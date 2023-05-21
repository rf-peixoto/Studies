import time
import smtplib
import hashlib
import os
import socket
import pwd
from email.mime.text import MIMEText
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Set up email configuration
smtp_server = 'smtp.gmail.com'
smtp_port = 587
sender_email = 'your_email@gmail.com'
sender_password = 'your_password'
recipient_email = 'recipient_email@example.com'

class FileChangeHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            self.send_email_notification(event.src_path, 'created')

    def on_modified(self, event):
        if not event.is_directory:
            self.send_email_notification(event.src_path, 'modified')

    def on_deleted(self, event):
        if not event.is_directory:
            self.send_email_notification(event.src_path, 'deleted')

    def send_email_notification(self, file_path, event_type):
        subject = f'File {event_type}: {file_path}'
        body = f'The file {file_path} was {event_type} at {time.ctime()}.\n\n'

        if event_type != 'deleted':
            body += f'File Path: {file_path}\n'
            body += f'Event Type: {event_type}\n'
            file_size = os.path.getsize(file_path)
            body += f'File Size: {file_size} bytes\n'

#            with open(file_path, 'rb') as file:
#                file_data = file.read()
#                file_hash = hashlib.md5(file_data).hexdigest()
#            body += f'Hash: {file_hash}\n'

        # Retrieve the username of the user who performed the action
        username = pwd.getpwuid(os.stat(file_path).st_uid).pw_name
        body += f'User: {username}\n'

        # Retrieve the IP address of the machine
        machine_ip = socket.gethostbyname(socket.gethostname())
        body += f'Machine IP: {machine_ip}\n'

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = recipient_email

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())

# Set up the file system observer
path_to_monitor = '/path/to/monitor'
event_handler = FileChangeHandler()
observer = Observer()
observer.schedule(event_handler, path_to_monitor, recursive=True)
observer.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    observer.stop()
observer.join()
