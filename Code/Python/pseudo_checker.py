# Pseudo checker using Luhn algorithm
import random
from datetime import datetime, timedelta

def luhn_checksum(card_number):
    def digits_of(n):
        return [int(d) for d in str(n)]
    digits = digits_of(card_number)
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    checksum = 0
    checksum += sum(odd_digits)
    for d in even_digits:
        checksum += sum(digits_of(d*2))
    return checksum % 10

def is_luhn_valid(card_number):
    return luhn_checksum(card_number) == 0

def generate_card_number(bin_prefix, length):
    while True:
        # Generate the card number with the BIN, filling the rest with random digits
        num = bin_prefix + ''.join([str(random.randint(0, 9)) for _ in range(length - len(bin_prefix) - 1)])
        # Calculate the check digit that makes the card number pass the Luhn check
        check_digit = [str(x) for x in range(10) if is_luhn_valid(int(num + str(x)))]
        if check_digit:
            return num + check_digit[0]

def generate_expiration_date():
    today = datetime.now()
    future_year = today.year + random.randint(1, 5)  # Expiration year 1-5 years in the future
    future_month = random.randint(1, 12)
    return f"{future_month:02d}", str(future_year)

def generate_cvv():
    return str(random.randint(0, 999)).zfill(3)  # Generates a CVV with 3 digits

def generate_and_validate_cards(bin_prefix, num_cards):
    if len(bin_prefix) != 6:
        raise ValueError("BIN must be 6 digits long.")
    card_length = 16  # Most common length
    card_details = []
    for _ in range(num_cards):
        card_number = generate_card_number(bin_prefix, card_length)
        if is_luhn_valid(int(card_number)):
            expiration_month, expiration_year = generate_expiration_date()
            cvv = generate_cvv()
            card_detail = f"{card_number}|{expiration_month}|{expiration_year}|{cvv} - [VALID]"
            card_details.append(card_detail)
    return card_details

def main():
    bin_prefix = input("Enter the 6-digit BIN: ")
    num_cards = int(input("Enter the number of fake cards to generate: "))
    
    card_details = generate_and_validate_cards(bin_prefix, num_cards)
    
    # Writing the generated card details to a file
    with open("generated_cards_details.txt", "w") as file:
        for detail in card_details:
            file.write(detail + "\n")
    
    print(f"{len(card_details)} valid card numbers with details generated and saved to 'generated_cards_details.txt'.")

if __name__ == "__main__":
    main()

