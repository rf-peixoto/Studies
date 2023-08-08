import email
from email.header import decode_header

def extract_domain_from_eml(eml_file_path):
    with open(eml_file_path, 'r', encoding='utf-8') as eml_file:
        msg = email.message_from_file(eml_file)

        from_header = msg.get('From')
        if from_header:
            decoded_header = decode_header(from_header)[0]
            if isinstance(decoded_header[0], bytes):
                sender_email = decoded_header[0].decode(decoded_header[1] or 'utf-8')
            else:
                sender_email = decoded_header[0]
            
            # Extract domain
            domain = sender_email.split('@')[-1]
            return domain

    return None

# Example usage
eml_file_path = 'path/to/your/email.eml'
sender_domain = extract_domain_from_eml(eml_file_path)
if sender_domain:
    print(f"Sender domain: {sender_domain}")
else:
    print("Unable to extract sender domain.")
