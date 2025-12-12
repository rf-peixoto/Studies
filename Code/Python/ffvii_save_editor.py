import os
import struct
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import scrolledtext

# =========================
# FF7 PC/Steam save geometry
# =========================
FILE_HEADER_SIZE = 0x09
SLOT_SIZE = 0x10F4  # 4340 bytes
SLOT_COUNT = 15

# Slot-relative offsets
SLOT_CHECKSUM_OFF = 0x0000  # 4 bytes; low 16 bits are used
CHAR_TABLE_OFF = 0x0054
CHAR_REC_SIZE = 132

# Character order as stored in save
CHAR_NAMES = [
    "Cloud", "Barret", "Tifa", "Aerith", "Red XIII",
    "Yuffie", "Cait Sith", "Vincent", "Cid"
]

# Character record offsets (relative to record start)
CR_LEVEL = 0x01
CR_STR   = 0x02
CR_VIT   = 0x03
CR_MAG   = 0x04
CR_SPR   = 0x05
CR_DEX   = 0x06
CR_LUCK  = 0x07

CR_CUR_HP  = 0x2C  # u16
CR_BASE_HP = 0x2E  # u16
CR_CUR_MP  = 0x30  # u16
CR_BASE_MP = 0x32  # u16

# After materia/equipment area; still within record
CR_MAX_HP  = 0x38  # u16
CR_MAX_MP  = 0x3A  # u16

# Hex view format
BYTES_PER_LINE = 16

# Expected file size for saveXX.ff7 (PC/Steam)
EXPECTED_FILE_SIZE = FILE_HEADER_SIZE + SLOT_COUNT * SLOT_SIZE


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def crc16_ccitt_ff7(data: bytes) -> int:
    """
    CRC-16/CCITT over 4336 bytes starting at slot+0x04 (skip checksum dword),
    init=0xFFFF, poly=0x1021, xorout=0xFFFF.
    """
    r = 0xFFFF
    for b in data:
        r ^= (b << 8)
        for _ in range(8):
            if r & 0x8000:
                r = ((r << 1) ^ 0x1021) & 0xFFFF
            else:
                r = (r << 1) & 0xFFFF
    return (r ^ 0xFFFF) & 0xFFFF


def hexdump_lines(data: bytes, base_offset: int = 0):
    """
    Yields lines:
    '00000000  00 11 22 ... FF  |ASCII.............|'
    """
    for i in range(0, len(data), BYTES_PER_LINE):
        chunk = data[i:i + BYTES_PER_LINE]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        hex_part = hex_part.ljust(BYTES_PER_LINE * 3 - 1)
        ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        yield f"{base_offset + i:08X}  {hex_part}  |{ascii_part:<16}|"


def byte_range_to_line_range(start: int, end_inclusive: int, base: int):
    """
    Maps absolute byte offsets [start, end] to 1-based hexdump line numbers.
    base = first byte offset represented at line 1.
    """
    if end_inclusive < start:
        return (1, 1)
    ls = (start - base) // BYTES_PER_LINE + 1
    le = (end_inclusive - base) // BYTES_PER_LINE + 1
    return (int(ls), int(le))


class FF7SaveEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FF7 (Steam/PC) Save Editor — Stats + Hex Visualizer")
        self.geometry("980x680")

        self.file_path = None
        self.buf = None  # bytearray

        self.slot_var = tk.IntVar(value=1)
        self.char_var = tk.StringVar(value=CHAR_NAMES[0])
        self.hex_mode = tk.StringVar(value="slot")  # "slot" or "file"

        self._build_ui()
        self._set_editor_enabled(False)

    # ------------------------
    # UI
    # ------------------------
    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Button(top, text="Open saveXX.ff7…", command=self.open_file).pack(side="left")
        ttk.Button(top, text="Save as…", command=self.save_as).pack(side="left", padx=8)
        ttk.Button(top, text="Overwrite", command=self.overwrite).pack(side="left")

        self.path_label = ttk.Label(top, text="No file loaded")
        self.path_label.pack(side="left", padx=12)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # ---- Editor tab ----
        self.editor_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.editor_tab, text="Editor")

        self._build_editor_tab(self.editor_tab)

        # ---- Hex tab ----
        self.hex_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.hex_tab, text="Hex Visualizer")

        self._build_hex_tab(self.hex_tab)

        # Status bar
        self.status = ttk.Label(self, text="")
        self.status.pack(fill="x", padx=10, pady=(0, 10))

    def _build_editor_tab(self, parent):
        # Selection bar
        sel = ttk.Frame(parent, padding=10)
        sel.pack(fill="x")

        ttk.Label(sel, text="Slot:").pack(side="left")
        self.slot_box = ttk.Spinbox(
            sel, from_=1, to=SLOT_COUNT, width=4,
            textvariable=self.slot_var, command=self.on_selection_changed
        )
        self.slot_box.pack(side="left", padx=6)

        ttk.Label(sel, text="Character:").pack(side="left", padx=(16, 0))
        self.char_box = ttk.Combobox(sel, values=CHAR_NAMES, state="readonly", textvariable=self.char_var, width=12)
        self.char_box.pack(side="left", padx=6)
        self.char_box.bind("<<ComboboxSelected>>", lambda _e: self.on_selection_changed())

        # Form
        form = ttk.Frame(parent, padding=10)
        form.pack(fill="both", expand=True)

        self.entries = {}

        def add_row(r, label, key):
            ttk.Label(form, text=label).grid(row=r, column=0, sticky="e", padx=6, pady=4)
            e = ttk.Entry(form, width=12)
            e.grid(row=r, column=1, sticky="w", padx=6, pady=4)
            self.entries[key] = e

        add_row(0, "Level (0–99)", "level")
        add_row(1, "Strength (0–255)", "str")
        add_row(2, "Vitality (0–255)", "vit")
        add_row(3, "Magic (0–255)", "mag")
        add_row(4, "Spirit (0–255)", "spr")
        add_row(5, "Dexterity (0–255)", "dex")
        add_row(6, "Luck (0–255)", "luck")

        ttk.Separator(form, orient="horizontal").grid(row=7, column=0, columnspan=4, sticky="ew", pady=10)

        add_row(8, "Current HP (0–9999)", "cur_hp")
        add_row(9, "Base HP (0–9999)", "base_hp")
        add_row(10, "Max HP (0–9999)", "max_hp")

        ttk.Separator(form, orient="horizontal").grid(row=11, column=0, columnspan=4, sticky="ew", pady=10)

        add_row(12, "Current MP (0–9999)", "cur_mp")
        add_row(13, "Base MP (0–9999)", "base_mp")
        add_row(14, "Max MP (0–9999)", "max_mp")

        # Buttons
        btns = ttk.Frame(parent, padding=10)
        btns.pack(fill="x")

        ttk.Button(btns, text="Reload from save", command=self.refresh_fields).pack(side="left")
        ttk.Button(btns, text="Apply changes (update checksum)", command=self.apply_changes).pack(side="left", padx=10)

    def _build_hex_tab(self, parent):
        controls = ttk.Frame(parent, padding=10)
        controls.pack(fill="x")

        ttk.Radiobutton(controls, text="Current slot", variable=self.hex_mode, value="slot", command=self.refresh_hex).pack(side="left")
        ttk.Radiobutton(controls, text="Whole file", variable=self.hex_mode, value="file", command=self.refresh_hex).pack(side="left", padx=10)

        ttk.Button(controls, text="Refresh", command=self.refresh_hex).pack(side="left", padx=10)

        self.hex_text = scrolledtext.ScrolledText(
            parent, height=30, wrap="none", font=("Courier New", 10)
        )
        self.hex_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Tag colors (you can change, but these are restrained)
        self.hex_text.tag_configure("tag_header", background="#e9e9e9")
        self.hex_text.tag_configure("tag_slot", background="#f5f5f5")
        self.hex_text.tag_configure("tag_slot_current", background="#dbeaff")
        self.hex_text.tag_configure("tag_checksum", background="#ffe0c7")
        self.hex_text.tag_configure("tag_char_table", background="#ddffdd")
        self.hex_text.tag_configure("tag_char_current", background="#fff2aa")

        self.hex_text.config(state="disabled")

    def _set_editor_enabled(self, enabled: bool):
        state_entry = "normal" if enabled else "disabled"
        for e in getattr(self, "entries", {}).values():
            e.config(state=state_entry)
        if hasattr(self, "slot_box"):
            self.slot_box.config(state=("readonly" if enabled else "disabled"))
        if hasattr(self, "char_box"):
            self.char_box.config(state=("readonly" if enabled else "disabled"))

    # ------------------------
    # File/offset helpers
    # ------------------------
    def slot_offset(self, slot_index_1based: int) -> int:
        return FILE_HEADER_SIZE + (slot_index_1based - 1) * SLOT_SIZE

    def char_offset(self, slot_off: int, char_name: str) -> int:
        ci = CHAR_NAMES.index(char_name)
        return slot_off + CHAR_TABLE_OFF + ci * CHAR_REC_SIZE

    # ------------------------
    # File operations
    # ------------------------
    def open_file(self):
        path = filedialog.askopenfilename(
            title="Open FF7 saveXX.ff7",
            filetypes=[("FF7 Save (*.ff7)", "*.ff7"), ("All files", "*.*")]
        )
        if not path:
            return

        data = open(path, "rb").read()

        if len(data) != EXPECTED_FILE_SIZE:
            messagebox.showerror(
                "Unexpected file size",
                f"This editor expects PC/Steam saveXX.ff7 files of size {EXPECTED_FILE_SIZE} bytes.\n"
                f"Selected file size: {len(data)} bytes.\n\n"
                "If you are using a different release or format, this tool will not be safe to use."
            )
            return

        self.file_path = path
        self.buf = bytearray(data)
        self.path_label.config(text=os.path.basename(path))
        self._set_editor_enabled(True)

        self.refresh_fields()
        self.refresh_hex()

        self.status.config(text="Loaded. Use 'Save as…' first; overwrite only after verifying the save loads in-game.")

    def save_as(self):
        if not self.buf:
            return
        out = filedialog.asksaveasfilename(
            title="Save edited file as",
            defaultextension=".ff7",
            filetypes=[("FF7 Save (*.ff7)", "*.ff7"), ("All files", "*.*")]
        )
        if not out:
            return
        open(out, "wb").write(self.buf)
        messagebox.showinfo("Saved", f"Saved:\n{out}")

    def overwrite(self):
        if not self.buf or not self.file_path:
            return
        if not messagebox.askyesno("Overwrite", "Overwrite the currently loaded file on disk?"):
            return
        open(self.file_path, "wb").write(self.buf)
        messagebox.showinfo("Overwritten", "File overwritten successfully.")

    # ------------------------
    # Editor logic
    # ------------------------
    def on_selection_changed(self):
        if not self.buf:
            return
        self.refresh_fields()
        self.refresh_hex()

    def _set_entry(self, key: str, value: int):
        e = self.entries[key]
        e.delete(0, tk.END)
        e.insert(0, str(value))

    def _get_int(self, key: str, default=0) -> int:
        try:
            return int(self.entries[key].get().strip(), 10)
        except Exception:
            return default

    def refresh_fields(self):
        if not self.buf:
            return

        slot = clamp(self.slot_var.get(), 1, SLOT_COUNT)
        self.slot_var.set(slot)

        slot_off = self.slot_offset(slot)
        char_off = self.char_offset(slot_off, self.char_var.get())

        def read_u8(off): return self.buf[off]
        def read_u16(off): return struct.unpack_from("<H", self.buf, off)[0]

        self._set_entry("level", read_u8(char_off + CR_LEVEL))
        self._set_entry("str",   read_u8(char_off + CR_STR))
        self._set_entry("vit",   read_u8(char_off + CR_VIT))
        self._set_entry("mag",   read_u8(char_off + CR_MAG))
        self._set_entry("spr",   read_u8(char_off + CR_SPR))
        self._set_entry("dex",   read_u8(char_off + CR_DEX))
        self._set_entry("luck",  read_u8(char_off + CR_LUCK))

        self._set_entry("cur_hp",  read_u16(char_off + CR_CUR_HP))
        self._set_entry("base_hp", read_u16(char_off + CR_BASE_HP))
        self._set_entry("max_hp",  read_u16(char_off + CR_MAX_HP))

        self._set_entry("cur_mp",  read_u16(char_off + CR_CUR_MP))
        self._set_entry("base_mp", read_u16(char_off + CR_BASE_MP))
        self._set_entry("max_mp",  read_u16(char_off + CR_MAX_MP))

        self.status.config(text=f"Viewing slot {slot:02d}, character {self.char_var.get()}.")

    def apply_changes(self):
        if not self.buf:
            return

        slot = clamp(self.slot_var.get(), 1, SLOT_COUNT)
        slot_off = self.slot_offset(slot)
        char_off = self.char_offset(slot_off, self.char_var.get())

        # Read, clamp
        level = clamp(self._get_int("level"), 0, 99)
        st = clamp(self._get_int("str"), 0, 255)
        vi = clamp(self._get_int("vit"), 0, 255)
        ma = clamp(self._get_int("mag"), 0, 255)
        sp = clamp(self._get_int("spr"), 0, 255)
        dx = clamp(self._get_int("dex"), 0, 255)
        lu = clamp(self._get_int("luck"), 0, 255)

        cur_hp  = clamp(self._get_int("cur_hp"),  0, 9999)
        base_hp = clamp(self._get_int("base_hp"), 0, 9999)
        max_hp  = clamp(self._get_int("max_hp"),  0, 9999)

        cur_mp  = clamp(self._get_int("cur_mp"),  0, 9999)
        base_mp = clamp(self._get_int("base_mp"), 0, 9999)
        max_mp  = clamp(self._get_int("max_mp"),  0, 9999)

        # Write bytes
        self.buf[char_off + CR_LEVEL] = level
        self.buf[char_off + CR_STR] = st
        self.buf[char_off + CR_VIT] = vi
        self.buf[char_off + CR_MAG] = ma
        self.buf[char_off + CR_SPR] = sp
        self.buf[char_off + CR_DEX] = dx
        self.buf[char_off + CR_LUCK] = lu

        struct.pack_into("<H", self.buf, char_off + CR_CUR_HP,  cur_hp)
        struct.pack_into("<H", self.buf, char_off + CR_BASE_HP, base_hp)
        struct.pack_into("<H", self.buf, char_off + CR_MAX_HP,  max_hp)

        struct.pack_into("<H", self.buf, char_off + CR_CUR_MP,  cur_mp)
        struct.pack_into("<H", self.buf, char_off + CR_BASE_MP, base_mp)
        struct.pack_into("<H", self.buf, char_off + CR_MAX_MP,  max_mp)

        # Update slot checksum: CRC over 4336 bytes starting at slot+0x04
        crc_region = bytes(self.buf[slot_off + 0x04: slot_off + 0x04 + 4336])
        crc = crc16_ccitt_ff7(crc_region)

        # Store as 32-bit LE; low word matters
        struct.pack_into("<I", self.buf, slot_off + SLOT_CHECKSUM_OFF, crc)

        self.status.config(text=f"Applied changes. Slot {slot:02d} checksum updated (CRC16=0x{crc:04X}).")
        self.refresh_fields()
        self.refresh_hex()

    # ------------------------
    # Hex visualizer
    # ------------------------
    def refresh_hex(self):
        if not self.buf:
            self.hex_text.config(state="normal")
            self.hex_text.delete("1.0", tk.END)
            self.hex_text.config(state="disabled")
            return

        mode = self.hex_mode.get()
        slot = clamp(self.slot_var.get(), 1, SLOT_COUNT)
        slot_off = self.slot_offset(slot)

        if mode == "file":
            view_bytes = bytes(self.buf)
            base = 0
        else:
            view_bytes = bytes(self.buf[slot_off:slot_off + SLOT_SIZE])
            base = slot_off

        self.hex_text.config(state="normal")
        self.hex_text.delete("1.0", tk.END)

        for line in hexdump_lines(view_bytes, base_offset=base):
            self.hex_text.insert(tk.END, line + "\n")

        # Apply highlighting
        if mode == "file":
            self._highlight_file_sectors()
        else:
            self._highlight_slot_sectors(slot_off)

        self.hex_text.config(state="disabled")

    def _tag_lines(self, line_start: int, line_end: int, tag: str):
        if line_start < 1:
            line_start = 1
        if line_end < line_start:
            line_end = line_start
        self.hex_text.tag_add(tag, f"{line_start}.0", f"{line_end}.end")

    def _highlight_file_sectors(self):
        # File header
        ls, le = byte_range_to_line_range(0, FILE_HEADER_SIZE - 1, base=0)
        self._tag_lines(ls, le, "tag_header")

        # Slots
        cur_slot = clamp(self.slot_var.get(), 1, SLOT_COUNT)
        for i in range(1, SLOT_COUNT + 1):
            off = self.slot_offset(i)
            start = off
            end = off + SLOT_SIZE - 1
            ls, le = byte_range_to_line_range(start, end, base=0)
            self._tag_lines(ls, le, "tag_slot_current" if i == cur_slot else "tag_slot")

        # Current slot details
        slot_off = self.slot_offset(cur_slot)
        self._highlight_slot_details_absolute(slot_off_abs=slot_off, base=0)

    def _highlight_slot_sectors(self, slot_off_abs: int):
        # In slot-only mode, base == slot offset
        base = slot_off_abs

        # Entire view is current slot
        ls, le = byte_range_to_line_range(base, base + SLOT_SIZE - 1, base=base)
        self._tag_lines(ls, le, "tag_slot_current")

        self._highlight_slot_details_absolute(slot_off_abs=slot_off_abs, base=base)

    def _highlight_slot_details_absolute(self, slot_off_abs: int, base: int):
        # checksum dword
        cs_start = slot_off_abs + 0x0000
        cs_end = cs_start + 3
        ls, le = byte_range_to_line_range(cs_start, cs_end, base=base)
        self._tag_lines(ls, le, "tag_checksum")

        # character table region
        ct_start = slot_off_abs + CHAR_TABLE_OFF
        ct_end = ct_start + len(CHAR_NAMES) * CHAR_REC_SIZE - 1
        ls, le = byte_range_to_line_range(ct_start, ct_end, base=base)
        self._tag_lines(ls, le, "tag_char_table")

        # selected character record region
        char_name = self.char_var.get()
        ci = CHAR_NAMES.index(char_name)
        cr_start = ct_start + ci * CHAR_REC_SIZE
        cr_end = cr_start + CHAR_REC_SIZE - 1
        ls, le = byte_range_to_line_range(cr_start, cr_end, base=base)
        self._tag_lines(ls, le, "tag_char_current")


if __name__ == "__main__":
    app = FF7SaveEditor()
    app.mainloop()
