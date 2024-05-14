import tkinter as tk
from tkinter import ttk
import random
import string

class Rotor:
    def __init__(self, wiring, notch):
        self.wiring = wiring
        self.notch = notch
        self.position = 0

    def set_position(self, position):
        self.position = position

    def step(self):
        self.position = (self.position + 1) % 26

    def encode_forward(self, c):
        index = (ord(c) - ord('A') + self.position) % 26
        return chr((ord(self.wiring[index]) - ord('A') - self.position) % 26 + ord('A'))

    def encode_backward(self, c):
        index = (self.wiring.index(c) + self.position) % 26
        return chr((index - self.position) % 26 + ord('A'))

class Reflector:
    def __init__(self, wiring):
        self.wiring = wiring

    def reflect(self, c):
        return self.wiring[ord(c) - ord('A')]

class Plugboard:
    def __init__(self, wiring):
        self.wiring = wiring

    def swap(self, c):
        return self.wiring.get(c, c)

class EnigmaMachine:
    def __init__(self, rotors, reflector, plugboard):
        self.rotors = rotors
        self.reflector = reflector
        self.plugboard = plugboard

    def set_rotor_positions(self, positions):
        for rotor, pos in zip(self.rotors, positions):
            rotor.set_position(pos)

    def encode_letter(self, letter):
        letter = self.plugboard.swap(letter)
        for rotor in self.rotors:
            letter = rotor.encode_forward(letter)
        letter = self.reflector.reflect(letter)
        for rotor in reversed(self.rotors):
            letter = rotor.encode_backward(letter)
        letter = self.plugboard.swap(letter)
        return letter

    def encode_message(self, message):
        encoded_message = ''
        for letter in message:
            if letter.isalpha():
                self.rotors[0].step()
                for i in range(len(self.rotors) - 1):
                    if self.rotors[i].position == self.rotors[i].notch:
                        self.rotors[i + 1].step()
                    else:
                        break
                encoded_message += self.encode_letter(letter)
            else:
                encoded_message += letter
        return encoded_message

class EnigmaGUI(tk.Tk):
    def __init__(self, enigma):
        super().__init__()
        self.enigma = enigma
        self.title("Enigma Machine")
        self.geometry("500x400")
        self.create_widgets()

    def create_widgets(self):
        tk.Label(self, text="Enigma Machine", font=("Helvetica", 16)).grid(row=0, column=0, columnspan=4, pady=10)

        tk.Label(self, text="Message:").grid(row=1, column=0, pady=5, padx=5, sticky=tk.W)
        self.message_entry = tk.Entry(self, width=50)
        self.message_entry.grid(row=1, column=1, columnspan=3, pady=5, padx=5, sticky=tk.W)

        tk.Label(self, text="Rotor Positions (0-25):").grid(row=2, column=0, pady=5, padx=5, sticky=tk.W)
        self.rotor1_position = tk.Entry(self, width=5)
        self.rotor1_position.grid(row=2, column=1, pady=5, padx=5, sticky=tk.W)
        self.rotor2_position = tk.Entry(self, width=5)
        self.rotor2_position.grid(row=2, column=2, pady=5, padx=5, sticky=tk.W)
        self.rotor3_position = tk.Entry(self, width=5)
        self.rotor3_position.grid(row=2, column=3, pady=5, padx=5, sticky=tk.W)

        tk.Label(self, text="Rotor Wirings:").grid(row=3, column=0, pady=5, padx=5, sticky=tk.W)
        self.rotor1_wiring = tk.Entry(self, width=30)
        self.rotor1_wiring.grid(row=3, column=1, columnspan=3, pady=5, padx=5, sticky=tk.W)
        self.rotor2_wiring = tk.Entry(self, width=30)
        self.rotor2_wiring.grid(row=4, column=1, columnspan=3, pady=5, padx=5, sticky=tk.W)
        self.rotor3_wiring = tk.Entry(self, width=30)
        self.rotor3_wiring.grid(row=5, column=1, columnspan=3, pady=5, padx=5, sticky=tk.W)

        tk.Label(self, text="Reflector Wiring:").grid(row=6, column=0, pady=5, padx=5, sticky=tk.W)
        self.reflector_wiring = tk.Entry(self, width=30)
        self.reflector_wiring.grid(row=6, column=1, columnspan=3, pady=5, padx=5, sticky=tk.W)

        tk.Label(self, text="Plugboard Pairs:").grid(row=7, column=0, pady=5, padx=5, sticky=tk.W)
        self.plugboard_pairs = tk.Entry(self, width=30)
        self.plugboard_pairs.grid(row=7, column=1, columnspan=3, pady=5, padx=5, sticky=tk.W)

        self.random_setup_button = tk.Button(self, text="Random Setup", command=self.random_setup)
        self.random_setup_button.grid(row=8, column=0, columnspan=2, pady=10, padx=5, sticky=tk.E)

        self.encode_button = tk.Button(self, text="Encode", command=self.encode_message)
        self.encode_button.grid(row=8, column=2, columnspan=2, pady=10, padx=5, sticky=tk.W)

        self.encoded_message_label = tk.Label(self, text="Encoded Message: ", font=("Helvetica", 12))
        self.encoded_message_label.grid(row=9, column=0, columnspan=4, pady=10)

    def random_setup(self):
        rotor_wirings = [''.join(random.sample(string.ascii_uppercase, 26)) for _ in range(3)]
        reflector_wiring = ''.join(random.sample(string.ascii_uppercase, 26))
        plugboard_pairs = ' '.join([''.join(random.sample(string.ascii_uppercase, 2)) for _ in range(10)])
        rotor_positions = [random.randint(0, 25) for _ in range(3)]

        self.rotor1_wiring.delete(0, tk.END)
        self.rotor1_wiring.insert(0, rotor_wirings[0])
        self.rotor2_wiring.delete(0, tk.END)
        self.rotor2_wiring.insert(0, rotor_wirings[1])
        self.rotor3_wiring.delete(0, tk.END)
        self.rotor3_wiring.insert(0, rotor_wirings[2])
        self.reflector_wiring.delete(0, tk.END)
        self.reflector_wiring.insert(0, reflector_wiring)
        self.plugboard_pairs.delete(0, tk.END)
        self.plugboard_pairs.insert(0, plugboard_pairs)
        self.rotor1_position.delete(0, tk.END)
        self.rotor1_position.insert(0, rotor_positions[0])
        self.rotor2_position.delete(0, tk.END)
        self.rotor2_position.insert(0, rotor_positions[1])
        self.rotor3_position.delete(0, tk.END)
        self.rotor3_position.insert(0, rotor_positions[2])

    def encode_message(self):
        message = self.message_entry.get().upper()
        rotor1_pos = int(self.rotor1_position.get())
        rotor2_pos = int(self.rotor2_position.get())
        rotor3_pos = int(self.rotor3_position.get())
        
        rotor1_wiring = self.rotor1_wiring.get().upper()
        rotor2_wiring = self.rotor2_wiring.get().upper()
        rotor3_wiring = self.rotor3_wiring.get().upper()
        
        reflector_wiring = self.reflector_wiring.get().upper()
        
        plugboard_input = self.plugboard_pairs.get().upper().split()
        plugboard = {}
        for pair in plugboard_input:
            if len(pair) == 2:
                plugboard[pair[0]] = pair[1]
                plugboard[pair[1]] = pair[0]
        
        rotor1 = Rotor(rotor1_wiring, notch=16)
        rotor2 = Rotor(rotor2_wiring, notch=4)
        rotor3 = Rotor(rotor3_wiring, notch=21)
        reflector = Reflector(reflector_wiring)
        plugboard = Plugboard(plugboard)
        
        self.enigma = EnigmaMachine([rotor1, rotor2, rotor3], reflector, plugboard)
        self.enigma.set_rotor_positions([rotor1_pos, rotor2_pos, rotor3_pos])
        encoded_message = self.enigma.encode_message(message)
        self.encoded_message_label.config(text=f"Encoded Message: {encoded_message}")

# Example setup
rotor1 = Rotor("EKMFLGDQVZNTOWYHXUSPAIBRCJ", notch=16)
rotor2 = Rotor("AJDKSIRUXBLHWTMCQGZNPYFVOE", notch=4)
rotor3 = Rotor("BDFHJLCPRTXVZNYEIWGAKMUSQO", notch=21)
reflector = Reflector("YRUHQSLDPXNGOKMIEBFZCWVJAT")
plugboard = Plugboard({'A': 'B', 'B': 'A', 'C': 'D', 'D': 'C'})

enigma = EnigmaMachine([rotor1, rotor2, rotor3], reflector, plugboard)

if __name__ == "__main__":
    app = EnigmaGUI(enigma)
    app.mainloop()
