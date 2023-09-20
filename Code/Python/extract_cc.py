import re
import sys

# Check if the correct number of command-line arguments are provided
if len(sys.argv) != 2:
    print("Usage: python extract_values.py input_file output_file")
    sys.exit(1)

# Input file name (provided as a command-line argument)
input_file = sys.argv[1]

# Output file name (provided as a command-line argument)
output_file = "output." + sys.argv[1]

# Define the encoding (e.g., 'utf-8' or 'ISO-8859-1') appropriate for your file
encoding = 'utf-8'  # You may need to adjust this based on your file's actual encoding

# Define the regex pattern
pattern = r'\d{16}\|\d{4}\|\d{3}'

print(f"Extracting values from {input_file}...")

try:
    # Open the input file for reading with the specified encoding
    with open(input_file, 'r', encoding=encoding, errors='ignore') as infile:
        # Read the content of the input file
        file_content = infile.read()
        
        # Find all matches in the file content
        matches = re.findall(pattern, file_content)

    print(f"Found {len(matches)} matches.")
    
    # Open the output file for writing
    with open(output_file, 'w') as outfile:
        # Write the matched values to the output file
        for match in matches:
            outfile.write(match + '\n')

    print(f"Matched values saved to {output_file}.")
    
except Exception as e:
    print(f"An error occurred: {str(e)}")
    sys.exit(1)

print("Script completed successfully.")
