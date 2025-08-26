## Android SSL - Pinning:
# Get target cert:
echo | openssl s_client -connect <url:443> 2> /dev/null | openssl x509 > cert.pem

# Extract public key:
openssl x509 -in cert.pem -pubkey -noout > publick_key.pem

# Convert pubkey to DER:
openssl pkey -punin -in publick_key.pem -outform DER -out pub.der

# Hash and encode it:
openssl dgst -sha256 -binary pub.der | base64

# Dev would pin this hash on the code and check the certificate every connection.
