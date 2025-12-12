import os
import struct
import hashlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import scrolledtext

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

# =========================
# FFCFGv2 format (FF7-like)
# =========================
MAGIC = b"FFCFGv2\0"          # 8 bytes
HEADER_SIZE = 9              # magic(8) + slot_count(1)
DEFAULT_SLOTS = 15
SLOT_SIZE = 0x10F4           # 4340 bytes
PAYLOAD_OFF = 0x0038
PAYLOAD_SIZE = SLOT_SIZE - PAYLOAD_OFF

# Slot header fields
# 0x0000..0x0003 legacy/checksum (unused here)
SLOT_ID_OFF    = 0x0004      # u32
SLOT_FLAGS_OFF = 0x0008      # u8  (bit0 in_use)
SLOT_ENC_OFF   = 0x0009      # u8  (0 plaintext, 1 encrypted)
SLOT_RSVD_OFF  = 0x000A      # u16
SLOT_SALT_OFF  = 0x000C      # 16 bytes
SLOT_NONCE_OFF = 0x001C      # 12 bytes
SLOT_TAG_OFF   = 0x0028      # 16 bytes

FLAG_IN_USE = 0x01

# Record types (TLV)
T_INT32, T_FLOAT64, T_UTF8, T_BYTES = 1, 2, 3, 4
TYPE_NAMES = {T_INT32: "int32", T_FLOAT64: "float64", T_UTF8: "utf8", T_BYTES: "bytes(hex)"}
NAME_TO_TYPE = {v: k for k, v in TYPE_NAMES.items()}

# =========================
# Utilities
# =========================
def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))

# =========================
# Crypto (memory-safe KDF)
# =========================
def derive_key(password: str, salt: bytes) -> bytes:
    # PBKDF2: bounded memory footprint
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        200_000,
        dklen=32
    )

def aead_encrypt(password: str, salt: bytes, nonce: bytes, plaintext: bytes, aad: bytes) -> tuple[bytes, bytes]:
    key = derive_key(password, salt)
    aead = ChaCha20Poly1305(key)
    ct_and_tag = aead.encrypt(nonce, plaintext, aad)
    return ct_and_tag[:-16], ct_and_tag[-16:]

def aead_decrypt(password: str, salt: bytes, nonce: bytes, ciphertext: bytes, tag: bytes, aad: bytes) -> bytes:
    key = derive_key(password, salt)
    aead = ChaCha20Poly1305(key)
    return aead.decrypt(nonce, ciphertext + tag, aad)

# =========================
# TLV helpers
# =========================
class Record:
    def __init__(self, rtype: int, key: str, value: str):
        self.rtype = rtype
        self.key = key
        self.value = value  # stored as string in UI (bytes stored as hex string)

def encode_value(rtype: int, v: str) -> bytes:
    if rtype == T_INT32:
        return struct.pack("<i", int(v, 10))
    if rtype == T_FLOAT64:
        return struct.pack("<d", float(v))
    if rtype == T_UTF8:
        return v.encode("utf-8")
    if rtype == T_BYTES:
        hs = v.replace(" ", "").replace("\n", "").replace("\t", "")
        if len(hs) % 2 != 0:
            raise ValueError("bytes(hex): hex string must have an even number of characters.")
        return bytes.fromhex(hs)
    raise ValueError("Invalid type.")

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

def pack_records(records: list[Record], random_fill_padding: bool) -> bytes:
    """
    TLV:
      type(u8), klen(u8), vlen(u16 LE), key, value
    Terminator: 0,0,0 (4 bytes) so we can stop even with random padding.
    """
    out = bytearray()
    for r in records:
        kb = r.key.encode("utf-8")
        if len(kb) > 255:
            raise ValueError("Key too long (max 255 UTF-8 bytes).")
        vb = encode_value(r.rtype, r.value)
        if len(vb) > 65535:
            raise ValueError("Value too long (max 65535 bytes).")
        out.extend(struct.pack("<BBH", r.rtype, len(kb), len(vb)))
        out.extend(kb)
        out.extend(vb)

    out.extend(b"\x00\x00\x00\x00")  # terminator

    if len(out) > PAYLOAD_SIZE:
        raise ValueError("Slot overflow: payload exceeds fixed capacity.")

    rem = PAYLOAD_SIZE - len(out)
    out.extend(os.urandom(rem) if random_fill_padding else b"\x00" * rem)
    return bytes(out)

def unpack_records(payload_plain: bytes) -> list[Record]:
    recs: list[Record] = []
    i = 0
    n = len(payload_plain)
    while i + 4 <= n:
        rtype, klen, vlen = struct.unpack_from("<BBH", payload_plain, i)
        if rtype == 0 and klen == 0 and vlen == 0:
            break
        i += 4
        if i + klen + vlen > n:
            break
        key = payload_plain[i:i+klen].decode("utf-8", errors="replace")
        i += klen
        val_raw = payload_plain[i:i+vlen]
        i += vlen

        if rtype not in TYPE_NAMES:
            # unknown -> stop to avoid interpreting garbage
            break

        recs.append(Record(rtype, key, decode_value(rtype, val_raw)))
    return recs

# =========================
# GUI editor
# =========================
class Editor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Avalanche")
        self.geometry("980x600")

        self.path = None
        self.buf: bytearray | None = None
        self.slot_count = DEFAULT_SLOTS

        # UI state
        self.slot_var = tk.IntVar(value=1)
        self.inuse_var = tk.BooleanVar(value=False)
        self.encrypt_var = tk.BooleanVar(value=True)
        self.randfill_var = tk.BooleanVar(value=True)
        self.password_var = tk.StringVar(value="")

        self.records: list[Record] = []

        self._build_ui()
        self._enable(False)

    # ----- UI layout -----
    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Button(top, text="New", command=self.new_file).pack(side="left")
        ttk.Button(top, text="Open", command=self.open_file).pack(side="left", padx=6)
        ttk.Button(top, text="Save as", command=self.save_as).pack(side="left", padx=6)
        ttk.Button(top, text="Overwrite", command=self.overwrite).pack(side="left")

        self.path_label = ttk.Label(top, text="(no file)")
        self.path_label.pack(side="left", padx=12)

        body = ttk.Frame(self, padding=(10, 0, 10, 10))
        body.pack(fill="both", expand=True)

        # Left: slot + security
        left = ttk.Frame(body)
        left.pack(side="left", fill="y", padx=(0, 10))

        slot_box = ttk.LabelFrame(left, text="Slot", padding=10)
        slot_box.pack(fill="x", pady=(0, 10))

        row = ttk.Frame(slot_box)
        row.pack(fill="x")
        ttk.Label(row, text="Number:").pack(side="left")
        self.slot_spin = ttk.Spinbox(
            row, from_=1, to=DEFAULT_SLOTS, width=5,
            textvariable=self.slot_var, command=self.load_slot
        )
        self.slot_spin.pack(side="left", padx=6)

        ttk.Button(slot_box, text="Load (decrypt if needed)", command=self.load_slot).pack(fill="x", pady=(8, 0))

        sec = ttk.LabelFrame(left, text="Slot security", padding=10)
        sec.pack(fill="x")

        self.inuse_chk = ttk.Checkbutton(sec, text="Slot in use", variable=self.inuse_var)
        self.inuse_chk.pack(anchor="w")

        self.encrypt_chk = ttk.Checkbutton(sec, text="Encrypt this slot", variable=self.encrypt_var)
        self.encrypt_chk.pack(anchor="w", pady=(6, 0))

        ttk.Label(sec, text="Slot password:").pack(anchor="w", pady=(8, 0))
        self.pw_entry = ttk.Entry(sec, textvariable=self.password_var, show="•")
        self.pw_entry.pack(fill="x", pady=(2, 6))

        self.rand_chk = ttk.Checkbutton(sec, text="Random-fill payload padding", variable=self.randfill_var)
        self.rand_chk.pack(anchor="w")

        ttk.Button(sec, text="Write slot (save + encrypt)", command=self.write_slot).pack(fill="x", pady=(10, 0))

        # Middle: record list
        mid = ttk.Frame(body)
        mid.pack(side="left", fill="y", padx=(0, 10))

        lst = ttk.LabelFrame(mid, text="Records", padding=10)
        lst.pack(fill="both", expand=True)

        self.listbox = tk.Listbox(lst, width=34, height=20)
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self.on_select())

        btnrow = ttk.Frame(lst)
        btnrow.pack(fill="x", pady=(8, 0))
        ttk.Button(btnrow, text="Add", command=self.add_record).pack(side="left", expand=True, fill="x")
        ttk.Button(btnrow, text="Delete", command=self.delete_record).pack(side="left", expand=True, fill="x", padx=6)

        # Right: record editor
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        edt = ttk.LabelFrame(right, text="Record editor", padding=10)
        edt.pack(fill="both", expand=True)

        ttk.Label(edt, text="Key:").pack(anchor="w")
        self.key_entry = ttk.Entry(edt)
        self.key_entry.pack(fill="x", pady=(0, 8))

        ttk.Label(edt, text="Type:").pack(anchor="w")
        self.type_var = tk.StringVar(value="utf8")
        self.type_box = ttk.Combobox(
            edt, values=list(NAME_TO_TYPE.keys()),
            state="readonly", textvariable=self.type_var, width=14
        )
        self.type_box.pack(anchor="w", pady=(0, 8))

        ttk.Label(edt, text="Value:").pack(anchor="w")
        self.val_text = scrolledtext.ScrolledText(edt, height=10, wrap="word")
        self.val_text.pack(fill="both", expand=True)

        ttk.Button(edt, text="Apply to selected", command=self.apply_record).pack(anchor="e", pady=(10, 0))

        self.status = ttk.Label(self, text="")
        self.status.pack(fill="x", padx=10, pady=(0, 10))

    def _enable(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for w in [
            self.slot_spin, self.inuse_chk, self.encrypt_chk, self.pw_entry, self.rand_chk,
            self.listbox, self.key_entry, self.type_box, self.val_text
        ]:
            try:
                w.config(state=state)
            except Exception:
                pass

    # ----- File format helpers -----
    def _expected_size(self) -> int:
        return HEADER_SIZE + self.slot_count * SLOT_SIZE

    def _slot_off(self, slot_1based: int) -> int:
        return HEADER_SIZE + (slot_1based - 1) * SLOT_SIZE

    def _slot_aad(self, slot_id: int, flags: int, enc: int) -> bytes:
        return struct.pack("<I BB", slot_id, flags, enc)

    # ----- Actions: New/Open/Save -----
    def new_file(self):
        self.slot_count = DEFAULT_SLOTS
        total = self._expected_size()

        # Random-fill the file BUT ensure each slot contains a valid empty TLV payload.
        buf = bytearray(os.urandom(total))
        buf[0:8] = MAGIC
        buf[8] = self.slot_count

        for i in range(1, self.slot_count + 1):
            so = self._slot_off(i)

            struct.pack_into("<I", buf, so + 0x0000, 0)              # legacy/checksum
            struct.pack_into("<I", buf, so + SLOT_ID_OFF, i)         # slot_id
            struct.pack_into("<B", buf, so + SLOT_FLAGS_OFF, 0)      # flags
            struct.pack_into("<B", buf, so + SLOT_ENC_OFF, 0)        # enc=0 (plaintext)

            # random salt/nonce/tag (unused for plaintext but keeps file "non-patterned")
            buf[so + SLOT_SALT_OFF: so + SLOT_SALT_OFF + 16] = os.urandom(16)
            buf[so + SLOT_NONCE_OFF: so + SLOT_NONCE_OFF + 12] = os.urandom(12)
            buf[so + SLOT_TAG_OFF:  so + SLOT_TAG_OFF  + 16] = os.urandom(16)

            # valid empty payload (terminator + random padding)
            empty_payload = pack_records([], random_fill_padding=True)
            buf[so + PAYLOAD_OFF: so + PAYLOAD_OFF + PAYLOAD_SIZE] = empty_payload

        self.buf = buf
        self.path = None
        self.path_label.config(text="(new file — unsaved)")
        self._enable(True)
        self.slot_spin.config(to=self.slot_count)
        self.slot_var.set(1)
        self.password_var.set("")
        self.load_slot()
        self.status.config(text="New file created (valid empty slots). Use Save as to write to disk.")

    def open_file(self):
        p = filedialog.askopenfilename(filetypes=[("FFCFG", "*.ffcfg"), ("All files", "*.*")])
        if not p:
            return
        data = open(p, "rb").read()
        if len(data) < HEADER_SIZE or data[0:8] != MAGIC:
            messagebox.showerror("Invalid file", "Bad magic. This editor expects FFCFGv2.")
            return
        slot_count = data[8]
        expected = HEADER_SIZE + slot_count * SLOT_SIZE
        if len(data) != expected:
            messagebox.showerror("Invalid file", f"Unexpected size: expected {expected}, got {len(data)}.")
            return

        self.path = p
        self.buf = bytearray(data)
        self.slot_count = slot_count

        self.path_label.config(text=os.path.basename(p))
        self._enable(True)
        self.slot_spin.config(to=self.slot_count)
        self.slot_var.set(clamp(self.slot_var.get(), 1, self.slot_count))
        self.load_slot()
        self.status.config(text="File loaded. If a slot is encrypted, enter its password and click Load.")

    def save_as(self):
        if not self.buf:
            return
        p = filedialog.asksaveasfilename(
            defaultextension=".ffcfg",
            filetypes=[("FFCFG", "*.ffcfg"), ("All files", "*.*")]
        )
        if not p:
            return
        open(p, "wb").write(self.buf)
        self.path = p
        self.path_label.config(text=os.path.basename(p))
        self.status.config(text="Saved successfully.")

    def overwrite(self):
        if not self.buf or not self.path:
            return
        if not messagebox.askyesno("Confirm overwrite", "Overwrite the current file on disk?"):
            return
        open(self.path, "wb").write(self.buf)
        self.status.config(text="Overwritten successfully.")

    # ----- Slot load/write -----
    def load_slot(self):
        if not self.buf:
            return
        slot = clamp(self.slot_var.get(), 1, self.slot_count)
        self.slot_var.set(slot)

        so = self._slot_off(slot)
        slot_id = struct.unpack_from("<I", self.buf, so + SLOT_ID_OFF)[0]
        flags = struct.unpack_from("<B", self.buf, so + SLOT_FLAGS_OFF)[0]
        enc = struct.unpack_from("<B", self.buf, so + SLOT_ENC_OFF)[0]

        self.inuse_var.set(bool(flags & FLAG_IN_USE))
        self.encrypt_var.set(bool(enc))

        salt = bytes(self.buf[so + SLOT_SALT_OFF:  so + SLOT_SALT_OFF + 16])
        nonce = bytes(self.buf[so + SLOT_NONCE_OFF: so + SLOT_NONCE_OFF + 12])
        tag = bytes(self.buf[so + SLOT_TAG_OFF:    so + SLOT_TAG_OFF + 16])
        payload = bytes(self.buf[so + PAYLOAD_OFF: so + PAYLOAD_OFF + PAYLOAD_SIZE])

        try:
            if enc == 1:
                pw = self.password_var.get()
                if not pw:
                    self.records = []
                    self._refresh_list()
                    self.status.config(text=f"Slot {slot:02d} is encrypted. Enter password and click Load.")
                    return
                aad = self._slot_aad(slot_id, flags, enc)
                plain = aead_decrypt(pw, salt, nonce, payload, tag, aad)
            else:
                plain = payload

            self.records = unpack_records(plain)
            self._refresh_list()
            self._clear_editor()
            mode = "encrypted" if enc else "plaintext"
            self.status.config(text=f"Slot {slot:02d} loaded ({mode}). Records: {len(self.records)}.")
        except Exception as e:
            self.records = []
            self._refresh_list()
            messagebox.showerror("Load failed", f"Could not load slot (wrong password or corrupted data).\n\n{e}")

    def write_slot(self):
        if not self.buf:
            return
        slot = clamp(self.slot_var.get(), 1, self.slot_count)
        so = self._slot_off(slot)

        slot_id = struct.unpack_from("<I", self.buf, so + SLOT_ID_OFF)[0]

        flags = struct.unpack_from("<B", self.buf, so + SLOT_FLAGS_OFF)[0]
        flags = (flags | FLAG_IN_USE) if self.inuse_var.get() else (flags & ~FLAG_IN_USE)
        struct.pack_into("<B", self.buf, so + SLOT_FLAGS_OFF, flags)

        # Pack plaintext payload
        try:
            plain_payload = pack_records(self.records, random_fill_padding=self.randfill_var.get())
        except Exception as e:
            messagebox.showerror("Write failed", str(e))
            return

        if self.encrypt_var.get():
            pw = self.password_var.get()
            if not pw:
                messagebox.showerror("Missing password", "Encryption is enabled. Provide a slot password.")
                return

            salt = os.urandom(16)
            nonce = os.urandom(12)
            enc = 1
            aad = self._slot_aad(slot_id, flags, enc)
            ct, tag = aead_encrypt(pw, salt, nonce, plain_payload, aad)

            struct.pack_into("<B", self.buf, so + SLOT_ENC_OFF, 1)
            self.buf[so + SLOT_SALT_OFF:  so + SLOT_SALT_OFF + 16] = salt
            self.buf[so + SLOT_NONCE_OFF: so + SLOT_NONCE_OFF + 12] = nonce
            self.buf[so + SLOT_TAG_OFF:   so + SLOT_TAG_OFF + 16] = tag
            self.buf[so + PAYLOAD_OFF:    so + PAYLOAD_OFF + PAYLOAD_SIZE] = ct
        else:
            struct.pack_into("<B", self.buf, so + SLOT_ENC_OFF, 0)
            # keep these random if random-fill is desired (avoids obvious patterns)
            self.buf[so + SLOT_SALT_OFF:  so + SLOT_SALT_OFF + 16] = os.urandom(16)
            self.buf[so + SLOT_NONCE_OFF: so + SLOT_NONCE_OFF + 12] = os.urandom(12)
            self.buf[so + SLOT_TAG_OFF:   so + SLOT_TAG_OFF + 16] = os.urandom(16)
            self.buf[so + PAYLOAD_OFF:    so + PAYLOAD_OFF + PAYLOAD_SIZE] = plain_payload

        mode = "encrypted" if self.encrypt_var.get() else "plaintext"
        self.status.config(text=f"Slot {slot:02d} written successfully ({mode}).")

    # ----- Records operations -----
    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for i, r in enumerate(self.records):
            self.listbox.insert(tk.END, f"{i:02d}  {r.key}  [{TYPE_NAMES.get(r.rtype,'?')}]")

    def _clear_editor(self):
        self.key_entry.delete(0, tk.END)
        self.val_text.delete("1.0", tk.END)
        self.type_var.set("utf8")

    def on_select(self):
        if not self.listbox.curselection():
            return
        idx = self.listbox.curselection()[0]
        r = self.records[idx]
        self.key_entry.delete(0, tk.END)
        self.key_entry.insert(0, r.key)
        self.type_var.set(TYPE_NAMES[r.rtype])
        self.val_text.delete("1.0", tk.END)
        self.val_text.insert("1.0", r.value)

    def add_record(self):
        existing = {r.key for r in self.records}
        base = "key"
        k = base
        n = 1
        while k in existing:
            n += 1
            k = f"{base}{n}"
        self.records.append(Record(T_UTF8, k, ""))
        self._refresh_list()

    def delete_record(self):
        if not self.listbox.curselection():
            return
        idx = self.listbox.curselection()[0]
        del self.records[idx]
        self._refresh_list()
        self._clear_editor()

    def apply_record(self):
        if not self.listbox.curselection():
            return
        idx = self.listbox.curselection()[0]

        key = self.key_entry.get().strip()
        if not key:
            messagebox.showerror("Invalid key", "Key cannot be empty.")
            return

        for j, rr in enumerate(self.records):
            if j != idx and rr.key == key:
                messagebox.showerror("Duplicate key", f"Duplicate key: '{key}'.")
                return

        tname = self.type_var.get()
        if tname not in NAME_TO_TYPE:
            messagebox.showerror("Invalid type", "Invalid record type.")
            return
        rtype = NAME_TO_TYPE[tname]
        val = self.val_text.get("1.0", "end").strip()

        try:
            _ = encode_value(rtype, val)
        except Exception as e:
            messagebox.showerror("Invalid value", str(e))
            return

        self.records[idx] = Record(rtype, key, val)
        self._refresh_list()
        self.status.config(text="Record updated in memory. Click Write slot to persist (and encrypt if enabled).")


if __name__ == "__main__":
    Editor().mainloop()
