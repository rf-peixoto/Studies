# pip install pycapnp

import sys
import json
import capnp
import os

# Path for the Cap'n Proto schema file
SCHEMA_FILE = 'example.capnp'

def create_example_schema():
    """
    Create an example Cap'n Proto schema file if it doesn't exist.
    """
    schema_content = '''
    @0xabcdefabcdefabcdef;

    struct Message {
      id @0 :Int32;
      name @1 :Text;
      data @2 :Text;
    }
    '''
    with open(SCHEMA_FILE, 'w') as f:
        f.write(schema_content)
    print(f"Created example schema file: {SCHEMA_FILE}")


# Create schema file if it doesn't exist
if not os.path.exists(SCHEMA_FILE):
    create_example_schema()

# Load the Cap'n Proto schema
try:
    capnp_schema = capnp.load(SCHEMA_FILE)
except FileNotFoundError:
    print(f"Error: The schema file {SCHEMA_FILE} was not found.")
    sys.exit(1)


def read_capnp_file(filename):
    """
    Read and print the contents of a Cap'n Proto binary file.
    """
    try:
        with open(filename, 'rb') as f:
            message = capnp_schema.Message.read(f)
            print(message)
    except Exception as e:
        print(f"Error reading Cap'n Proto file {filename}: {e}")
        sys.exit(1)


def json_to_capnp(json_filename, capnp_filename):
    """
    Convert a JSON file to Cap'n Proto binary format.
    """
    try:
        # Read the JSON file
        with open(json_filename, 'r') as f:
            data = json.load(f)
        
        # Create a new Cap'n Proto message
        message = capnp_schema.Message.new_message()
        
        # Assign data from the JSON to the Cap'n Proto message fields
        # Note: This part assumes the Cap'n Proto schema has matching fields to the JSON structure
        for key, value in data.items():
            setattr(message, key, value)
        
        # Write the Cap'n Proto binary message to a file
        with open(capnp_filename, 'wb') as f:
            message.write(f)
        print(f"Converted {json_filename} to Cap'n Proto format in {capnp_filename}")
    
    except Exception as e:
        print(f"Error converting JSON to Cap'n Proto: {e}")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: script.py <capnp_file_to_read> OR script.py <json_file_to_convert> <output_capnp_file>")
        sys.exit(1)
    
    # If only one argument is provided, assume it's a Cap'n Proto file to read
    if len(sys.argv) == 2:
        capnp_file = sys.argv[1]
        if not os.path.exists(capnp_file):
            print(f"Error: File {capnp_file} not found.")
            sys.exit(1)
        read_capnp_file(capnp_file)
    
    # If two arguments are provided, assume it's converting JSON to Cap'n Proto
    elif len(sys.argv) == 3:
        json_file = sys.argv[1]
        capnp_file = sys.argv[2]
        
        if not os.path.exists(json_file):
            print(f"Error: File {json_file} not found.")
            sys.exit(1)
        json_to_capnp(json_file, capnp_file)


if __name__ == "__main__":
    main()
