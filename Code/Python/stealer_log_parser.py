import os
import re
from datetime import datetime

def find_and_parse_passwords(root_dir, output_file):
    # Define both patterns
    entry_patterns = [
        re.compile(r'^URL: (https?://[^\s]+)\s+Username: ([^\s]+)\s+Password: ([^\s]+)\s+Application: (.+)$', re.MULTILINE),
        re.compile(r'^URL: (https?://[^\s]+)\s+USER: ([^\s]+)\s+PASS: ([^\s]+)$', re.MULTILINE),
        re.compile(r'^URL: (https?://[^\s]+)\s+Login: ([^\s]+)\s+Password: ([^\s]+)$', re.MULTILINE),
        re.compile(r'^Host: (https?://[^\s]+)\s+Username: ([^\s]+)\s+Password: ([^\s]+)$', re.MULTILINE)
    ]
    
    # Generate output file path with timestamp
    current_time = datetime.now()
    timestamp = current_time.strftime("%Y-%m-%d_%H-%M-%S")
    output_file_with_timestamp = f'{output_file}_{timestamp}.txt'
    
    with open(output_file_with_timestamp, 'w', encoding='utf-8') as outfile:
        for root, dirs, files in os.walk(root_dir):
            # Normalize file names to lower case for case-insensitive matching
            normalized_files = [file.lower() for file in files]
            # Check for files that match any of the specified patterns
            for possible_filename in ['passwords.txt', 'all passwords.txt']:
                if possible_filename in normalized_files:
                    # Get the original filename
                    original_filename = files[normalized_files.index(possible_filename)]
                    try:
                        with open(os.path.join(root, original_filename), 'r', encoding='utf-8', errors='replace') as file:
                            content = file.read()
                            matches = None
                            # Try each pattern until a match is found
                            for pattern in entry_patterns:
                                matches = pattern.findall(content)
                                if matches:
                                    break
                            # If matches were found, process them
                            if matches:
                                for match in matches:
                                    # Formatting the output as "URL:Username:Password"
                                    outfile.write(f"{match[0]}:{match[1]}:{match[2]}\n")
                    except IOError as e:
                        print(f"Could not read file in {os.path.join(root, original_filename)}: {e}")
                        continue
                    except UnicodeDecodeError as e:
                        print(f"Encoding error in file {os.path.join(root, original_filename)}: {e}")
                        continue

# Example usage
root_directory = r'C:\path\to\root\folder'  # Update this to your starting directory
output_file_base = 'parsed_passwords'  # Base name for the output file
find_and_parse_passwords(root_directory, output_file_base)
