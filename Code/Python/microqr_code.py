import segno

def generate_micro_qr(data):
    # Generate a Micro QR Code
    qr = segno.make_micro(data, error='M')
    
    # Check the symbol size and raise an error if the data is too large
    symbol_size = qr.symbol_size()  # This is the correct way to get the symbol size
    if symbol_size[0] > 17:  # Size M4 is 17x17, the largest Micro QR Code
        raise ValueError("Data too long for any Micro QR Code version.")
    
    # Save the QR code as an image
    qr.save('micro_qr_code.png', scale=10)
    
    # Show the QR code
    qr.show(scale=10)

# Example usage
data = "12345678"  # Max int: 8
try:
    generate_micro_qr(data)
except ValueError as e:
    print(e)
