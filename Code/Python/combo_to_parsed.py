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
            # Split the line based on the ':' delimiter
            parts = line.strip().split(':')

            # Create a dictionary with the required structure
            json_obj = {
                "id": last_id,
                "stuff": parts[0],
                "another": parts[1]
            }

            # Increment the ID for the next object
            last_id += 1

            # Append the JSON object to the list
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
