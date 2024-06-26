"""
import os
import email
from email.header import decode_header
from collections import defaultdict
import chardet
import re

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

            # Validate email address format using a more permissive regex
            if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', sender_email) and is_valid_email_address(sender_email):
                domain = sender_email.split('@')[-1]
                return domain
        
        from_header = msg.get('From')
        if from_header:
            decoded_header = decode_header(from_header)[0]
            if isinstance(decoded_header[0], bytes):
                sender_email = decoded_header[0].decode(encoding or 'utf-8', errors='replace')
            else:
                sender_email = decoded_header[0]

            # Validate email address format using a more permissive regex
            if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', sender_email) and is_valid_email_address(sender_email):
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
                else:
                    error_log.append(f"No valid sender found in {filename}")
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

        print(f"Total errors encountered: {len(error_log)}")

if __name__ == "__main__":
    main()
"""
"""
# Version 2
import os
import email
from email.header import decode_header
from collections import defaultdict
import chardet
from validate_email import validate_email

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

            # Validate email address using the validate_email library
            if validate_email(sender_email):
                domain = sender_email.split('@')[-1]
                return domain
        
        from_header = msg.get('From')
        if from_header:
            decoded_header = decode_header(from_header)[0]
            if isinstance(decoded_header[0], bytes):
                sender_email = decoded_header[0].decode(encoding or 'utf-8', errors='replace')
            else:
                sender_email = decoded_header[0]

            # Validate email address using the validate_email library
            if validate_email(sender_email):
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
                else:
                    error_log.append(f"No valid sender found in {filename}")
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

        print(f"Total errors encountered: {len(error_log)}")

if __name__ == "__main__":
    main()
"""
"""
# Version 3:
import os
from collections import defaultdict
from envelopes import Envelope

def extract_domain_from_eml(eml_file_path):
    envelope = Envelope.from_file(eml_file_path)
    
    if envelope.reply_to:
        sender_email = envelope.reply_to[0]
        if "@" in sender_email:
            domain = sender_email.split('@')[-1]
            return domain
    
    if envelope.sender:
        sender_email = envelope.sender
        if "@" in sender_email:
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
                else:
                    error_log.append(f"No valid sender found in {filename}")
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

        print(f"Total errors encountered: {len(error_log)}")

if __name__ == "__main__":
    main()
"""
"""
# Holy crow, 4th version, here we go:
import os
import email
from email.header import decode_header
from collections import defaultdict
import chardet

def extract_emails_from_header(header_value):
    decoded_header = decode_header(header_value)[0]
    if isinstance(decoded_header[0], bytes):
        header_text = decoded_header[0].decode('utf-8', errors='replace')
    else:
        header_text = decoded_header[0]

    emails = []
    for word in header_text.split():
        if "@" in word:
            emails.append(word)
    return emails

def extract_domain_from_eml(eml_file_path):
    with open(eml_file_path, 'rb') as eml_file:
        raw_email = eml_file.read()

        result = chardet.detect(raw_email)
        encoding = result['encoding']

        msg = email.message_from_bytes(raw_email)
        
        reply_to_header = msg.get('Reply-To')
        from_header = msg.get('From')

        emails = []

        if reply_to_header:
            emails.extend(extract_emails_from_header(reply_to_header))
        
        if from_header:
            emails.extend(extract_emails_from_header(from_header))

        for email_address in emails:
            if "@" in email_address:
                domain = email_address.split('@')[-1]
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
                else:
                    error_log.append(f"No valid sender found in {filename}")
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

        print(f"Total errors encountered: {len(error_log)}")

if __name__ == "__main__":
    main()
"""

# Starting to panic right now
import os
import email
from email.header import decode_header
from collections import defaultdict
import chardet

def extract_emails_from_header(header_value):
    decoded_header = decode_header(header_value)[0]
    if isinstance(decoded_header[0], bytes):
        header_text = decoded_header[0].decode('utf-8', errors='replace')
    else:
        header_text = decoded_header[0]

    # Remove trailing ">" characters, if present
    header_text = header_text.rstrip('>')

    emails = []
    for word in header_text.split():
        if "@" in word:
            emails.append(word)
    return emails

def extract_domain_from_eml(eml_file_path):
    with open(eml_file_path, 'rb') as eml_file:
        raw_email = eml_file.read()

        result = chardet.detect(raw_email)
        encoding = result['encoding']

        msg = email.message_from_bytes(raw_email)
        
        reply_to_header = msg.get('Reply-To')
        from_header = msg.get('From')

        emails = []

        if reply_to_header:
            emails.extend(extract_emails_from_header(reply_to_header))
        
        if from_header:
            emails.extend(extract_emails_from_header(from_header))

        for email_address in emails:
            if "@" in email_address:
                domain = email_address.split('@')[-1]
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
                else:
                    error_log.append(f"No valid sender found in {filename}")
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

        print(f"Total errors encountered: {len(error_log)}")

if __name__ == "__main__":
    main()
