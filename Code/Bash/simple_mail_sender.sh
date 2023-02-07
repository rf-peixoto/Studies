#!/bin/bash

# From GPT

HOST=$1
MY_EMAIL="wbks4@protonmail.ch"

if ping -c 1 "$HOST" &> /dev/null; then
  echo "$HOST is up."
  if nc -z "$HOST" 25 &> /dev/null; then
    echo "SMTP server is open on $HOST:25."
    echo "Sending test email to $MY_EMAIL..."
    echo "Subject: Test Email" | \
    sendmail -f "from_email@$HOST" "$MY_EMAIL"
    echo "Test email sent."
  else
    echo "SMTP server is not open on $HOST:25."
  fi
else
  echo "$HOST is down."
fi
