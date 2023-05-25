# GPT helped with this one.
# Ref: https://en.wikipedia.org/wiki/DNA_digital_data_storage

import sys

def encode_to_dna(file_path):
    # Read the file in binary mode
    with open(file_path, 'rb') as file:
        file_data = file.read()

    # Create a dictionary for encoding binary data to DNA nucleotides
    encoding_dict = {
        '00': 'A',
        '01': 'C',
        '10': 'G',
        '11': 'T'
    }

    # Encode the file data into DNA nucleotides
    dna_sequence = ''
    for byte in file_data:
        binary_byte = bin(byte)[2:].zfill(8)  # Convert each byte to 8-bit binary representation
        for i in range(0, 8, 2):  # Process two bits at a time
            dna_sequence += encoding_dict[binary_byte[i:i+2]]

    return dna_sequence


def decode_to_file(dna_sequence, output_file_path):
    # Create a dictionary for decoding DNA nucleotides to binary data
    decoding_dict = {
        'A': '00',
        'C': '01',
        'G': '10',
        'T': '11'
    }

    # Decode the DNA sequence into binary data
    binary_data = ''
    for nucleotide in dna_sequence:
        binary_data += decoding_dict[nucleotide]

    # Convert the binary data into bytes
    byte_array = bytearray()
    for i in range(0, len(binary_data), 8):
        byte = int(binary_data[i:i+8], 2)
        byte_array.append(byte)

    # Write the decoded binary data to a file
    with open(output_file_path, 'wb') as output_file:
        output_file.write(byte_array)

    print(f"The DNA sequence has been decoded and saved as '{output_file_path}'.")


# Check if the appropriate command-line arguments are provided
if len(sys.argv) < 3:
    print("Please provide the command-line arguments: -e <filename> to encode a file or -d <filename> to decode the DNA sequence.")
    sys.exit(1)

command = sys.argv[1]
file_path = sys.argv[2]
output_file_path = 'decoded_file.bin'

if command == '-e':
    # Encode the file into DNA sequence
    dna_sequence = encode_to_dna(file_path)

    # Write the DNA sequence to a text file
    with open(output_file_path, 'w') as output_file:
        output_file.write(dna_sequence)

    print(f"The file '{file_path}' has been encoded into DNA sequence and saved as '{output_file_path}'.")
elif command == '-d':
    # Read the DNA sequence from the specified file
    with open(file_path, 'r') as input_file:
        dna_sequence = input_file.read()

    # Decode the DNA sequence into a file
    decode_to_file(dna_sequence, output_file_path)
else:
    print("Invalid command-line argument. Please use -e <filename> to encode a file or -d <filename> to decode the DNA sequence.")
