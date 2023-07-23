#!/bin/bash

# Replace these variables with appropriate values
gmail_access_token="YOUR_GMAIL_ACCESS_TOKEN"
recipient_email="recipient@example.com"
email_subject="Test Email Subject"
email_body="This is a test email sent using the Gmail API."

# Construct the JSON payload for the email
email_data=$(cat << EOF
{
  "raw": "From: me@example.com\\nTo: $recipient_email\\nSubject: $email_subject\\n\\n$email_body"
}
EOF
)

# Send the email using Gmail API
curl -X POST \
  -H "Authorization: Bearer $gmail_access_token" \
  -H "Content-Type: application/json" \
  --data "$email_data" \
  "https://www.googleapis.com/gmail/v1/users/me/messages/send"

echo "Email sent successfully."
