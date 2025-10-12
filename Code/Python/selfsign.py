#!/usr/bin/env python3
"""
signed_container_verbose.py

Verbose demonstration of "Signed container with a fixed placeholder" pattern.

Features:
 - Generates Ed25519 keypair (author).
 - Creates a container with:
     * canonical header (magic, version, algorithm)
     * author's public key embedded
     * fixed-size signature placeholder (64 bytes)
     * metadata length and metadata (watermark token)
     * payload (media bytes)
 - Computes SHA-256 over canonicalized bytes with placeholder zeroed, signs with Ed25519.
 - Writes signature into placeholder.
 - Verifies signature and watermark token.
 - Demonstrates tamper detection (flip one payload byte).
 - Prints human-friendly diagnostic information (hex/base64, hexdumps, offsets).
 - Writes two files to the current directory:
     - signed_container.bin
     - tampered_container.bin

Important:
 - This is an educational, practical demonstration. For production, use secure key storage (HSM),
   canonicalization specs, hardened player code signing, and robust watermarking for audio/video.
"""

import os
import sys
import struct
import base64
import hashlib
from dataclasses import dataclass
from typing import Optional, Tuple

# cryptography required: pip install cryptography
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives import serialization
except Exception as e:
    print("Missing dependency 'cryptography'. Install with: pip install cryptography")
    raise

# -----------------------------
# Formatting helpers (user-friendly)
# -----------------------------
def hexstr(b: bytes, max_len=96) -> str:
    if b is None:
        return "<none>"
    if len(b) <= max_len:
        return b.hex()
    return b[:max_len].hex() + f"...(+{len(b)-max_len} bytes)"

def b64(b: bytes, max_len=140) -> str:
    if b is None:
        return "<none>"
    s = base64.b64encode(b).decode()
    if len(s) <= max_len:
        return s
    return s[:max_len] + f"...(+{len(s)-max_len} chars)"

def hexdump(b: bytes, width=16, max_lines=24, start_offset=0) -> str:
    lines = []
    for i in range(0, min(len(b), width * max_lines), width):
        chunk = b[i : i + width]
        hex_part = " ".join(f"{x:02x}" for x in chunk)
        ascii_part = "".join(chr(x) if 32 <= x < 127 else "." for x in chunk)
        lines.append(f"{start_offset + i:08x}  {hex_part:<{width*3}}  |{ascii_part}|")
    if len(b) > width * max_lines:
        lines.append(f"... ({len(b) - width*max_lines} more bytes)")
    return "\n".join(lines)

# -----------------------------
# Container format (canonical)
# -----------------------------
MAGIC = b"SIGNCNTR"  # 8 bytes
VERSION = 1
ALG_ED25519 = 1
PUBKEY_LEN = 32
SIG_LEN = 64
HEADER_FMT = ">8sII"  # magic (8s), version (uint32), alg (uint32)
HEADER_SIZE = 8 + 4 + 4
FIXED_HEADER_SIZE = HEADER_SIZE + PUBKEY_LEN + SIG_LEN + 8  # + metadata_len (uint64)

@dataclass
class ContainerParseResult:
    author_pubkey_bytes: bytes
    signature_bytes: bytes
    metadata_bytes: bytes
    payload_bytes: bytes
    raw: bytes

# -----------------------------
# Key utilities
# -----------------------------
def generate_keys() -> Tuple[bytes, bytes]:
    """
    Generate an Ed25519 keypair.
    Returns (private_raw_bytes, public_raw_bytes).
    """
    priv = Ed25519PrivateKey.generate()
    priv_bytes = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = priv.public_key()
    pub_bytes = pub.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    return priv_bytes, pub_bytes

def load_private_key(raw: bytes) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(raw)

def load_public_key(raw: bytes) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(raw)

# -----------------------------
# Container creation & verification
# -----------------------------
def _build_header(author_pubkey: bytes) -> bytes:
    assert len(author_pubkey) == PUBKEY_LEN
    header = struct.pack(HEADER_FMT, MAGIC, VERSION, ALG_ED25519)
    header += author_pubkey
    header += b"\x00" * SIG_LEN  # signature placeholder (zeroed)
    return header

def _serialize_container(header: bytes, metadata: bytes, payload: bytes) -> bytes:
    metadata_len = len(metadata)
    container = bytearray()
    container += header
    container += struct.pack(">Q", metadata_len)  # metadata length as uint64 big-endian
    container += metadata
    container += payload
    return bytes(container)

def _compute_signing_hash(container_bytes: bytes) -> bytes:
    """
    Compute SHA-256 over canonicalized container where signature_placeholder is zeroed.
    The placeholder is at offset = HEADER_SIZE + PUBKEY_LEN, length = SIG_LEN.
    """
    placeholder_offset = HEADER_SIZE + PUBKEY_LEN
    if len(container_bytes) < placeholder_offset + SIG_LEN:
        raise ValueError("Container too small for placeholder")
    pre = container_bytes[:placeholder_offset]
    post = container_bytes[placeholder_offset + SIG_LEN :]
    h = hashlib.sha256()
    h.update(pre)
    h.update(b"\x00" * SIG_LEN)
    h.update(post)
    return h.digest()

def create_signed_container(
    payload: bytes,
    author_privkey_raw: bytes,
    author_pubkey_raw: Optional[bytes] = None,
    metadata: Optional[bytes] = None,
) -> bytes:
    """
    Create a signed container and return the bytes. The signature is written into the fixed placeholder.
    """
    if author_pubkey_raw is None:
        priv = load_private_key(author_privkey_raw)
        author_pubkey_raw = priv.public_key().public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)

    header = _build_header(author_pubkey_raw)
    metadata = metadata or b""
    container = _serialize_container(header, metadata, payload)

    signing_hash = _compute_signing_hash(container)
    priv = load_private_key(author_privkey_raw)
    signature = priv.sign(signing_hash)
    assert len(signature) == SIG_LEN

    placeholder_offset = HEADER_SIZE + PUBKEY_LEN
    container_mut = bytearray(container)
    container_mut[placeholder_offset : placeholder_offset + SIG_LEN] = signature
    return bytes(container_mut)

def parse_container(container_bytes: bytes) -> ContainerParseResult:
    if len(container_bytes) < FIXED_HEADER_SIZE:
        raise ValueError("Container too small")
    magic, version, alg = struct.unpack_from(HEADER_FMT, container_bytes, 0)
    if magic != MAGIC:
        raise ValueError("Bad magic value")
    if version != VERSION:
        raise ValueError("Unsupported version")
    if alg != ALG_ED25519:
        raise ValueError("Unsupported algorithm")

    offset = HEADER_SIZE
    author_pubkey_bytes = container_bytes[offset : offset + PUBKEY_LEN]
    offset += PUBKEY_LEN
    signature_bytes = container_bytes[offset : offset + SIG_LEN]
    offset += SIG_LEN
    metadata_len = struct.unpack_from(">Q", container_bytes, offset)[0]
    offset += 8
    metadata_bytes = container_bytes[offset : offset + metadata_len]
    offset += metadata_len
    payload_bytes = container_bytes[offset:]
    return ContainerParseResult(
        author_pubkey_bytes=author_pubkey_bytes,
        signature_bytes=signature_bytes,
        metadata_bytes=metadata_bytes,
        payload_bytes=payload_bytes,
        raw=container_bytes,
    )

def verify_container(container_bytes: bytes, expected_author_pubkey: Optional[bytes] = None) -> Tuple[bool, str]:
    """
    Verify the container signature. Optionally ensure the embedded author public key matches expected_author_pubkey.
    Returns (ok, message).
    """
    parsed = parse_container(container_bytes)

    if expected_author_pubkey is not None and parsed.author_pubkey_bytes != expected_author_pubkey:
        return False, "Author public key mismatch."

    signing_hash = _compute_signing_hash(parsed.raw)
    pub = load_public_key(parsed.author_pubkey_bytes)
    try:
        pub.verify(parsed.signature_bytes, signing_hash)
    except Exception as e:
        return False, f"Signature verification failed: {e}"
    return True, "Signature OK"

# -----------------------------
# Watermark token (per-copy forensic token)
# -----------------------------
def create_copy_with_watermark(payload: bytes, author_privkey_raw: bytes, buyer_id: str) -> bytes:
    """
    Create a signed container whose metadata contains:
      [buyer_id_len (uint16 BE)] [buyer_id (utf-8)] [token_signature (Ed25519 over SHA256(buyer_id || payload_hash))]
    This ties the buyer_id to the payload hash and is signed by the author (forensics).
    """
    payload_hash = hashlib.sha256(payload).digest()
    buyer_bytes = buyer_id.encode("utf-8")
    token_input_hash = hashlib.sha256(buyer_bytes + payload_hash).digest()
    priv = load_private_key(author_privkey_raw)
    token_sig = priv.sign(token_input_hash)
    metadata = struct.pack(">H", len(buyer_bytes)) + buyer_bytes + token_sig
    return create_signed_container(payload=payload, author_privkey_raw=author_privkey_raw, metadata=metadata)

def decode_and_verify_watermark(parsed: ContainerParseResult) -> Tuple[bool, Optional[str]]:
    """
    If metadata matches watermark layout, verify token signature and return (True, buyer_id).
    Otherwise return (False, None).
    """
    meta = parsed.metadata_bytes
    if len(meta) < 2 + SIG_LEN:
        return False, None
    buyer_len = struct.unpack_from(">H", meta, 0)[0]
    if 2 + buyer_len + SIG_LEN != len(meta):
        return False, None
    buyer_bytes = meta[2 : 2 + buyer_len]
    buyer_id = buyer_bytes.decode("utf-8", errors="replace")
    token_sig = meta[2 + buyer_len : 2 + buyer_len + SIG_LEN]
    payload_hash = hashlib.sha256(parsed.payload_bytes).digest()
    token_input_hash = hashlib.sha256(buyer_bytes + payload_hash).digest()
    pub = load_public_key(parsed.author_pubkey_bytes)
    try:
        pub.verify(token_sig, token_input_hash)
    except Exception:
        return False, None
    return True, buyer_id

# -----------------------------
# Demo flow (verbose output)
# -----------------------------
def demo(verbose: bool = True):
    # 1) Key generation (author)
    author_priv, author_pub = generate_keys()

    # 2) Demo payload (replace with real media bytes)
    payload = (b"PAYLOAD: Example multimedia bytes. This simulates a video or audio file.\n" * 20) + b"[END]\n"

    # 3) Create a per-buyer signed container
    buyer_id = "buyer_42@example.com"
    container_bytes = create_copy_with_watermark(payload, author_priv, buyer_id)

    # 4) Parse and compute derived values
    parsed = parse_container(container_bytes)
    signing_hash = _compute_signing_hash(container_bytes)
    payload_hash = hashlib.sha256(parsed.payload_bytes).digest()

    # 5) Verify original
    ok, msg = verify_container(container_bytes, expected_author_pubkey=author_pub)
    water_ok, water_buyer = decode_and_verify_watermark(parsed)

    # 6) Tamper: flip one bit in payload region to demonstrate detection
    tampered = bytearray(container_bytes)
    meta_len = struct.unpack_from(">Q", container_bytes, HEADER_SIZE + PUBKEY_LEN + SIG_LEN)[0]
    payload_offset = FIXED_HEADER_SIZE + meta_len
    if payload_offset < len(container_bytes):
        tampered[payload_offset] ^= 0x01  # flip a single bit
    tampered = bytes(tampered)
    tampered_ok, tampered_msg = verify_container(tampered, expected_author_pubkey=author_pub)

    # 7) Save outputs
    signed_path = os.path.join(os.getcwd(), "signed_container.bin")
    tampered_path = os.path.join(os.getcwd(), "tampered_container.bin")
    with open(signed_path, "wb") as f:
        f.write(container_bytes)
    with open(tampered_path, "wb") as f:
        f.write(tampered)

    # 8) Human-friendly printing
    if verbose:
        print("\n=== Signed Container Demo (Verbose) ===\n")
        print("1) Keys")
        print(" - Author public key (hex):", hexstr(author_pub))
        print(" - Author public key (base64):", b64(author_pub))
        print("\n2) Container layout & sizes")
        print(f" - Total container size: {len(container_bytes)} bytes")
        print(f" - Fixed header size (up to metadata_len): {FIXED_HEADER_SIZE} bytes (includes signature placeholder)")
        placeholder_offset = HEADER_SIZE + PUBKEY_LEN
        print(f" - Signature placeholder offset: {placeholder_offset} (length {SIG_LEN})")
        print(f" - Metadata length: {len(parsed.metadata_bytes)} bytes")
        print(f" - Payload length: {len(parsed.payload_bytes)} bytes")

        print("\n3) Hashes & signature")
        print(" - Signing hash (SHA-256 over canonicalized container):", signing_hash.hex())
        print(" - Payload SHA-256:", payload_hash.hex())
        print(" - Signature (hex):", hexstr(parsed.signature_bytes))
        print(" - Signature (base64):", b64(parsed.signature_bytes))

        print("\n4) Watermark / metadata")
        if water_ok:
            print(" - Watermark token valid. Buyer id:", water_buyer)
        else:
            print(" - Watermark token invalid or missing.")
        print(" - Metadata (hex, truncated):", hexstr(parsed.metadata_bytes, max_len=160))

        print("\n5) Payload preview (hexdump, first 256 bytes):")
        print(hexdump(parsed.payload_bytes[:256]))

        print("\n6) Signature placeholder region (nearby bytes):")
        left = max(0, placeholder_offset - 32)
        right = min(len(container_bytes), placeholder_offset + SIG_LEN + 32)
        snippet = container_bytes[left:right]
        print(hexdump(snippet, start_offset=left))

        print("\n7) Verification results")
        print(" - Original container verification:", ok, f"({msg})")
        print(" - Tampered container verification :", tampered_ok, f"({tampered_msg})")

        print("\n8) Files written to current directory:")
        print(" - Signed container:", signed_path)
        print(" - Tampered container:", tampered_path)
        print("\nNote: For production use, do not print or expose private keys. Use secure storage (HSM).")
    return {
        "author_priv": author_priv,
        "author_pub": author_pub,
        "container": container_bytes,
        "parsed": parsed,
        "signing_hash": signing_hash,
        "payload_hash": payload_hash,
        "verification": (ok, msg),
        "watermark": (water_ok, water_buyer),
        "tampered_verification": (tampered_ok, tampered_msg),
        "paths": (signed_path, tampered_path),
    }

# -----------------------------
# Entry point
# -----------------------------
if __name__ == "__main__":
    try:
        demo()
    except Exception as e:
        print("Error during demo:", e, file=sys.stderr)
        raise
