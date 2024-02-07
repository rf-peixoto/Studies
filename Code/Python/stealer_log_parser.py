import os
import re
from datetime import datetime

def find_and_parse_passwords(root_dir, output_file):
    # Define both patterns
    entry_patterns = [
        re.compile(r'^URL: (https?://[^\s]+)\s+Username: ([^\s]+)\s+Password: ([^\s]+)\s+Application: (.+)$', re.MULTILINE),
        re.compile(r'^URL: (https?://[^\s]+)\s+Login: ([^\s]+)\s+Password: ([^\s]+)$', re.MULTILINE)
    ]
    
    # Generate output file path with timestamp
    current_time = datetime.now()
    timestamp = current_time.strftime("%Y-%m-%d_%H-%M-%S")
    output_file_with_timestamp = f'{output_file}_{timestamp}.txt'
    
    with open(output_file_with_timestamp, 'w', encoding='utf-8') as outfile:
        for root, dirs, files in os.walk(root_dir):
            # Convert the list of files to lower case for case-insensitive comparison
            lower_files = [file.lower() for file in files]
            if 'passwords.txt' in lower_files:
                # Find the original filename by its lowercased version
                original_filename = files[lower_files.index('passwords.txt')]
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
                                # Determine the correct format based on the matched pattern
                                if len(match) == 4:  # Pattern with Application
                                    outfile.write(f"{match[0]}:{match[1]}:{match[2]}\n")
                                else:  # Pattern without Application
                                    outfile.write(f"{match[0]}:{match[1]}:{match[2]}\n")
                except IOError as e:
                    print(f"Could not read file in {os.path.join(root, 'passwords.txt')}: {e}")
                    continue
                except UnicodeDecodeError as e:
                    print(f"Encoding error in file {os.path.join(root, 'passwords.txt')}: {e}")
                    continue

# Example usage
root_directory = r'C:\path\to\your\folder'  # Update this to your starting directory
output_file_base = 'parsed_passwords'  # Base name for the output file
find_and_parse_passwords(root_directory, output_file_base)
