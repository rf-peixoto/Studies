#!/usr/bin/env python3
"""
wow36.py

A fictional Wow!-signal-inspired intensity codec.

Concept:
    - Uses the "Big Ear style" intensity alphabet:
        0-9, A-Z  -> intensity bins 0..35

    - The glyph 6EQUJ5 is treated as a synchronization header.
      It means: "this is a WOW-36 encoded transmission."

    - Text payload is UTF-8.
    - The payload is wrapped with:
        version byte
        payload length
        payload
        CRC32 checksum

    - Data is encoded in 6-character glyphs.
      Each data glyph contains:
        5 base36 chars = 24 bits / 3 bytes
        1 parity char  = simple glyph integrity check

Example:
    python wow36.py --encode "WE ARE HERE"

    python wow36.py --decode "6EQUJ5-01EKGF-0028NX-2P3K1F-37K802-2TIKYV-2Q8UD7-7M5FKX"

    python wow36.py --values "6EQUJ5"
"""

import argparse
import sys
import zlib


ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
VALUE = {ch: i for i, ch in enumerate(ALPHABET)}

SYNC_GLYPH = "6EQUJ5"
VERSION = 1

DATA_CORE_LEN = 5
GLYPH_LEN = 6

MAX_24BIT = 0xFFFFFF


class Wow36Error(Exception):
    pass


def normalize_code(code: str) -> str:
    """
    Normalize WOW-36 code.

    Allows separators:
        space, tab, newline, carriage return, hyphen, underscore

    Rejects anything outside the intensity alphabet.
    """
    result = []

    for ch in code.upper():
        if ch in ALPHABET:
            result.append(ch)
        elif ch in " \t\r\n-_":
            continue
        else:
            raise Wow36Error(f"Invalid character in code: {ch!r}")

    return "".join(result)


def int_to_base36(n: int, width: int = 0) -> str:
    if n < 0:
        raise ValueError("Negative values cannot be encoded as base36.")

    if n == 0:
        encoded = "0"
    else:
        chars = []
        while n:
            n, rem = divmod(n, 36)
            chars.append(ALPHABET[rem])
        encoded = "".join(reversed(chars))

    if width:
        if len(encoded) > width:
            raise Wow36Error(f"Value too large for {width} base36 characters.")
        encoded = encoded.rjust(width, "0")

    return encoded


def base36_to_int(s: str) -> int:
    n = 0

    for ch in s:
        if ch not in VALUE:
            raise Wow36Error(f"Invalid base36 character: {ch!r}")
        n = n * 36 + VALUE[ch]

    return n


def parity_for_core(core: str) -> str:
    """
    Simple parity/check symbol.

    This is not cryptographic integrity.
    It is just a glyph-level sanity check for fiction/protocol flavor.
    """
    total = sum(VALUE[ch] for ch in core)
    return ALPHABET[total % 36]


def encode_block_3bytes(block: bytes) -> str:
    """
    Encode exactly 3 bytes into one 6-character glyph.

    3 bytes = 24 bits.
    36^5 = 60,466,176, which is enough to represent 0..16,777,215.
    Therefore, 5 base36 symbols can encode 3 bytes.

    The 6th symbol is a parity/check symbol.
    """
    if len(block) != 3:
        raise Wow36Error("Internal error: data block must be exactly 3 bytes.")

    n = int.from_bytes(block, "big")

    if n > MAX_24BIT:
        raise Wow36Error("Internal error: 24-bit block overflow.")

    core = int_to_base36(n, width=DATA_CORE_LEN)
    return core + parity_for_core(core)


def decode_glyph_to_3bytes(glyph: str, index: int) -> bytes:
    if len(glyph) != GLYPH_LEN:
        raise Wow36Error(f"Invalid glyph length at glyph {index}: {glyph!r}")

    core = glyph[:DATA_CORE_LEN]
    received_parity = glyph[DATA_CORE_LEN]
    expected_parity = parity_for_core(core)

    if received_parity != expected_parity:
        raise Wow36Error(
            f"Parity check failed at glyph {index}: "
            f"{glyph!r}, expected final symbol {expected_parity!r}"
        )

    n = base36_to_int(core)

    if n > MAX_24BIT:
        raise Wow36Error(
            f"Glyph {index} decodes to a value larger than 24 bits: {glyph!r}"
        )

    return n.to_bytes(3, "big")


def encode_text(text: str, compact: bool = False) -> str:
    payload = text.encode("utf-8")

    header = bytes([VERSION]) + len(payload).to_bytes(4, "big")
    protected = header + payload

    checksum = zlib.crc32(protected) & 0xFFFFFFFF
    frame = protected + checksum.to_bytes(4, "big")

    padding_needed = (-len(frame)) % 3
    if padding_needed:
        frame += b"\x00" * padding_needed

    glyphs = [SYNC_GLYPH]

    for i in range(0, len(frame), 3):
        glyphs.append(encode_block_3bytes(frame[i:i + 3]))

    separator = "" if compact else "-"
    return separator.join(glyphs)


def decode_code(code: str) -> str | None:
    normalized = normalize_code(code)

    if not normalized:
        raise Wow36Error("Empty code.")

    if normalized == SYNC_GLYPH:
        return None

    if not normalized.startswith(SYNC_GLYPH):
        raise Wow36Error(
            f"Missing synchronization glyph. Expected code to start with {SYNC_GLYPH!r}."
        )

    body = normalized[len(SYNC_GLYPH):]

    if not body:
        return None

    if len(body) % GLYPH_LEN != 0:
        raise Wow36Error(
            f"Invalid body length. Data after {SYNC_GLYPH} must be divisible by {GLYPH_LEN}."
        )

    raw = bytearray()

    glyph_index = 0
    for i in range(0, len(body), GLYPH_LEN):
        glyph_index += 1
        glyph = body[i:i + GLYPH_LEN]
        raw.extend(decode_glyph_to_3bytes(glyph, glyph_index))

    if len(raw) < 9:
        raise Wow36Error("Decoded frame is too short.")

    version = raw[0]
    if version != VERSION:
        raise Wow36Error(f"Unsupported WOW-36 version: {version}")

    payload_len = int.from_bytes(raw[1:5], "big")

    payload_start = 5
    payload_end = payload_start + payload_len
    checksum_start = payload_end
    checksum_end = checksum_start + 4

    if checksum_end > len(raw):
        raise Wow36Error("Decoded frame is truncated.")

    payload = bytes(raw[payload_start:payload_end])
    received_crc = int.from_bytes(raw[checksum_start:checksum_end], "big")

    protected = bytes(raw[:payload_end])
    calculated_crc = zlib.crc32(protected) & 0xFFFFFFFF

    if received_crc != calculated_crc:
        raise Wow36Error(
            f"CRC32 mismatch. Received {received_crc:08X}, calculated {calculated_crc:08X}."
        )

    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as e:
        raise Wow36Error(f"Payload is not valid UTF-8: {e}") from e


def show_values(code: str) -> str:
    normalized = normalize_code(code)

    if not normalized:
        raise Wow36Error("Empty code.")

    lines = []

    for i in range(0, len(normalized), GLYPH_LEN):
        glyph = normalized[i:i + GLYPH_LEN]
        values = [VALUE[ch] for ch in glyph]
        values_str = " ".join(f"{v:02d}" for v in values)
        lines.append(f"{glyph:<6} -> {values_str}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="WOW-36 fictional intensity encoder/decoder."
    )

    mode = parser.add_mutually_exclusive_group(required=True)

    mode.add_argument(
        "-e",
        "--encode",
        metavar="TEXT",
        help="Encode text into WOW-36 intensity glyphs.",
    )

    mode.add_argument(
        "-d",
        "--decode",
        metavar="CODE",
        help="Decode WOW-36 intensity glyphs back into text.",
    )

    mode.add_argument(
        "-v",
        "--values",
        metavar="CODE",
        help="Show numeric intensity-bin values for a WOW-36 code.",
    )

    parser.add_argument(
        "--compact",
        action="store_true",
        help="When encoding, omit hyphen separators.",
    )

    args = parser.parse_args()

    try:
        if args.encode is not None:
            print(encode_text(args.encode, compact=args.compact))

        elif args.decode is not None:
            decoded = decode_code(args.decode)

            if decoded is None:
                print(f"<SYNC ONLY: {SYNC_GLYPH}>")
            else:
                print(decoded)

        elif args.values is not None:
            print(show_values(args.values))

    except Wow36Error as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())