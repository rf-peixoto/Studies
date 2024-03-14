import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Your email account information
from_email = "your_email@gmail.com"
password = "your_password"  # Use an App Password if 2FA is enabled
to_email = "recipient_email@example.com"

# Create message
message = MIMEMultipart()
message["From"] = from_email
message["To"] = to_email
message["Subject"] = "Daily Email Report"

# Email body
body = "This is your daily report. Please find the attached document."
message.attach(MIMEText(body, "plain"))

# Convert message to string
email_text = message.as_string()

# Send the email
try:
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()  # Secure the connection
    server.login(from_email, password)
    server.sendmail(from_email, to_email, email_text)
    server.quit()
    print("Email sent successfully!")
except Exception as e:
    print(f"Failed to send email: {e}")
