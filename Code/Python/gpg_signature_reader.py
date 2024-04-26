import gnupg
import re

def count_signatures(file_path):
    # Initialize the GPG interface
    gpg = gnupg.GPG()

    # Read the content from the file
    with open(file_path, 'r') as file:
        content = file.read()
    
    # Check if the content is a GPG signed message
    if '-----BEGIN PGP SIGNED MESSAGE-----' in content:
        # Verify the signature(s)
        verified = gpg.verify(content)
        
        # Attempt to extract multiple signatures if present
        signatures = re.findall('-----BEGIN PGP SIGNATURE-----.*?-----END PGP SIGNATURE-----', content, re.DOTALL)
        num_signatures = len(signatures)
        
        # Print each signature and the number of signatures
        for idx, sig in enumerate(signatures, start=1):
            print(f"Signature {idx}:\n{sig}\n")
        print(f"Total number of signatures: {num_signatures}")
        
        return signatures, num_signatures
    else:
        print("No GPG signed message found.")
        return [], 0

# Example usage:
# Replace 'path_to_your_file.txt' with the path to your file
signatures, count = count_signatures('path_to_your_file.txt')
