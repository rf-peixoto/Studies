import hashlib
import pydenticon as pid
import base64
import io
from PIL import Image, PngImagePlugin
import sys

def read_pgp_key(file_path):
    """Reads a PGP public key from a text file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            key_data = f.read()
        return key_data.strip()
    except Exception as e:
        print(f"Error reading PGP key: {e}")
        return None

def generate_identicon(key_data, output_path="identicon.png", size=256, grid_size=5, color_scheme=None, background_color=None, key_owner="Unknown"):
    """Generates an identicon from the full PGP key with embedded metadata (full key, key owner, and key hash)."""
    if not key_data:
        print("Invalid key data.")
        return
    
    # Compute SHA-256 hash of the key
    hashed_key = hashlib.sha256(key_data.encode("utf-8")).hexdigest()
    # Encode the full key using base64 to preserve formatting in metadata
    encoded_key = base64.b64encode(key_data.encode("utf-8")).decode("utf-8")
    
    # Define color scheme and background
    colors = color_scheme or ["#3f51b5", "#ff9800", "#4caf50", "#f44336"]
    background = background_color or "#ffffff"
    
    # Generate identicon using the hashed key for consistent output
    generator = pid.Generator(grid_size, grid_size, foreground=colors, background=background)
    identicon_data = generator.generate(hashed_key, size, size, output_format="png")
    
    try:
        # Use an in-memory buffer to embed metadata without double disk I/O.
        img = Image.open(io.BytesIO(identicon_data))
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("KeyOwner", key_owner)
        metadata.add_text("KeyHash", hashed_key)
        metadata.add_text("FullKey", encoded_key)
        
        # Save the image with embedded metadata directly to disk
        img.save(output_path, "PNG", pnginfo=metadata)
        print(f"Identicon saved as {output_path} with metadata:")
        print(f"  Key Owner: {key_owner}")
        print(f"  Key Hash: {hashed_key}")
    except Exception as e:
        print(f"Error processing image: {e}")

def extract_key_from_identicon(image_path):
    """Extracts metadata from an identicon image and decodes the full PGP key."""
    try:
        img = Image.open(image_path)
        metadata = img.info
        key_owner = metadata.get("KeyOwner", "Unknown")
        extracted_hash = metadata.get("KeyHash", "No hash found")
        encoded_key = metadata.get("FullKey", None)
        
        if encoded_key:
            full_key = base64.b64decode(encoded_key.encode("utf-8")).decode("utf-8")
        else:
            full_key = "No key found"
        
        print("Extracted metadata:")
        print(f"  Key Owner: {key_owner}")
        print(f"  Key Hash: {extracted_hash}")
        print(f"  Full Key: {full_key}")
        return key_owner, extracted_hash, full_key
    except Exception as e:
        print(f"Error decoding identicon: {e}")
        return None, None, None

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python pgp_identicon.py <mode> <file> [options]")
        print("Modes:")
        print("  encode <pgp_key_file> [size] [grid_size] [color1,color2,...] [background_color] [key_owner] - Generate an identicon")
        print("  decode <image_file> - Extract PGP key metadata from identicon")
        print("\nExamples:")
        print("  Generate identicon with default settings:")
        print("    python pgp_identicon.py encode mykey.txt")
        print("\n  Generate identicon with custom size and grid:")
        print("    python pgp_identicon.py encode mykey.txt 512 7")
        print("\n  Generate identicon with custom colors, background, and key owner:")
        print("    python pgp_identicon.py encode mykey.txt 512 7 '#ff0000,#00ff00,#0000ff' '#ffffff' 'Alice'")
        print("\n  Decode identicon to retrieve metadata:")
        print("    python pgp_identicon.py decode identicon.png")
        sys.exit(1)
    
    mode = sys.argv[1]
    file_path = sys.argv[2]
    
    if mode == "encode":
        key_data = read_pgp_key(file_path)
        size = int(sys.argv[3]) if len(sys.argv) > 3 else 256
        grid_size = int(sys.argv[4]) if len(sys.argv) > 4 else 5
        color_scheme = sys.argv[5].split(",") if len(sys.argv) > 5 else None
        background_color = sys.argv[6] if len(sys.argv) > 6 else None
        key_owner = sys.argv[7] if len(sys.argv) > 7 else "Unknown"
        generate_identicon(key_data, output_path="identicon.png", size=size, grid_size=grid_size,
                           color_scheme=color_scheme, background_color=background_color, key_owner=key_owner)
    elif mode == "decode":
        extract_key_from_identicon(file_path)
    else:
        print("Invalid mode. Use 'encode' or 'decode'.")
