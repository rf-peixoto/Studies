import subprocess
import random
import argparse

# Copy your wallet.dat to C:\Users\User\AppData\Roaming\Bitcoin\wallets\NodeWallet or ~/.bitcoin/wallets
# Put this code and the english.txt together with bitcoin-cli and bitcoinid
# Start your node
# Run this
# Pray

def load_wordlist(filename):
    with open(filename, 'r') as file:
        words = file.read().split()
    return words

def generate_passphrases(wordlist, length, number):
    return [' '.join(random.sample(wordlist, length)) for _ in range(number)]

def try_unlock_wallet(passphrase):
    try:
        # Replace 'bitcoin-cli' with the full path if it's not in your PATH
        result = subprocess.run(['bitcoin-cli', 'walletpassphrase', "".format(passphrase), '60'], check=True, text=True, capture_output=True)
        return result.returncode == 0
    except subprocess.CalledProcessError:
        return False

def main():
    parser = argparse.ArgumentParser(description='Attempt to unlock a Bitcoin wallet with generated passphrases.')
    parser.add_argument('length', type=int, choices=[12, 24], help='Length of each passphrase (12 or 24 words)')
    parser.add_argument('number', type=int, help='Number of passphrases to generate')
    args = parser.parse_args()

    filename = 'english.txt'
    wordlist = load_wordlist(filename)

    passphrases = generate_passphrases(wordlist, args.length, args.number)

    # Save passphrases to a file
    with open('passphrases.txt', 'w') as file:
        for passphrase in passphrases:
            file.write(passphrase + '\n')

    # Try to unlock the wallet with each passphrase
    for passphrase in passphrases:
        if try_unlock_wallet(passphrase):
            print(f"Wallet unlocked with passphrase: {passphrase}")
            break
    else:
        print("Failed to unlock the wallet with the generated passphrases.")

if __name__ == "__main__":
    main()
