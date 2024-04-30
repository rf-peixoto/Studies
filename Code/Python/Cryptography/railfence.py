def encode_rail_fence_cipher(text, num_rails):
    if num_rails < 2:
        raise ValueError("Number of rails must be at least 2.")
    rails = [[] for _ in range(num_rails)]
    rail = 0
    direction = 1  # 1 for down, -1 for up
    
    for char in text:
        rails[rail].append(char)
        if rail == 0:
            direction = 1
        elif rail == num_rails - 1:
            direction = -1
        rail += direction
    
    encoded_message = ''.join(''.join(rail) for rail in rails)
    return encoded_message

def decode_rail_fence_cipher(encoded_text, num_rails):
    if num_rails < 2:
        raise ValueError("Number of rails must be at least 2.")
    positions = [0] * len(encoded_text)
    rail = 0
    direction = 1
    for i in range(len(encoded_text)):
        positions[i] = rail
        if rail == 0:
            direction = 1
        elif rail == num_rails - 1:
            direction = -1
        rail += direction

    rails = [[] for _ in range(num_rails)]
    idx = 0
    for r in range(num_rails):
        for i in range(len(encoded_text)):
            if positions[i] == r:
                rails[r].append(encoded_text[idx])
                idx += 1

    decoded_message = []
    rail = 0
    direction = 1
    for _ in range(len(encoded_text)):
        decoded_message.append(rails[rail].pop(0))
        if rail == 0:
            direction = 1
        elif rail == num_rails - 1:
            direction = -1
        rail += direction

    return ''.join(decoded_message)

# Example use
encoded_message = encode_rail_fence_cipher("HELLO WORLD", 3)
decoded_message = decode_rail_fence_cipher(encoded_message, 3)

print("Encoded:", encoded_message)
print("Decoded:", decoded_message)
