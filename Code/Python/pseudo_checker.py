# Pseudo checker using Luhn algorithm

import random

def generate_card_number(bin_prefix):
    """
    Generates a single credit card number starting with the given bin_prefix.
    The generated number will be 16 digits long, including the BIN, random digits, and a Luhn check digit.
    """
    number = bin_prefix + ''.join([str(random.randint(0, 9)) for _ in range(9)])  # Generate 9 random digits.
    check_digit = calculate_luhn_check_digit(number)
    return number + str(check_digit)

def calculate_luhn_check_digit(number):
    """
    Calculates the check digit required to make the number valid according to the Luhn algorithm.
    """
    def digits_of(n):
        return [int(d) for d in str(n)]
    digits = digits_of(number)
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    checksum = sum(odd_digits)
    for d in even_digits:
        checksum += sum(digits_of(d*2))
    return (10 - (checksum % 10)) % 10

def generate_and_validate_cards(bin_prefix, num_cards):
    """
    Generates and validates num_cards credit card numbers starting with bin_prefix.
    Validated numbers are written to a file.
    """
    valid_cards = []
    for _ in range(num_cards):
        card_number = generate_card_number(bin_prefix)
        if validate_luhn(card_number):
            valid_cards.append(str(card_number) + '[+] LIVE')
        else:
            valid_cards.append(str(card_number) + '[-] DIE')

    # Write the valid cards to a file
    with open('valid_cards.txt', 'w') as f:
        for card in valid_cards:
            f.write("%s\n" % card)
    print(f"Generated and validated {len(valid_cards)} credit card numbers.")

def validate_luhn(card_number):
    """
    Validates a credit card number using the Luhn algorithm.
    """
    total = 0
    reverse_digits = card_number[::-1]
    for i in range(len(reverse_digits)):
        n = int(reverse_digits[i])
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0

if __name__ == "__main__":
    bin_prefix = input("Enter the 6-digit BIN: ")
    num_cards = int(input("Enter the number of fake cards to generate: "))
    generate_and_validate_cards(bin_prefix, num_cards)
