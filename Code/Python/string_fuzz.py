import random

def generate_fuzzing_strings(num_lines, max_line_size):
    # Define strange characters and combinations that could cause issues
    strange_chars = [
        "\x00", "\x1F", "\x7F",  # Control characters
        "„", "�", "�", "�", "�", "�",  # Commonly glitched characters in encoding
        "\xA0", "\xAD", "\xC2", "\xC3",  # Non-breaking space, soft hyphen, etc.
        "\xE2\x80\x8B", "\xE2\x80\x8C", "\xE2\x80\x8D", "\xE2\x80\x8E", "\xE2\x80\x8F",  # Zero-width spaces
        "\xC3\xA3", "\xC3\xB5", "\xC3\xB1", "\xC3\xB7",  # Portuguese and Spanish accented characters
        "=", "(", ")", "{", "}", "[", "]", "<", ">", "!", "@", "#", "$", "%", "^", "&", "*", "+", "|", "\\"
    ]
    
    # Generate the fuzzing strings
    fuzzing_lines = []
    for i in range(1, num_lines + 1):
        line_size = int((i / num_lines) * max_line_size)
        line = ''.join(random.choices(strange_chars, k=line_size))
        fuzzing_lines.append(line)
    
    return fuzzing_lines

# Parameters
num_lines = 100  # Number of lines to generate
max_line_size = 1000  # Maximum line size in characters

# Generate fuzzing strings
fuzzing_strings = generate_fuzzing_strings(num_lines, max_line_size)

# Save to a file
output_path = 'fuzzing_strings.txt'
with open(output_path, 'w', encoding='utf-8') as file:
    file.write("\n".join(fuzzing_strings))

output_path
