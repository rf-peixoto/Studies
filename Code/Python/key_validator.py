import hashlib

def generate_blake2b_hash(input_string):
    # Create a Blake2b hash object
    blake2b_hash = hashlib.blake2b(input_string.encode(), digest_size=64)  # 64-byte hash

    # Get the hexadecimal representation of the hash
    hash_hex = blake2b_hash.hexdigest()
    
    return hash_hex

def hash_to_ascii_list(hash_hex):
    ascii_list = [ord(char) for char in hash_hex]
    return ascii_list

def calculate_average(ascii_list):
    total = sum(ascii_list)
    average = total / len(ascii_list)
    return average

# Input string
input_string = input("Enter the string: ")

# Generate Blake2b hash
hash_result = generate_blake2b_hash(input_string)
print(f"Blake2b Hash: {hash_result}")

# Convert hash to ASCII list
ascii_list = hash_to_ascii_list(hash_result)
print("ASCII List:", ascii_list)

# Calculate and print the average value
average_value = calculate_average(ascii_list)
print(f"Average Value: {average_value}")
