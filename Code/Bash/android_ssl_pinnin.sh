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


# If you need the .pem based on a .der:
openssl x509 -inform DER cert.der -out cert.pem

# Android will use <hash>.0 format, so:
openssl x509 -inform PEM -subject_hash_old -in cert.pem | head -1
# them rename the cert file to the <hash>.0 you got. Ex: mv cert.pem 1234abcd.0
# You will need to put the system files in write mode on your android:
adb remount
# Them:
adb push <hash>.0 /system/etc/security/cacerts/
adb shell chmod 644 /system/etc/security/cacerts/<hash>.0
adb reboot
