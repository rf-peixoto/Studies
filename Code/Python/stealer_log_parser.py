import os
import re

def find_and_parse_passwords(root_dir, output_file):
    # Regex to match the structure in the Passwords.txt file
    entry_pattern = re.compile(r'^URL: (https?://[^\s]+)\s+Username: ([^\s]+)\s+Password: ([^\s]+)\s+Application: (.+)$', re.MULTILINE)
    
    with open(output_file, 'w', encoding='utf-8') as outfile:
        for root, dirs, files in os.walk(root_dir):
            if 'Passwords.txt' in files:
                try:
                    with open(os.path.join(root, 'Passwords.txt'), 'r', encoding='utf-8', errors='replace') as file:
                        content = file.read()
                        matches = entry_pattern.findall(content)
                        for match in matches:
                            # Formatting the output as "URL:Username:Password"
                            outfile.write(f"{match[0]}:{match[1]}:{match[2]}\n")
                except IOError as e:
                    print(f"Could not read file in {os.path.join(root, 'Passwords.txt')}: {e}")
                except UnicodeDecodeError as e:
                    print(f"Encoding error in file {os.path.join(root, 'Passwords.txt')}: {e}")

# Example usage
root_directory = r'C:\Path\to\root\dir'  # Update this to your starting directory
output_file_path = 'parsed_passwords.txt'  # Output file where the results will be saved
find_and_parse_passwords(root_directory, output_file_path)
