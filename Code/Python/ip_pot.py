from flask import Flask, request
import smtplib

app = Flask(__name__)

@app.before_request
def log_request_info():
    # Retrieve source IP and request data
    source_ip = request.remote_addr
    request_data = request.data
    
    # Send email
    sender = 'your_email@example.com'
    receiver = 'your_email@example.com'
    subject = 'Web Server Request'
    message = f'Source IP: {source_ip}\nRequest Data: {request_data.decode()}'
    
    smtp_server = 'smtp.example.com'
    smtp_port = 587
    smtp_username = 'your_smtp_username'
    smtp_password = 'your_smtp_password'
    
    smtp_connection = smtplib.SMTP(smtp_server, smtp_port)
    smtp_connection.starttls()
    smtp_connection.login(smtp_username, smtp_password)
    smtp_connection.sendmail(sender, receiver, f'Subject: {subject}\n\n{message}')
    smtp_connection.quit()

@app.route('/')
def index():
    return 'Web server is up and running.'

if __name__ == '__main__':
    app.run()
