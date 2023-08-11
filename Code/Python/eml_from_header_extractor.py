import os
import email
from email.header import decode_header
from collections import defaultdict

def extract_domain_from_eml(eml_file_path):
    with open(eml_file_path, 'rb') as eml_file:
        msg = email.message_from_bytes(eml_file.read())

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

def process_eml_folder(folder_path):
    domains_count = defaultdict(int)

    for filename in os.listdir(folder_path):
        if filename.endswith('.eml'):
            eml_file_path = os.path.join(folder_path, filename)
            sender_domain = extract_domain_from_eml(eml_file_path)
            if sender_domain:
                domains_count[sender_domain] += 1

    return domains_count

def main():
    folder_path = 'path/to/your/eml/folder'
    domains_count = process_eml_folder(folder_path)

    total_domains = len(domains_count)
    total_files = sum(domains_count.values())

    print(f"Total unique domains found: {total_domains}")
    print(f"Total EML files processed: {total_files}")
    print("Domain distribution:")
    for domain, count in domains_count.items():
        print(f"{domain}: {count} files")

if __name__ == "__main__":
    main()
