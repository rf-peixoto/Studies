class DEREncoder:
    @staticmethod
    def encode_integer(value):
        # Similar to the previous example, encode an integer in DER format
        if value < 0:
            raise ValueError("Negative values are not supported in this example.")
        value_bytes = value.to_bytes((value.bit_length() + 7) // 8, byteorder='big') or b'\x00'
        if value_bytes[0] & 0x80:
            value_bytes = b'\x00' + value_bytes
        type_tag = b'\x02'
        length_byte = len(value_bytes).to_bytes(1, byteorder='big')
        return bytearray(type_tag + length_byte + value_bytes)

    @staticmethod
    def encode_string(value):
        # Encode a string in DER format using UTF-8 encoding
        value_bytes = value.encode('utf-8')
        type_tag = b'\x0C'  # UTF8String tag in DER
        length_byte = len(value_bytes).to_bytes(1, byteorder='big')
        return bytearray(type_tag + length_byte + value_bytes)

    @staticmethod
    def decode_integer(data):
        if data[0] != 0x02:
            raise ValueError("Invalid integer type tag")
        length = data[1]
        integer_bytes = data[2:2 + length]
        return int.from_bytes(integer_bytes, byteorder='big', signed=False)

    @staticmethod
    def decode_string(data):
        if data[0] != 0x0C:  # Assuming UTF8String type tag for simplicity
            raise ValueError("Invalid string type tag")
        length = data[1]
        string_bytes = data[2:2 + length]
        return string_bytes.decode('utf-8')


# Example usage:
encoder = DEREncoder()
#encoder.add_integer(123456)
#encoder.add_string("Hello, DER!")

# This would be the raw payload, further work needed to wrap it for specific protocols like SSH or HTTP
#encoded_message = encoder.get_encoded_message()
#print(f"Encoded message: {encoded_message.hex()}")
