import os
import re
from email.parser import BytesParser
from email.policy import default

# Specify the folder where your EML files are stored
folder_path = 'path/to/your/folder'

# Output file where sender addresses will be saved
output_file = 'output.txt'

# List of headers to check for the sender's email address
headers_to_check = ['from', 'reply-to', 'sender']

# Function to extract the primary sender from an EML file, checking multiple headers
def extract_sender_from_headers(file_path):
    try:
        with open(file_path, 'rb') as f:
            headers = BytesParser(policy=default).parse(f)
        for header in headers_to_check:
            from_header = headers.get(header)
            if from_header:
                # Attempt to extract the email address using regex
                match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', from_header)
                if match:
                    return match.group(0)
    except Exception as e:
        print(f"Error processing file {file_path}: {e}")

# Find all EML files in the specified folder
eml_files = [f for f in os.listdir(folder_path) if f.endswith('.eml')]

found_senders = 0

# Open the output file
with open(output_file, 'w') as output:
    for file in eml_files:
        file_path = os.path.join(folder_path, file)
        email_address = extract_sender_from_headers(file_path)
        if email_address:
            output.write(email_address + '\n')
            found_senders += 1
        else:
            print(f"No sender found in: {file}")

print(f"Process completed. Found {found_senders} sender addresses out of {len(eml_files)} files. Results are in {output_file}.")

# Then:
# sort output.txt | uniq -c | grep -v '^ *1 ' | sort -nr

