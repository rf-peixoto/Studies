import hashlib
import sys

def hash_file(filename, algorithm):
    """ Compute hash of a given file using the specified algorithm. """
    try:
        # Create a hash object initialized with the chosen algorithm
        hash_obj = hashlib.new(algorithm)
    except ValueError:
        print(f"Error: {algorithm} is not a supported algorithm.")
        sys.exit(1)
    
    try:
        # Open the file in binary mode and read chunks to avoid using too much memory
        with open(filename, "rb") as file:
            while chunk := file.read(4096):  # Read in 4KB chunks
                hash_obj.update(chunk)
    except FileNotFoundError:
        print(f"Error: The file '{filename}' does not exist.")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

    # Return the hexadecimal representation of the digest
    return hash_obj.hexdigest()

def main():
    if len(sys.argv) == 2 and sys.argv[1] == 'list':
        print("Supported hash algorithms:")
        for algo in hashlib.algorithms_available:
            print(algo)
        sys.exit(0)
    elif len(sys.argv) != 3:
        print("Usage: python hash_script.py [file] [algorithm]")
        print("Or to list all available hash algorithms: python hash_script.py list")
        sys.exit(1)
    
    filename = sys.argv[1]
    algorithm = sys.argv[2]

    # Compute the hash
    result = hash_file(filename, algorithm)
    print(f"The {algorithm} hash of '{filename}' is: {result}")

if __name__ == "__main__":
    main()
