import os
import re

# Define the regular expression pattern to extract the desired data
pattern = r'(\d+\|\d+\|\d+\|\d+)'

# Specify the directory containing your HTML files
directory_path = r'C:\path\to\your\html\files'  # Use a raw string with r-prefix

# Initialize a list to store the extracted data
extracted_data = []

# Iterate through the files in the directory
print('Extracting data.')
encodings = ['utf-8', 'windows-1256', 'ISO-8859-6']
for en in encodings:
    try:
        for filename in os.listdir(directory_path):
            if filename.endswith(".html"):
                # Construct the full path to the HTML file
                file_path = os.path.join(directory_path, filename)

                # Open and read the HTML file
                with open(file_path, 'r', encoding=en) as file:
                    html_content = file.read()

                # Use regex to find all matches in the HTML content
                matches = re.findall(pattern, html_content)

                # Add the matches to the extracted_data list
                extracted_data.extend(matches)
        break
    except UnicodeDecodeError:
        continue
            

# Export the extracted data
with open('extracted.txt', 'w') as fl:
    for data in extracted_data:
        fl.write(data + '\n')
print('Done')
