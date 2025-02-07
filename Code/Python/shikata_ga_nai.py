#!/usr/bin/env python3
# Original version: https://github.com/rapid7/metasploit-framework/blob/master/modules/encoders/x86/shikata_ga_nai.rb
import argparse
import os
import random
import struct
import sys

class ShikataGaNaiEncoder:
    """
    An enhanced polymorphic XOR additive feedback encoder.

    Features:
      1. Additional instruction variants in each stub block.
      2. Dynamic register selection (for key, counter, and pointer).
      3. Multi-stage decoding (optional, via --multistage).
      4. Self-modifying code variants (optional, via --selfmod).
      5. Anti-debugging techniques (optional, via --antidebug).
      6. Variable block sizes (via --block-size).
      7. Dummy/junk instructions insertion.
      8. Secondary cryptographic layer (optional, via --crypto).
      9. Multi-architecture support (x32 [default] or x64, via --arch).

    The XOR additive feedback encoding is performed per block.
    The decoder stub (generated later) uses dynamic registers and randomized instruction variants.
    """
    def __init__(self, key: int = None, arch="x32", block_size: int = None,
                 multistage: bool = False, selfmod: bool = False,
                 antidebug: bool = False, crypto: bool = False):
        self.arch = arch.lower()
        if self.arch not in ["x32", "x64"]:
            sys.exit("Unsupported architecture. Choose x32 or x64.")
        # Default block sizes: x32 → 4 bytes; x64 → 8 bytes.
        if block_size is None:
            self.block_size = 4 if self.arch == "x32" else 8
        else:
            self.block_size = block_size
        # For x32, permit only 1, 2, or 4; for x64 allow 1, 2, 4, 8.
        if self.arch == "x32" and self.block_size not in [1, 2, 4]:
            sys.exit("For x32, allowed block sizes: 1, 2, or 4 bytes.")
        if self.arch == "x64" and self.block_size not in [1, 2, 4, 8]:
            sys.exit("For x64, allowed block sizes: 1, 2, 4, or 8 bytes.")
        self.multistage = multistage
        self.selfmod = selfmod
        self.antidebug = antidebug
        self.crypto = crypto
        # Generate a random initial key if none provided.
        if key is None:
            if self.arch == "x32":
                self.initial_key = random.randint(0, 0xffffffff)
            else:
                self.initial_key = random.randint(0, 0xffffffffffffffff)
        else:
            self.initial_key = key
        self.key_mask = 0xffffffff if self.arch == "x32" else 0xffffffffffffffff
        # Save original key for stub generation.
        self.encoding_key = self.initial_key
        # Always enable dynamic register selection.
        self.choose_registers()

    def choose_registers(self):
        """
        Randomly select registers for the key, counter, and pointer.
        For x32, allowed registers (except ESP) are chosen.
        For the pointer, exclude EBP (x32) or rbp (x64) to simplify addressing.
        """
        if self.arch == "x32":
            regs_all = [("eax", 0), ("ebx", 3), ("ecx", 1),
                        ("edx", 2), ("edi", 7), ("esi", 6), ("ebp", 5)]
            regs_ptr = [r for r in regs_all if r[0] != "ebp"]
        else:
            regs_all = [("rax", 0), ("rbx", 3), ("rcx", 1),
                        ("rdx", 2), ("rdi", 7), ("rsi", 6), ("rbp", 5)]
            regs_ptr = [r for r in regs_all if r[0] != "rbp"]
        self.regs = {}
        self.regs["key"] = random.choice(regs_all)
        available_counter = [r for r in regs_all if r != self.regs["key"]]
        self.regs["counter"] = random.choice(available_counter)
        available_ptr = [r for r in regs_ptr if r not in [self.regs["key"], self.regs["counter"]]]
        self.regs["ptr"] = random.choice(available_ptr)
        # (For debugging one might print self.regs, but we remain silent.)

    def _pad_data(self, data: bytes) -> bytes:
        """Pad data so its length is a multiple of the block size."""
        padding = (self.block_size - (len(data) % self.block_size)) % self.block_size
        return data + (b'\x00' * padding)

    def encode(self, data: bytes) -> bytes:
        """
        Perform XOR additive feedback encoding on the payload.
        For each block (of self.block_size bytes), interpret the block as a little‑endian
        integer and compute:
            encoded = original XOR (key & mask)
            key = (encoded + key) mod (2^(32) or 2^(64))
        """
        data = self._pad_data(data)
        encoded = bytearray()
        key = self.initial_key
        mask = (1 << (8 * self.block_size)) - 1
        for i in range(0, len(data), self.block_size):
            block = data[i:i+self.block_size]
            block_val = int.from_bytes(block, byteorder="little")
            encoded_val = block_val ^ (key & mask)
            encoded.extend(encoded_val.to_bytes(self.block_size, byteorder="little"))
            key = (encoded_val + key) & self.key_mask
        # Reset encoding_key for stub generation.
        self.encoding_key = self.initial_key
        return bytes(encoded)

    def secondary_encrypt(self, data: bytes) -> (bytes, int, int):
        """
        Apply a secondary encryption layer using a similar XOR additive feedback algorithm.
        Returns a tuple: (encrypted_data, secondary_key, block_count).
        (In a real multi-stage stub the secondary key would be embedded.)
        """
        if self.arch == "x32":
            sec_key = random.randint(0, 0xffffffff)
        else:
            sec_key = random.randint(0, 0xffffffffffffffff)
        key_mask = 0xffffffff if self.arch == "x32" else 0xffffffffffffffff
        encrypted = bytearray()
        mask = (1 << (8 * self.block_size)) - 1
        for i in range(0, len(data), self.block_size):
            block = data[i:i+self.block_size]
            block_val = int.from_bytes(block, byteorder="little")
            enc_val = block_val ^ (sec_key & mask)
            encrypted.extend(enc_val.to_bytes(self.block_size, byteorder="little"))
            sec_key = (enc_val + sec_key) & key_mask
        block_count = len(encrypted) // self.block_size
        return bytes(encrypted), sec_key, block_count

    # ─── Helper FUNCTIONS FOR x32 and x64 INSTRUCTION GENERATION ─────────────
    def mov_imm_x32(self, reg, value):
        # MOV reg, imm32: opcode = B8 + (reg_code), then 4-byte little-endian.
        return bytes([0xB8 + reg[1]]) + struct.pack("<I", value)

    def mov_imm_x64(self, reg, value):
        # For x64, use REX.W (0x48) and opcode B8+reg code, then imm64.
        return b"\x48" + bytes([0xB8 + reg[1]]) + struct.pack("<Q", value)

    def add_imm_x32(self, reg, imm):
        # ADD reg, imm8 (if possible) or imm32.
        if -128 <= imm <= 127:
            return bytes([0x83, 0xC0 + reg[1]]) + struct.pack("b", imm)
        else:
            return bytes([0x81, 0xC0 + reg[1]]) + struct.pack("<I", imm)

    def add_imm_x64(self, reg, imm):
        if -128 <= imm <= 127:
            return b"\x48" + bytes([0x83, 0xC0 + reg[1]]) + struct.pack("b", imm)
        else:
            return b"\x48" + bytes([0x81, 0xC0 + reg[1]]) + struct.pack("<I", imm)

    def dec_reg_x32(self, reg):
        # DEC reg: one-byte encoding = 0x48 + reg_code.
        return bytes([0x48 + reg[1]])

    def dec_reg_x64(self, reg):
        return b"\x48" + bytes([0x48 + reg[1]])

    def jnz_x32(self, offset):
        # JNZ rel8: opcode 75 then one-byte offset.
        return bytes([0x75]) + struct.pack("b", offset)

    def jnz_x64(self, offset):
        return bytes([0x75]) + struct.pack("b", offset)

    def xor_mem_reg_x32(self, mem_reg, reg):
        # XOR [mem_reg], reg: opcode 31 /r.
        modrm = (0 << 6) | (reg[1] << 3) | (mem_reg[1])
        return bytes([0x31, modrm])

    def xor_mem_reg_x64(self, mem_reg, reg):
        return b"\x48" + self.xor_mem_reg_x32(mem_reg, reg)

    def add_mem_reg_x32(self, mem_reg, reg):
        # ADD reg, [mem_reg]: opcode 03 /r.
        modrm = (0 << 6) | (reg[1] << 3) | (mem_reg[1])
        return bytes([0x03, modrm])

    def add_mem_reg_x64(self, mem_reg, reg):
        return b"\x48" + self.add_mem_reg_x32(mem_reg, reg)
    # ─────────────────────────────────────────────────────────────────────────────

    def get_pc_block(self):
        """
        Generate a get-PC block using the “call/pop” technique.
        The call instruction is followed by a pop into the pointer register.
        Several variants are randomized.
        """
        if self.arch == "x32":
            variants = [
                b"\xE8\x00\x00\x00\x00" + bytes([0x58 + self.regs["ptr"][1]]),
                b"\x90" + b"\xE8\x00\x00\x00\x00" + bytes([0x58 + self.regs["ptr"][1]])
            ]
            return random.choice(variants)
        else:
            # For x64, a similar technique is used. (Note: proper REX handling is simplified.)
            if self.regs["ptr"][1] == 0:
                return b"\xE8\x00\x00\x00\x00" + b"\x58"
            else:
                return b"\xE8\x00\x00\x00\x00" + b"\x48" + bytes([0x58 + self.regs["ptr"][1]])

    def init_block(self, block_count):
        """
        Generate an initialization block that moves the loop counter (block_count)
        into the counter register and the encoding key into the key register.
        Two variants (direct MOV and push/pop) are randomized and their order is swapped.
        """
        if self.arch == "x32":
            init_counter = self.mov_imm_x32(self.regs["counter"], block_count)
            init_key = self.mov_imm_x32(self.regs["key"], self.encoding_key)
        else:
            init_counter = self.mov_imm_x64(self.regs["counter"], block_count)
            init_key = self.mov_imm_x64(self.regs["key"], self.encoding_key)
        return init_counter + init_key if random.choice([True, False]) else init_key + init_counter

    def adjustment_block(self, offset):
        """Generate an adjustment block that adds an immediate offset to the pointer register."""
        if self.arch == "x32":
            return self.add_imm_x32(self.regs["ptr"], offset)
        else:
            return self.add_imm_x64(self.regs["ptr"], offset)

    def loop_block(self):
        """
        Generate the polymorphic decoding loop block.
        The basic operations are:
            xor [ptr], key
            add key, [ptr]
            add ptr, immediate (block size)
            dec counter
            jnz loop_start
        If --selfmod is enabled, one candidate variant inserts a self-modifying instruction.
        """
        if self.arch == "x32":
            code = b""
            code += self.xor_mem_reg_x32(self.regs["ptr"], self.regs["key"])
            code += self.add_mem_reg_x32(self.regs["ptr"], self.regs["key"])
            add_ptr = self.add_imm_x32(self.regs["ptr"], self.block_size)
            code += add_ptr
            code += self.dec_reg_x32(self.regs["counter"])
            # Compute relative offset for jnz: total length of loop block.
            total_loop = 2 + 2 + len(add_ptr) + 1 + 2  # (xor, add, add-imm, dec, jnz)
            code += self.jnz_x32(-total_loop)
            if self.selfmod:
                # Insert a self-modifying instruction (e.g. write 0x90 into memory).
                modrm = (1 << 6) | (0 << 3) | self.regs["ptr"][1]
                selfmod_code = b"\xC6" + bytes([modrm]) + struct.pack("b", -1) + b"\x90"
                code = selfmod_code + code
            return code
        else:
            code = b""
            code += self.xor_mem_reg_x64(self.regs["ptr"], self.regs["key"])
            code += self.add_mem_reg_x64(self.regs["ptr"], self.regs["key"])
            add_ptr = self.add_imm_x64(self.regs["ptr"], self.block_size)
            code += add_ptr
            code += self.dec_reg_x64(self.regs["counter"])
            total_loop = 2 + 2 + len(add_ptr) + 1 + 2
            code += self.jnz_x64(-total_loop)
            if self.selfmod:
                modrm = (1 << 6) | (0 << 3) | self.regs["ptr"][1]
                selfmod_code = b"\xC6" + bytes([modrm]) + struct.pack("b", -1) + b"\x90"
                code = selfmod_code + code
            return code

    def antidebug_block(self):
        """
        Generate a simple anti-debugging block.
        Uses pushfd/pushfq, pop into a register, an AND/cmp test, and an INT3 if triggered.
        """
        if self.arch == "x32":
            block = (b"\x9C"                # pushfd
                     b"\x58"                # pop eax
                     b"\x25\x00\x10\x00\x00"  # and eax, 0x1000
                     b"\x3D\x00\x10\x00\x00"  # cmp eax, 0x1000
                     b"\x74\x05"            # je skip 5 bytes
                     b"\xCC"                # int3
                     + b"\x90" * 5)         # NOP padding (skip label)
            return block
        else:
            block = (b"\x9C"                # pushfq
                     b"\x58"                # pop rax
                     b"\x48\x25\x00\x10\x00\x00"  # and rax, 0x1000
                     b"\x48\x3D\x00\x10\x00\x00"  # cmp rax, 0x1000
                     b"\x74\x05"
                     b"\xCC"
                     + b"\x90" * 5)
            return block

    def generate_basic_decoder_stub(self, block_count):
        """
        Generate a basic decoder stub without checking for multistage or crypto.
        This method is used as the base for both single-stage and multi-stage decoding.
        """
        if self.arch == "x32":
            stub = self.get_pc_block()
            if self.antidebug:
                stub += self.antidebug_block()
            init = self.init_block(block_count)
            adj = self.adjustment_block(len(init) +
                                        len(self.add_imm_x32(self.regs["ptr"], self.block_size)) +
                                        len(self.loop_block()))
            stub += init + adj + self.loop_block()
            return stub
        else:
            stub = self.get_pc_block()
            if self.antidebug:
                stub += self.antidebug_block()
            init = self.init_block(block_count)
            adj = self.adjustment_block(len(init) +
                                        len(self.add_imm_x64(self.regs["ptr"], self.block_size)) +
                                        len(self.loop_block()))
            stub += init + adj + self.loop_block()
            return stub

    def generate_decoder_stub(self, block_count):
        """
        Generate the final decoder stub.
        Depending on flags:
          - If --multistage is enabled, generate a two-stage stub.
          - If --crypto is enabled, prepend an extra decryption loop.
          Otherwise, simply return the basic decoder stub.
        """
        if self.multistage:
            return self.generate_multistage_stub(block_count)
        if self.crypto:
            return self.generate_full_stub(block_count)
        return self.generate_basic_decoder_stub(block_count)

    def generate_multistage_stub(self, main_block_count):
        """
        Multi-stage decoding: generate a primary stub that decodes an encoded secondary stub,
        which in turn decodes the main payload.
        """
        # Generate secondary stub using a secondary key.
        secondary_key = (random.randint(0, 0xffffffff) if self.arch == "x32"
                         else random.randint(0, 0xffffffffffffffff))
        old_key = self.encoding_key
        self.encoding_key = secondary_key
        # Use the basic stub to avoid recursion.
        secondary_stub = self.generate_basic_decoder_stub(main_block_count)
        encoded_secondary_stub = self.encode(secondary_stub)
        secondary_block_count = len(encoded_secondary_stub) // self.block_size
        self.encoding_key = old_key
        # Generate primary stub that will decode the secondary stub.
        if self.arch == "x32":
            primary = self.get_pc_block()
            if self.antidebug:
                primary += self.antidebug_block()
            init = self.init_block(secondary_block_count)
            adj = self.adjustment_block(len(init) +
                                        len(self.add_imm_x32(self.regs["ptr"], self.block_size)) +
                                        len(self.loop_block()))
            primary += init + adj + self.loop_block()
        else:
            primary = self.get_pc_block()
            if self.antidebug:
                primary += self.antidebug_block()
            init = self.init_block(secondary_block_count)
            adj = self.adjustment_block(len(init) +
                                        len(self.add_imm_x64(self.regs["ptr"], self.block_size)) +
                                        len(self.loop_block()))
            primary += init + adj + self.loop_block()
        # Append a short jump (primary stub jumps to secondary stub after decoding)
        jump = b"\xEB" + struct.pack("b", len(encoded_secondary_stub) + 2)
        primary += jump
        return primary + encoded_secondary_stub

    def generate_full_stub(self, block_count):
        """
        If the crypto layer is enabled, generate a stub that first decrypts the
        secondary (crypto) layer and then decodes the main payload.
        """
        if self.crypto:
            # Generate a crypto decryption stub.
            if self.arch == "x32":
                crypto_stub = self.get_pc_block()
                if self.antidebug:
                    crypto_stub += self.antidebug_block()
                init = self.init_block(block_count)
                adj = self.adjustment_block(len(init) +
                                            len(self.add_imm_x32(self.regs["ptr"], self.block_size)) +
                                            len(self.loop_block()))
                crypto_stub += init + adj + self.loop_block()
            else:
                crypto_stub = self.get_pc_block()
                if self.antidebug:
                    crypto_stub += self.antidebug_block()
                init = self.init_block(block_count)
                adj = self.adjustment_block(len(init) +
                                            len(self.add_imm_x64(self.regs["ptr"], self.block_size)) +
                                            len(self.loop_block()))
                crypto_stub += init + adj + self.loop_block()
            # Then append the “normal” decoder stub.
            normal_stub = self.generate_decoder_stub(block_count)
            return crypto_stub + normal_stub
        else:
            return self.generate_decoder_stub(block_count)

    def generate_decoder(self, block_count):
        """Entry point for stub generation – handles multistage and crypto options."""
        if self.multistage:
            return self.generate_multistage_stub(block_count)
        elif self.crypto:
            return self.generate_full_stub(block_count)
        else:
            return self.generate_decoder_stub(block_count)

# ─────────────────────────────────────────────────────────────────────────────
def main():
    epilog_text = (
        "Usage Examples:\n"
        "  1. Encode a file with full polymorphism and a decoder stub (x32, default 4-byte blocks):\n"
        "         python3 shikata_ga_nai.py -f input.bin -o encoded.bin --stub\n\n"
        "  2. Encode a string using multi-stage decoding and anti-debugging, targeting x64 with 8-byte blocks:\n"
        "         python3 shikata_ga_nai.py -s \"payload data\" --stub --multistage --antidebug --arch x64 --block-size 8\n\n"
        "  3. Enable self-modifying code and an additional cryptographic layer:\n"
        "         python3 shikata_ga_nai.py -f input.bin --stub --selfmod --crypto\n"
    )
    parser = argparse.ArgumentParser(
        description="Enhanced Polymorphic Shikata Ga Nai Encoder (Advanced)",
        epilog=epilog_text,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-f", "--file", help="Input file to encode")
    group.add_argument("-s", "--string", help="Input string to encode")
    parser.add_argument("-o", "--output", help="Output file (if omitted, writes to stdout)")
    parser.add_argument("--stub", action="store_true", help="Prepend the polymorphic decoder stub to the encoded payload")
    parser.add_argument("--multistage", action="store_true", help="Enable multi-stage decoding. In this mode the primary stub decodes a secondary stub which then decodes the main payload.")
    parser.add_argument("--selfmod", action="store_true", help="Enable self-modifying code in the decoder stub for added polymorphism")
    parser.add_argument("--antidebug", action="store_true", help="Insert anti-debugging techniques into the decoder stub")
    parser.add_argument("--crypto", action="store_true", help="Enable an additional cryptographic layer over the encoded payload")
    parser.add_argument("--arch", choices=["x32", "x64"], default="x32", help="Target architecture: x32 (default) or x64")
    parser.add_argument("--block-size", type=int, help="Block size in bytes. Default is 4 for x32 and 8 for x64. For x32 allowed sizes: 1, 2, or 4; for x64: 1, 2, 4, or 8.")
    parser.add_argument("--key", help="Specify the initial key as a hexadecimal value (e.g. 0x12345678)")
    args = parser.parse_args()

    # Read input data.
    if args.file:
        if not os.path.isfile(args.file):
            sys.exit("Error: File not found.")
        with open(args.file, "rb") as f:
            data = f.read()
    else:
        data = args.string.encode("latin-1")

    # Determine block size.
    if args.block_size is None:
        block_size = 4 if args.arch == "x32" else 8
    else:
        block_size = args.block_size

    # Determine key.
    if args.key:
        try:
            key = int(args.key, 16)
        except ValueError:
            sys.exit("Error: Invalid key format.")
    else:
        key = None

    encoder = ShikataGaNaiEncoder(key=key, arch=args.arch, block_size=block_size,
                                   multistage=args.multistage, selfmod=args.selfmod,
                                   antidebug=args.antidebug, crypto=args.crypto)
    encoded_payload = encoder.encode(data)
    block_count = len(encoded_payload) // encoder.block_size

    # If crypto is enabled, perform the secondary encryption layer.
    if args.crypto:
        encoded_payload, crypto_key, crypto_block_count = encoder.secondary_encrypt(encoded_payload)
        block_count = len(encoded_payload) // encoder.block_size

    if args.stub:
        stub = encoder.generate_decoder(block_count)
        output_data = stub + encoded_payload
    else:
        output_data = encoded_payload

    if args.output:
        try:
            with open(args.output, "wb") as f:
                f.write(output_data)
        except IOError as err:
            sys.exit(f"Error writing output file: {err}")
    else:
        sys.stdout.buffer.write(output_data)

if __name__ == "__main__":
    main()
