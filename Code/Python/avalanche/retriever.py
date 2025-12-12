#!/usr/bin/env python3
"""
ffcfg_get.py — CLI reader for FFCFGv2 files (FF7-like slots + optional per-slot encryption)

Examples:
  # Read a plaintext slot value
  python ffcfg_get.py --file config.ffcfg --slot 1 --key api_url

  # Read an encrypted slot value (password required)
  python ffcfg_get.py --file config.ffcfg --slot 3 --key token --password "s3cret"

  # Read and print the slot metadata + all keys in that slot (optionally decrypted)
  python ffcfg_get.py --file config.ffcfg --slot 3 --list-keys --password "s3cret"
"""

import argparse
import hashlib
import os
import struct
import sys
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

# =========================
# Format constants (must match the GUI editor)
# =========================
MAGIC = b"FFCFGv2\0"
HEADER_SIZE = 9
SLOT_SIZE = 0x10F4
PAYLOAD_OFF = 0x0038
PAYLOAD_SIZE = SLOT_SIZE - PAYLOAD_OFF

SLOT_ID_OFF = 0x0004
SLOT_FLAGS_OFF = 0x0008
SLOT_ENC_OFF = 0x0009
SLOT_SALT_OFF = 0x000C  # 16
SLOT_NONCE_OFF = 0x001C  # 12
SLOT_TAG_OFF = 0x0028    # 16

FLAG_IN_USE = 0x01

# TLV record types
T_INT32, T_FLOAT64, T_UTF8, T_BYTES = 1, 2, 3, 4
TYPE_NAMES = {T_INT32: "int32", T_FLOAT64: "float64", T_UTF8: "utf8", T_BYTES: "bytes(hex)"}


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


# =========================
# Crypto (PBKDF2)
# =========================
def derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        200_000,
        dklen=32
    )


def aead_decrypt(password: str, salt: bytes, nonce: bytes, ciphertext: bytes, tag: bytes, aad: bytes) -> bytes:
    key = derive_key(password, salt)
    aead = ChaCha20Poly1305(key)
    return aead.decrypt(nonce, ciphertext + tag, aad)


def slot_aad(slot_id: int, flags: int, enc: int) -> bytes:
    # Must match GUI implementation to decrypt successfully
    return struct.pack("<I BB", slot_id, flags, enc)


# =========================
# TLV parsing
# =========================
def decode_value(rtype: int, raw: bytes) -> str:
    if rtype == T_INT32:
        if len(raw) != 4:
            return raw.hex()
        return str(struct.unpack("<i", raw)[0])
    if rtype == T_FLOAT64:
        if len(raw) != 8:
            return raw.hex()
        return str(struct.unpack("<d", raw)[0])
    if rtype == T_UTF8:
        return raw.decode("utf-8", errors="replace")
    if rtype == T_BYTES:
        return raw.hex()
    return raw.hex()


def iter_records(payload_plain: bytes):
    """
    Yields (rtype, key, value_str) until terminator (0,0,0) or malformed data.
    Terminator is 4 bytes: type=0, klen=0, vlen=0.
    """
    i = 0
    n = len(payload_plain)
    while i + 4 <= n:
        rtype, klen, vlen = struct.unpack_from("<BBH", payload_plain, i)
        if rtype == 0 and klen == 0 and vlen == 0:
            break
        i += 4
        if i + klen + vlen > n:
            break

        key_b = payload_plain[i:i + klen]
        i += klen
        val_b = payload_plain[i:i + vlen]
        i += vlen

        try:
            key = key_b.decode("utf-8", errors="replace")
        except Exception:
            key = "<decode_error>"

        if rtype not in TYPE_NAMES:
            # Unknown type: stop (do not interpret random padding)
            break

        yield (rtype, key, decode_value(rtype, val_b))


# =========================
# File reading
# =========================
class FFCFGFile:
    def __init__(self, path: str):
        self.path = path
        self.data = open(path, "rb").read()
        self._validate()
        self.slot_count = self.data[8]

    def _validate(self):
        if len(self.data) < HEADER_SIZE:
            raise ValueError("File too small.")
        if self.data[0:8] != MAGIC:
            raise ValueError("Bad magic (expected FFCFGv2).")
        slot_count = self.data[8]
        if slot_count <= 0:
            raise ValueError("Invalid slot_count.")
        expected = HEADER_SIZE + slot_count * SLOT_SIZE
        if len(self.data) != expected:
            raise ValueError(f"Unexpected file size: expected {expected}, got {len(self.data)}.")

    def slot_offset(self, slot_1based: int) -> int:
        return HEADER_SIZE + (slot_1based - 1) * SLOT_SIZE

    def read_slot_payload_plain(self, slot_1based: int, password: Optional[str]) -> tuple[bytes, dict]:
        """
        Returns (payload_plain_bytes, metadata_dict)
        """
        slot_1based = clamp(slot_1based, 1, self.slot_count)
        so = self.slot_offset(slot_1based)

        slot_id = struct.unpack_from("<I", self.data, so + SLOT_ID_OFF)[0]
        flags = struct.unpack_from("<B", self.data, so + SLOT_FLAGS_OFF)[0]
        enc = struct.unpack_from("<B", self.data, so + SLOT_ENC_OFF)[0]

        salt = self.data[so + SLOT_SALT_OFF: so + SLOT_SALT_OFF + 16]
        nonce = self.data[so + SLOT_NONCE_OFF: so + SLOT_NONCE_OFF + 12]
        tag = self.data[so + SLOT_TAG_OFF: so + SLOT_TAG_OFF + 16]
        payload = self.data[so + PAYLOAD_OFF: so + PAYLOAD_OFF + PAYLOAD_SIZE]

        meta = {
            "slot": slot_1based,
            "slot_id": slot_id,
            "in_use": bool(flags & FLAG_IN_USE),
            "encrypted": bool(enc),
        }

        if enc == 1:
            if not password:
                raise ValueError("Slot is encrypted; password is required.")
            aad = slot_aad(slot_id, flags, enc)
            plain = aead_decrypt(password, salt, nonce, payload, tag, aad)
            return plain, meta

        return payload, meta


def main():
    ap = argparse.ArgumentParser(description="Retrieve values from an FFCFGv2 file by slot/key (optionally decrypt slot).")
    ap.add_argument("--file", required=True, help="Path to .ffcfg file (FFCFGv2).")
    ap.add_argument("--slot", type=int, required=True, help="Slot number (1-based).")
    ap.add_argument("--key", help="Key to retrieve from that slot.")
    ap.add_argument("--password", help="Slot password (only needed if slot is encrypted).")
    ap.add_argument("--list-keys", action="store_true", help="List all keys in the slot (requires password if encrypted).")
    ap.add_argument("--show-meta", action="store_true", help="Print slot metadata (in_use/encrypted/slot_id).")

    args = ap.parse_args()

    if not args.key and not args.list_keys:
        ap.error("You must provide --key or --list-keys.")

    try:
        f = FFCFGFile(args.file)
        if args.slot < 1 or args.slot > f.slot_count:
            raise ValueError(f"Slot out of range: 1..{f.slot_count}")

        payload_plain, meta = f.read_slot_payload_plain(args.slot, args.password)

        if args.show_meta:
            print(f"slot={meta['slot']} slot_id={meta['slot_id']} in_use={meta['in_use']} encrypted={meta['encrypted']}")

        if args.list_keys:
            for rtype, key, value in iter_records(payload_plain):
                print(f"{key}\t[{TYPE_NAMES[rtype]}]")
            return

        # Lookup a key
        target = args.key
        for rtype, key, value in iter_records(payload_plain):
            if key == target:
                print(value)
                return

        # Not found
        print(f"Key not found: {target}", file=sys.stderr)
        sys.exit(2)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
