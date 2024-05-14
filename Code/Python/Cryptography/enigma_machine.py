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
        # Pass through plugboard
        letter = self.plugboard.swap(letter)

        # Pass through rotors forward
        for rotor in self.rotors:
            letter = rotor.encode_forward(letter)

        # Pass through reflector
        letter = self.reflector.reflect(letter)

        # Pass through rotors backward
        for rotor in reversed(self.rotors):
            letter = rotor.encode_backward(letter)

        # Pass through plugboard again
        letter = self.plugboard.swap(letter)

        return letter

    def encode_message(self, message):
        encoded_message = ''
        for letter in message:
            if letter.isalpha():
                # Step rotors
                self.rotors[0].step()
                for i in range(len(self.rotors) - 1):
                    if self.rotors[i].position == self.rotors[i].notch:
                        self.rotors[i + 1].step()
                    else:
                        break

                # Encode letter
                encoded_message += self.encode_letter(letter)
            else:
                encoded_message += letter
        return encoded_message

# Example setup
rotor1 = Rotor("EKMFLGDQVZNTOWYHXUSPAIBRCJ", notch=16)  # Rotor I with notch at Q
rotor2 = Rotor("AJDKSIRUXBLHWTMCQGZNPYFVOE", notch=4)   # Rotor II with notch at E
rotor3 = Rotor("BDFHJLCPRTXVZNYEIWGAKMUSQO", notch=21)  # Rotor III with notch at V
reflector = Reflector("YRUHQSLDPXNGOKMIEBFZCWVJAT")      # Reflector B
plugboard = Plugboard({'A': 'B', 'B': 'A', 'C': 'D', 'D': 'C'})  # Simple plugboard

enigma = EnigmaMachine([rotor1, rotor2, rotor3], reflector, plugboard)
enigma.set_rotor_positions([0, 0, 0])

message = "HELLOENIGMA"
encoded_message = enigma.encode_message(message)
print(f"Encoded Message: {encoded_message}")
