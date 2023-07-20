import sys
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

# Define valid options for the DKIM policy record
policy_options = ["quarantine", "reject", "none"]

# Define user questions
questions = [
    "What is your domain?",
    "What is the IP address of your mail server?",
    "What is the DKIM key length?",
    f"What is the DMARC policy? (Options: {', '.join(policy_options)})",
]

# Get user answers
answers = []
for question in questions:
    print(question)
    answer = input()
    answers.append(answer)

# Validate DMARC policy option
dmarc_policy = answers[3].strip().lower()
while dmarc_policy not in policy_options:
    print(f"Invalid DMARC policy. Please choose from: {', '.join(policy_options)}")
    answers[3] = input("What is the DMARC policy? ")
    dmarc_policy = answers[3].strip().lower()

# Generate the DKIM public and private keys
key_length = int(answers[2])
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=key_length,
    backend=default_backend()
)
public_key = private_key.public_key()

# Generate SPF, DMARC, and DKIM records
spf_record = f"v=spf1 a mx ip4:{answers[1]} -all"
dmarc_record = f"v=DMARC1 pct=100 policy={dmarc_policy}"
dkim_record = f"v=DKIM1; s=default; h=sha256; k=rsa; p={public_key.public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo).decode()}"

# Print the records
print("")
print("SPF Record:", spf_record)
print("DMARC Record:", dmarc_record)
print("DKIM Record:", dkim_record)

# Save the public and private keys
with open("public_key.pem", "wb") as f:
    f.write(public_key.public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo))

with open("private_key.pem", "wb") as f:
    f.write(private_key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.TraditionalOpenSSL, encryption_algorithm=serialization.NoEncryption()))
