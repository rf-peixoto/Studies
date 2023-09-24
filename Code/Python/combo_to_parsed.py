import json

# Define an empty list to store the JSON objects
json_objects = []

# Open your data file for reading
with open('your_data.txt', 'r') as file:
    for line in file:
        # Split the line based on the ':' delimiter
        parts = line.strip().split(':')

        # Create a dictionary with the required structure
        json_obj = {
            "id": 0,
            "stuff": parts[0],
            "another": parts[1]
        }

        # Append the JSON object to the list
        json_objects.append(json_obj)

# Open a new file for writing the JSON objects
with open('output.json', 'w') as output_file:
    # Write the JSON objects to the file
    json.dump(json_objects, output_file, indent=4)

print("Conversion completed. JSON objects are saved in 'output.json'.")
