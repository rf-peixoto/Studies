import json
import sys

# Check if the user provided a file path as a command-line argument
if len(sys.argv) != 2:
    print("Usage: python script.py <file_path>")
    sys.exit(1)

# Get the file path from the command-line argument
file_path = sys.argv[1]

# Define the output file path
output_file_path = 'output.json'
id_file_path = 'last_id.txt'

# Initialize the last used ID to 0
last_id = 0

# Check if the ID file exists
try:
    with open(id_file_path, 'r') as id_file:
        last_id = int(id_file.read())
except FileNotFoundError:
    # If the ID file does not exist, create it with ID 0
    with open(id_file_path, 'w') as id_file:
        id_file.write(str(last_id))

# Define an empty list to store the JSON objects
json_objects = []

# Open the specified data file for reading
try:
    with open(file_path, 'r') as file:
        for line in file:
            line = line.strip().replace(' ', ':')

            # Check if the line contains 'http://' or 'https://'
            if 'http://' in line or 'https://' in line:
                # Find the index of the second ':' which separates the URL from the email
                separator_index = line.find(':', line.find('//') + 2)
                url = line[:separator_index]
                rest = line[separator_index + 1:].split(':')
            else:
                url = ""
                rest = line.split(':')

            # Create the JSON object
            if len(rest) == 2:
                json_obj = {
                    "id": last_id,
                    "url": url,
                    "email": rest[0],
                    "password": rest[1]
                }
            else:
                # Handle unexpected format
                print(f"Unexpected format in line: {line}")
                continue

            last_id += 1
            json_objects.append(json_obj)
except FileNotFoundError:
    print(f"File not found: {file_path}")
    sys.exit(1)

# Open a new file for writing the JSON objects
with open(output_file_path, 'w') as output_file:
    # Write the JSON objects to the file
    json.dump(json_objects, output_file, indent=4)

# Update the ID file with the last used ID
with open(id_file_path, 'w') as id_file:
    id_file.write(str(last_id))

print("Conversion completed. JSON objects are saved in 'output.json'.")

