import hashlib

def drake_equation(params):
    # Parameters for the Drake Equation
    num_starforming_galaxies = params[0]
    avg_stars_per_galaxy = params[1]
    frac_planets_habitable = params[2]
    avg_habitable_planets = params[3]
    frac_life_possible = params[4]
    frac_intelligent_life = params[5]
    frac_communicative_life = params[6]
    
    # Calculate the estimated number of communicative civilizations
    estimated_civilizations = (
        num_starforming_galaxies * avg_stars_per_galaxy *
        frac_planets_habitable * avg_habitable_planets *
        frac_life_possible * frac_intelligent_life *
        frac_communicative_life
    )
    
    return estimated_civilizations

def is_prime(n):
    if n <= 1:
        return False
    if n <= 3:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True

def highest_prime(value):
    prime = value
    while not is_prime(prime):
        prime -= 1
    return prime

def custom_hash(average_value, ascii_list):
    num_params = len(ascii_list)
    params = [ord(str(char)[0]) for char in ascii_list]
    params.append(average_value)
    
    # Replace values with highest prime numbers
    prime_params = [highest_prime(value) for value in params]
    
    # Use the Drake Equation with prime numbers and average value as parameters
    custom_result = drake_equation(prime_params)
    
    return custom_result

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
    average = round(total / len(ascii_list))
    return average * (len(ascii_list) + total * (ascii_list[0] * ascii_list[1]))

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

# Calculate and print the custom hash
custom_result = custom_hash(average_value, ascii_list)
print(f"Custom Hash: {custom_result}")
