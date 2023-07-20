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
    "What is the DKIM key length? (e.g., 2048)",
    f"What is the DMARC policy? (Options: {' '.join(policy_options)})",
]

def get_user_input(question):
    return input(question + "\n")

def get_valid_dkim_policy():
    dmarc_policy = get_user_input(questions[3]).strip().lower()
    while dmarc_policy not in policy_options:
        print(f"Invalid DMARC policy. Please choose from: {' '.join(policy_options)}")
        dmarc_policy = get_user_input(questions[3]).strip().lower()
    return dmarc_policy

def generate_key_pair(key_length):
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_length,
        backend=default_backend()
    )
    public_key = private_key.public_key()
    return public_key, private_key

def generate_records():
    domain = get_user_input(questions[0])
    mail_server_ip = get_user_input(questions[1])
    key_length = int(get_user_input(questions[2]))
    dmarc_policy = get_valid_dkim_policy()

    # Generate the DKIM public and private keys
    public_key, private_key = generate_key_pair(key_length)

    # Generate SPF, DMARC, and DKIM records
    spf_record = f"v=spf1 a mx ip4:{mail_server_ip} -all"
    dmarc_record = f"v=DMARC1 pct=100 policy={dmarc_policy}"
    dkim_record = f"v=DKIM1; s=default; h=sha256; k=rsa; p={public_key.public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo).decode()}"

    return spf_record, dmarc_record, dkim_record, public_key, private_key

def save_keys(public_key, private_key):
    with open("public_key.pem", "wb") as f:
        f.write(public_key.public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo))

    with open("private_key.pem", "wb") as f:
        f.write(private_key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.TraditionalOpenSSL, encryption_algorithm=serialization.NoEncryption()))

if __name__ == "__main__":
    spf_record, dmarc_record, dkim_record, public_key, private_key = generate_records()

    # Print the records
    print("\nSPF Record:", spf_record)
    print("DMARC Record:", dmarc_record)
    print("DKIM Record:", dkim_record)

    # Save the public and private keys
    save_keys(public_key, private_key)
