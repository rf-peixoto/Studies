import random
import threading
from datetime import datetime, timedelta
from queue import Queue

def luhn_checksum(card_number):
    def digits_of(n):
        return [int(d) for d in str(n)]
    digits = digits_of(card_number)
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    checksum = sum(odd_digits)
    for d in even_digits:
        checksum += sum(digits_of(d*2))
    return checksum % 10

def is_luhn_valid(card_number):
    return luhn_checksum(card_number) == 0

def generate_card_number(bin_prefix, length):
    num = bin_prefix + ''.join([str(random.randint(0, 9)) for _ in range(length - len(bin_prefix) - 1)])
    check_digit = [str(x) for x in range(10) if is_luhn_valid(int(num + str(x)))]
    if check_digit:
        return num + check_digit[0]

def generate_expiration_date():
    today = datetime.now()
    future_year = today.year + random.randint(1, 5)
    future_month = random.randint(1, 12)
    return f"{future_month:02d}", str(future_year)

def generate_cvv():
    return str(random.randint(0, 999)).zfill(3)

def generate_and_validate_card(bin_prefix, card_length, card_details):
    card_number = generate_card_number(bin_prefix, card_length)
    if card_number and is_luhn_valid(int(card_number)):
        expiration_month, expiration_year = generate_expiration_date()
        cvv = generate_cvv()
        card_details.put(f"{card_number}|{expiration_month}|{expiration_year}|{cvv} - [VALID]")

def card_generator_worker(bin_prefixes, num_cards, card_length, card_details):
    while card_details.qsize() < num_cards:
        bin_prefix = random.choice(bin_prefixes)
        generate_and_validate_card(bin_prefix, card_length, card_details)

def main():
    start_time = datetime.now()
    print(f"Start Time: {start_time}")

    with open("bins.txt", "r") as file:
        bin_prefixes = [line.strip() for line in file.readlines()]

    num_cards = int(input("Enter the number of valid cards to generate: "))
    card_length = 16
    card_details = Queue()

    threads = [threading.Thread(target=card_generator_worker, args=(bin_prefixes, num_cards, card_length, card_details)) for _ in range(10)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    output_filename = f"generated_cards_details_{timestamp}.txt"

    with open(output_filename, "w") as file:
        while not card_details.empty():
            file.write(card_details.get() + "\n")

    end_time = datetime.now()
    print(f"End Time: {end_time}")
    print(f"Execution Time: {end_time - start_time}")
    print(f"{num_cards} valid card numbers with details generated and saved to '{output_filename}'.")

if __name__ == "__main__":
    main()
