import pyperclip
import time

# List of paste:
pastes = []

# Loop:
while True:
    if pyperclip.paste() != "None":
        value = pyperclip.paste()
        if value not in pastes:
            pastes.append(value)
            print("Paste collected: {0}".format(value))
    # Sleep
    time.sleep(5)
