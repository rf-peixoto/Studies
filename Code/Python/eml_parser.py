import os
import email
import pandas as pd
from email import policy
from email.parser import BytesParser

# Directory containing EML files
eml_directory = 'path_to_your_eml_files'

# Function to extract information from an EML file
def extract_info_from_eml(file_path):
    with open(file_path, 'rb') as f:
        msg = BytesParser(policy=policy.default).parse(f)
    subject = msg['subject']
    from_ = msg['from']
    date = msg.get('date')
    return from_, subject, date

# Process each EML file and store the information in a list
data = []
for file in os.listdir(eml_directory):
    if file.endswith('.eml'):
        file_path = os.path.join(eml_directory, file)
        from_, subject, date = extract_info_from_eml(file_path)
        data.append({'From': from_, 'Subject': subject, 'Date': date})

# Convert the list to a DataFrame and save to CSV
df = pd.DataFrame(data)
csv_output_path = 'eml_data.csv'
df.to_csv(csv_output_path, index=False)
print(f"Data extracted and saved to {csv_output_path}")
