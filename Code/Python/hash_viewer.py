import sys

def compare_hashes(hash1, hash2):
    """Compare two hashes and print them with matching characters highlighted, styled in a 'cyberspace' theme."""
    if len(hash1) != len(hash2):
        print("Hashes are of different types or lengths and cannot be compared.")
        return

    # Initialize variables for comparison
    matches = 0
    styled_hash1 = ""
    styled_hash2 = ""

    # Styling for headers and footers
    header_footer = '+' + '-' * (len(hash1) + 2) + '+'

    # Compare character by character
    for i in range(len(hash1)):
        if hash1[i] == hash2[i]:
            matches += 1
            styled_hash1 += f"\033[42m\033[30m{hash1[i]}\033[0m"  # Green background, black text
            styled_hash2 += f"\033[42m\033[30m{hash2[i]}\033[0m"
        else:
            styled_hash1 += f"\033[41m\033[30m{hash1[i]}\033[0m"  # Red background, black text
            styled_hash2 += f"\033[41m\033[30m{hash2[i]}\033[0m"

    # Calculate similarity percentage
    similarity = matches / len(hash1) * 100

    # Print results with cyberpunk styling
    print("\033[1;34m" + header_footer + "\033[0m")
    print("\033[1;34m|\033[0m " + styled_hash1 + " \033[1;34m|\033[0m")
    print("\033[1;34m|\033[0m " + styled_hash2 + " \033[1;34m|\033[0m")
    print("\033[1;34m" + header_footer + "\033[0m")
    print(f"\033[1;36m[Similarity: {similarity:.2f}%]\033[0m")

# Example usage
hash1 = sys.argv[1]
hash2 = sys.argv[2]
compare_hashes(hash1, hash2)
