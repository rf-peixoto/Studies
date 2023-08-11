import os
import email
from email.header import decode_header
from collections import defaultdict
import chardet

def is_valid_email_address(address):
    try:
        email.utils.parseaddr(address)
        return True
    except:
        return False

def extract_domain_from_eml(eml_file_path):
    with open(eml_file_path, 'rb') as eml_file:
        raw_email = eml_file.read()

        result = chardet.detect(raw_email)
        encoding = result['encoding']

        msg = email.message_from_bytes(raw_email)
        
        reply_to_header = msg.get('Reply-To')
        if reply_to_header:
            decoded_header = decode_header(reply_to_header)[0]
            if isinstance(decoded_header[0], bytes):
                sender_email = decoded_header[0].decode(encoding or 'utf-8', errors='replace')
            else:
                sender_email = decoded_header[0]

            if is_valid_email_address(sender_email):
                domain = sender_email.split('@')[-1]
                return domain
        
    return None

def process_eml_folder(folder_path):
    domains_count = defaultdict(int)
    error_log = []

    for filename in os.listdir(folder_path):
        if filename.endswith('.eml'):
            eml_file_path = os.path.join(folder_path, filename)
            try:
                sender_domain = extract_domain_from_eml(eml_file_path)
                if sender_domain and sender_domain != 'pot':
                    domains_count[sender_domain] += 1
            except Exception as e:
                error_log.append(f"Error processing {filename}: {str(e)}")

    return domains_count, error_log

def main():
    folder_path = 'path/to/your/eml/folder'
    domains_count, error_log = process_eml_folder(folder_path)

    total_domains = len(domains_count)
    total_files = sum(domains_count.values())

    print(f"Total unique domains found: {total_domains}")
    print(f"Total EML files processed: {total_files}")
    print("Domain distribution (sorted by file count):")
    for domain, count in sorted(domains_count.items(), key=lambda x: x[1], reverse=True):
        print(f"{domain}: {count} files")

    if error_log:
        with open('error.log', 'w') as error_file:
            for error in error_log:
                error_file.write(error + '\n')

if __name__ == "__main__":
    main()
