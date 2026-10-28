#!/usr/bin/env python3
"""
msg2eml.py - High-fidelity bulk converter: Outlook .msg  ->  RFC 5322 .eml

Fidelity rules
--------------
* The original Internet header block (PR_TRANSPORT_MESSAGE_HEADERS) is copied
  byte-for-byte: same order, same folding, same spacing, duplicates kept.
* Content-Type / Content-Transfer-Encoding are kept verbatim whenever the
  reconstructed body can honestly be described by them (the original MIME
  boundary is even reused).  If one of them must change (e.g. "7bit" declared
  but the body contains non-ASCII), the original line is preserved as
  "X-MSG2EML-Original-<Name>:" so no header is ever dropped.
* Body: the real HTML is used (PR_HTML, or HTML de-encapsulated from the
  compressed RTF body); plain text is PR_BODY; the original MIME structure
  (single part vs. alternative vs. related vs. mixed) is followed.
* Attachments, inline (cid:) images and embedded .msg attachments
  (converted recursively to message/rfc822) are all included.
* S/MIME signed / encrypted messages are rebuilt from the stored MIME blob.
* Messages without transport headers (drafts, sent items) get headers built
  from the MAPI properties (From, To, Cc, Bcc, Subject, Date, Message-ID...).
* Optional --sidecar writes <name>.mapi.json with EVERY MAPI property of the
  .msg (Outlook-only data such as categories, flags, named properties), which
  an .eml file has no place for.

Usage
-----
    pip install olefile
    python msg2eml.py  INPUT_FOLDER  OUTPUT_FOLDER  [--sidecar] [--overwrite] [--jobs N]

The folder tree is mirrored, file times are copied, and a
conversion_report.csv is written to OUTPUT_FOLDER.
"""

import argparse
import base64
import csv
import datetime as dt
import email.quoprimime
import email.utils
import json
import os
import re
import struct
import sys
import traceback
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from email.header import Header

try:
    import olefile
except ImportError:
    sys.exit("Missing dependency: run   pip install olefile")

CRLF = b"\r\n"

# --------------------------------------------------------------------------
# Codepages
# --------------------------------------------------------------------------
_CP_SPECIAL = {
    65001: "utf-8", 65000: "utf-7", 1200: "utf-16-le", 1201: "utf-16-be",
    20127: "ascii", 28591: "iso-8859-1", 28592: "iso-8859-2",
    28593: "iso-8859-3", 28594: "iso-8859-4", 28595: "iso-8859-5",
    28596: "iso-8859-6", 28597: "iso-8859-7", 28598: "iso-8859-8",
    28599: "iso-8859-9", 28603: "iso-8859-13", 28605: "iso-8859-15",
    50220: "iso-2022-jp", 50221: "iso-2022-jp", 50222: "iso-2022-jp",
    51932: "euc-jp", 51949: "euc-kr", 52936: "hz", 54936: "gb18030",
    20866: "koi8-r", 21866: "koi8-u", 10000: "mac-roman", 932: "shift_jis",
    936: "gbk", 949: "ks_c_5601-1987", 950: "big5",
}
_RTF_CHARSET_CP = {
    77: 10000, 128: 932, 129: 949, 130: 1361, 134: 936, 136: 950, 161: 1253,
    162: 1254, 163: 1258, 177: 1255, 178: 1256, 186: 1257, 204: 1251,
    222: 874, 238: 1250, 255: 437,
}


def cp_to_charset(cp):
    if cp in _CP_SPECIAL:
        return _CP_SPECIAL[cp]
    if 1250 <= cp <= 1258:
        return "windows-%d" % cp
    return "cp%d" % cp


def fix_surrogates(text):
    """Join UTF-16 surrogate pairs (e.g. emoji written as two \\uN codes in RTF)
    into real characters; replace any unpaired half with U+FFFD."""
    if not text or not re.search("[\ud800-\udfff]", text):
        return text
    return text.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


def codec_ok(name):
    import codecs
    try:
        codecs.lookup(name)
        return True
    except LookupError:
        return False


def safe_codec(name, default="cp1252"):
    if name and codec_ok(name):
        return name
    return default


# --------------------------------------------------------------------------
# Compressed RTF (MS-OXRTFCP) decompressor - no external dependency
# --------------------------------------------------------------------------
_RTF_PREBUF = (b"{\\rtf1\\ansi\\mac\\deff0\\deftab720{\\fonttbl;}{\\f0\\fnil \\froman "
               b"\\fswiss \\fmodern \\fscript \\fdecor MS Sans SerifSymbolArialTimes"
               b" New RomanCourier{\\colortbl\\red0\\green0\\blue0\r\n\\par "
               b"\\pard\\plain\\f0\\fs20\\b\\i\\u\\tab\\tx")


def decompress_rtf(data):
    if len(data) < 16:
        return b""
    comp_size, raw_size, magic, _crc = struct.unpack_from("<IIII", data, 0)
    if magic == 0x414C454D:                      # "MELA" -> stored uncompressed
        return data[16:16 + raw_size]
    if magic != 0x75465A4C:                      # "LZFu"
        raise ValueError("unknown compressed RTF signature")
    dic = bytearray(4096)
    dic[:len(_RTF_PREBUF)] = _RTF_PREBUF
    wpos = len(_RTF_PREBUF)
    out = bytearray()
    src = data[16:16 + comp_size - 12]
    i, n = 0, len(src)
    while i < n:
        ctrl = src[i]
        i += 1
        for bit in range(8):
            if i >= n:
                break
            if ctrl & (1 << bit):
                if i + 1 >= n:
                    i = n
                    break
                word = (src[i] << 8) | src[i + 1]
                i += 2
                off, length = word >> 4, (word & 0xF) + 2
                if off == wpos:
                    return bytes(out)
                for k in range(length):
                    c = dic[(off + k) & 0xFFF]
                    out.append(c)
                    dic[wpos] = c
                    wpos = (wpos + 1) & 0xFFF
            else:
                c = src[i]
                i += 1
                out.append(c)
                dic[wpos] = c
                wpos = (wpos + 1) & 0xFFF
    return bytes(out)


# --------------------------------------------------------------------------
# RTF -> HTML de-encapsulation (MS-OXRTFEX)
# --------------------------------------------------------------------------
_SKIP_DESTS = {
    "fonttbl", "colortbl", "stylesheet", "info", "pict", "object", "fldinst",
    "listtable", "listoverridetable", "rsidtbl", "generator", "xmlnstbl",
    "themedata", "colorschememapping", "latentstyles", "datastore", "header",
    "footer", "headerl", "headerr", "footerl", "footerr", "pntext", "pntxta",
    "pntxtb", "filetbl", "revtbl", "author", "operator", "title", "subject",
    "keywords", "comment", "doccomm", "company", "bkmkstart", "bkmkend",
}
_RTF_TOKEN = re.compile(
    rb"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\([^a-zA-Z])|([{}])|([\r\n]+)|([^\\{}\r\n]+)")


def rtf_kind(rtf):
    head = rtf[:1024]
    if b"\\fromhtml" in head:
        return "html"
    if b"\\fromtext" in head:
        return "text"
    return "rtf"


def rtf_to_html(rtf):
    """Return the HTML encapsulated in an RTF body (\\fromhtml1)."""
    m = re.search(rb"\\ansicpg(\d+)", rtf[:2048])
    ansicp = int(m.group(1)) if m else 1252
    fonts = {}                  # font number -> codepage
    out = []
    pending = bytearray()
    pending_cp = [ansicp]

    def flush():
        if pending:
            enc = safe_codec(cp_to_charset(pending_cp[0]))
            out.append(pending.decode(enc, errors="replace"))
            pending.clear()

    # state: [dest, suppress, uc, font, first_token_of_group, star]
    st = {"dest": "normal", "sup": False, "uc": 1, "font": None,
          "first": False, "star": False, "param": None}
    stack = []
    skip_chars = 0
    skip_htmltag = None
    in_fonttbl_font = [None]

    def cur_cp():
        f = st["font"]
        if f is not None and f in fonts:
            return fonts[f]
        return ansicp

    def emitting():
        if st["dest"] in ("htmltag", "mhtmltag"):
            return True
        return st["dest"] == "normal" and not st["sup"]

    def emit_text(s):
        flush()
        out.append(s)

    for mt in _RTF_TOKEN.finditer(rtf):
        word, param, hexb, sym, brace, nl, text = mt.groups()
        if brace:
            if brace == b"{":
                stack.append(dict(st))
                st["first"] = True
                st["star"] = False
            else:
                was_dest = st["dest"]
                if stack:
                    st = stack.pop()
                if was_dest == "fonttbl" and st["dest"] != "fonttbl":
                    pass
            continue
        first = st["first"]
        st["first"] = False
        if nl:
            continue
        if word is not None:
            w = word.decode("ascii")
            p = int(param) if param is not None else None
            if first or st["star"]:
                if w in ("htmltag", "mhtmltag"):
                    if w == "htmltag" and skip_htmltag is not None and p == skip_htmltag:
                        st["dest"] = "skip"
                        skip_htmltag = None
                    else:
                        st["dest"] = w
                        if w == "mhtmltag":
                            skip_htmltag = p
                    st["star"] = False
                    continue
                if w == "fonttbl":
                    st["dest"] = "fonttbl"
                    st["star"] = False
                    continue
                if st["star"] or w in _SKIP_DESTS:
                    if st["dest"] != "fonttbl":
                        st["dest"] = "skip"
                    st["star"] = False
                    continue
            if st["dest"] == "fonttbl":
                if w == "f":
                    in_fonttbl_font[0] = p
                elif w == "fcharset" and in_fonttbl_font[0] is not None:
                    if p in _RTF_CHARSET_CP:
                        fonts[in_fonttbl_font[0]] = _RTF_CHARSET_CP[p]
                    elif p == 2:
                        fonts[in_fonttbl_font[0]] = 1252
                continue
            if w == "htmlrtf":
                st["sup"] = (p != 0)
                continue
            if w == "f":
                st["font"] = p
                continue
            if w == "uc":
                st["uc"] = p if p is not None else 1
                continue
            if st["dest"] == "skip":
                continue
            if w == "u" and p is not None:
                if emitting():
                    emit_text(chr(p + 65536 if p < 0 else p))
                skip_chars = st["uc"]
                continue
            if emitting():
                if w in ("par", "line"):
                    emit_text("\r\n")
                elif w == "tab":
                    emit_text("\t")
                elif w == "emdash":
                    emit_text("\u2014")
                elif w == "endash":
                    emit_text("\u2013")
                elif w == "lquote":
                    emit_text("\u2018")
                elif w == "rquote":
                    emit_text("\u2019")
                elif w == "ldblquote":
                    emit_text("\u201c")
                elif w == "rdblquote":
                    emit_text("\u201d")
                elif w == "bullet":
                    emit_text("\u2022")
            continue
        if sym is not None:
            if sym == b"*":
                st["star"] = True
                continue
            if st["dest"] in ("skip", "fonttbl"):
                continue
            if skip_chars:
                skip_chars -= 1
                continue
            if not emitting():
                continue
            if sym in (b"\\", b"{", b"}"):
                emit_text(sym.decode())
            elif sym == b"~":
                emit_text("\u00a0")
            elif sym == b"_":
                emit_text("\u2011")
            elif sym in (b"\r", b"\n"):
                emit_text("\r\n")
            continue
        if hexb is not None:
            if st["dest"] in ("skip", "fonttbl"):
                continue
            if skip_chars:
                skip_chars -= 1
                continue
            if emitting():
                cp = cur_cp()
                if pending and pending_cp[0] != cp:
                    flush()
                pending_cp[0] = cp
                pending.append(int(hexb, 16))
            continue
        if text is not None:
            if st["dest"] in ("skip", "fonttbl"):
                continue
            t = text
            if skip_chars:
                cut = min(skip_chars, len(t))
                skip_chars -= cut
                t = t[cut:]
            if t and emitting():
                cp = cur_cp()
                if pending and pending_cp[0] != cp:
                    flush()
                pending_cp[0] = cp
                pending.extend(t)
    flush()
    return fix_surrogates("".join(out))


# --------------------------------------------------------------------------
# MSG (CFB) reading
# --------------------------------------------------------------------------
class MsgStorage:
    """One MAPI object: the message, an attachment, a recipient or an embedded message."""

    def __init__(self, ole, prefix, kind, codepage=None):
        self.ole = ole
        self.prefix = list(prefix)
        self.kind = kind            # 'root' | 'embedded' | 'attach' | 'recip'
        self.streams = {}           # (propid, proptype) -> path
        self.fixed = {}             # propid -> (type, raw 8 bytes)
        plen = len(self.prefix)
        for entry in ole.listdir(streams=True, storages=False):
            if entry[:plen] != self.prefix or len(entry) != plen + 1:
                continue
            name = entry[-1]
            if name.startswith("__substg1.0_") and len(name) == 20:
                try:
                    pid = int(name[12:16], 16)
                    ptype = int(name[16:20], 16)
                except ValueError:
                    continue
                self.streams[(pid, ptype)] = entry
        self._read_fixed()
        cp = self.int_prop(0x3FFD) or self.int_prop(0x3FDE) or codepage
        self.codepage = cp or 1252

    def _read_fixed(self):
        path = self.prefix + ["__properties_version1.0"]
        if not self.ole.exists("/".join(path)):
            return
        data = self.ole.openstream(path).read()
        hdr = {"root": 32, "embedded": 24}.get(self.kind, 8)
        for off in range(hdr, len(data) - 15, 16):
            tag, _flags = struct.unpack_from("<II", data, off)
            ptype, pid = tag & 0xFFFF, tag >> 16
            self.fixed[pid] = (ptype, data[off + 8:off + 16])

    def raw(self, pid, ptype):
        path = self.streams.get((pid, ptype))
        if path is None:
            return None
        return self.ole.openstream(path).read()

    def string(self, pid):
        b = self.raw(pid, 0x001F)
        if b is not None:
            return fix_surrogates(b.decode("utf-16-le", errors="replace").rstrip("\x00"))
        b = self.raw(pid, 0x001E)
        if b is not None:
            return b.decode(safe_codec(cp_to_charset(self.codepage)),
                            errors="replace").rstrip("\x00")
        return None

    def binary(self, pid):
        return self.raw(pid, 0x0102)

    def int_prop(self, pid):
        v = self.fixed.get(pid)
        if not v:
            return None
        ptype, raw = v
        if ptype == 0x0003:
            return struct.unpack("<i", raw[:4])[0]
        if ptype == 0x0002:
            return struct.unpack("<h", raw[:2])[0]
        if ptype == 0x000B:
            return raw[0]
        if ptype == 0x0014:
            return struct.unpack("<q", raw)[0]
        return None

    def time_prop(self, pid):
        v = self.fixed.get(pid)
        if not v or v[0] != 0x0040:
            return None
        ft = struct.unpack("<Q", v[1])[0]
        if ft == 0:
            return None
        try:
            return dt.datetime(1601, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(microseconds=ft // 10)
        except OverflowError:
            return None

    def substorages(self, marker):
        plen = len(self.prefix)
        names = set()
        for entry in self.ole.listdir(streams=True, storages=True):
            if entry[:plen] == self.prefix and len(entry) > plen and entry[plen].startswith(marker):
                names.add(entry[plen])
        return sorted(names)


# --------------------------------------------------------------------------
# MIME building helpers
# --------------------------------------------------------------------------
def new_boundary():
    return "----=_NextPart_msg2eml_" + uuid.uuid4().hex


def norm_crlf(text):
    text = fix_surrogates(text)
    return re.sub(r"\r\n|\r|\n", "\r\n", text)


def encode_body(data, cte):
    cte = (cte or "7bit").lower()
    if cte == "base64":
        return base64.encodebytes(data).replace(b"\n", b"\r\n")
    if cte == "quoted-printable":
        s = data.decode("latin-1")
        s = re.sub(r"\r\n|\r|\n", "\n", s)
        enc = email.quoprimime.body_encode(s, maxlinelen=76, eol="\r\n")
        return enc.encode("ascii")
    return data


def cte_fits(data, cte):
    cte = (cte or "7bit").lower()
    if cte in ("base64", "quoted-printable", "binary"):
        return True
    long_line = any(len(l) > 998 for l in data.split(b"\r\n"))
    if cte == "7bit":
        return not long_line and all(b < 128 for b in data) and b"\x00" not in data
    if cte == "8bit":
        return not long_line and b"\x00" not in data
    return False


def pick_cte(data, is_text):
    if not is_text:
        return "base64"
    if cte_fits(data, "7bit"):
        return "7bit"
    return "quoted-printable"


def param_header(name, value, params):
    """Build e.g. Content-Type: a/b; name="x" with RFC 2231/2047 handling."""
    parts = [value]
    for k, v in params:
        if v is None:
            continue
        try:
            v.encode("ascii")
            parts.append('%s="%s"' % (k, v.replace("\\", "\\\\").replace('"', '\\"')))
        except UnicodeEncodeError:
            if k in ("filename", "name"):
                parts.append("%s*=%s" % (k, email.utils.encode_rfc2231(v, "utf-8")))
                parts.append('%s="%s"' % (k, Header(v, "utf-8").encode()))
            else:
                parts.append("%s*=%s" % (k, email.utils.encode_rfc2231(v, "utf-8")))
    return "%s: %s" % (name, ";\r\n\t".join(parts))


class Part:
    def __init__(self, ctype, headers=None, body=b"", children=None,
                 boundary=None, ctype_params=None, cte=None):
        self.ctype = ctype.lower()
        self.headers = headers or []    # extra header lines (str), no CT/CTE
        self.body = body
        self.children = children
        self.boundary = boundary
        self.ctype_params = ctype_params or []
        self.cte = cte

    def ct_line(self):
        params = list(self.ctype_params)
        if self.children is not None:
            params.append(("boundary", self.boundary))
        return param_header("Content-Type", self.ctype, params)

    def payload(self):
        if self.children is None:
            return encode_body(self.body, self.cte)
        out = []
        for c in self.children:
            out.append(b"--" + self.boundary.encode() + CRLF + c.render())
        if self.children:
            res = CRLF.join(out) + CRLF + b"--" + self.boundary.encode() + b"--" + CRLF
        else:
            res = b"--" + self.boundary.encode() + b"--" + CRLF
        return res

    def render(self):
        lines = [self.ct_line()]
        if self.children is None and self.cte:
            lines.append("Content-Transfer-Encoding: " + self.cte)
        lines += self.headers
        head = fix_surrogates("\r\n".join(lines)).encode("utf-8")
        body = self.payload()
        if self.children is not None:
            body = CRLF + body          # blank preamble line after headers
        return head + CRLF + CRLF + body if self.children is None else head + CRLF + body


# --------------------------------------------------------------------------
# Header block handling
# --------------------------------------------------------------------------
def split_header_fields(text):
    """Split a raw header block into fields, keeping folding exactly."""
    lines = re.split(r"\r\n|\n|\r", text)
    while lines and lines[-1].strip() == "":
        lines.pop()
    fields, cur, dropped = [], None, []
    for ln in lines:
        if ln[:1] in (" ", "\t") and cur is not None:
            cur.append(ln)
            continue
        if re.match(r"^[!-9;-~]+:", ln):
            cur = [ln]
            fields.append(cur)
        elif ln.strip() == "":
            # stray empty line inside the header block: keep as nothing
            cur = None
        else:
            # e.g. "Microsoft Mail Internet Headers Version 2.0" pseudo line
            if cur is not None:
                cur.append(" " + ln)        # malformed continuation, keep
            else:
                dropped.append(ln)
    return [(f[0].split(":", 1)[0], f) for f in fields], dropped


def field_value(lines):
    v = "\r\n".join(lines).split(":", 1)[1]
    return re.sub(r"\r\n[ \t]", " ", v).strip()


def parse_ct(value):
    """-> (media type lower, {param: value})"""
    if not value:
        return None, {}
    parts = re.split(r';(?=(?:[^"]*"[^"]*")*[^"]*$)', value)
    mtype = parts[0].strip().lower()
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
                v = v[1:-1]
            params[k.strip().lower()] = v
    return mtype, params


def fmt_addr(name, addr):
    if not addr and not name:
        return None
    if name and addr and name.strip("'\"") == addr:
        name = None
    if name:
        try:
            name.encode("ascii")
            return email.utils.formataddr((name, addr or ""))
        except UnicodeEncodeError:
            return "%s <%s>" % (Header(name, "utf-8").encode(), addr or "")
    return addr


def enc_hdr(value):
    try:
        value.encode("ascii")
        return value
    except UnicodeEncodeError:
        return Header(value, "utf-8").encode()


# --------------------------------------------------------------------------
# Conversion
# --------------------------------------------------------------------------
class Converter:
    def __init__(self, ole, prefix=(), kind="root", codepage=None, warnings=None):
        self.ole = ole
        self.msg = MsgStorage(ole, prefix, kind, codepage)
        self.warn = warnings if warnings is not None else []

    # ---- smtp address helpers ----
    def _smtp(self, store, smtp_pid, email_pid, type_pid):
        smtp = store.string(smtp_pid)
        if smtp:
            return smtp
        addr = store.string(email_pid)
        atype = (store.string(type_pid) or "").upper()
        if addr and (atype in ("SMTP", "") or "@" in addr):
            return addr
        return addr

    def recipients(self):
        res = {1: [], 2: [], 3: []}
        for sub in self.msg.substorages("__recip_version1.0_"):
            r = MsgStorage(self.ole, self.msg.prefix + [sub], "recip", self.msg.codepage)
            rtype = r.int_prop(0x0C15) or 1
            name = r.string(0x3001)
            addr = r.string(0x39FE) or self._smtp(r, 0x39FE, 0x3003, 0x3002)
            a = fmt_addr(name, addr)
            if a:
                res.setdefault(rtype & 0xF, []).append(a)
        return res

    def build_headers_from_mapi(self):
        m = self.msg
        h = []
        from_name = m.string(0x0042) or m.string(0x0C1A)
        from_addr = (m.string(0x5D02) or self._smtp(m, 0x5D02, 0x0065, 0x0064)
                     or m.string(0x5D01) or self._smtp(m, 0x5D01, 0x0C1F, 0x0C1E))
        f = fmt_addr(from_name, from_addr)
        if f:
            h.append("From: " + f)
        snd_name = m.string(0x0C1A)
        snd_addr = m.string(0x5D01) or self._smtp(m, 0x5D01, 0x0C1F, 0x0C1E)
        if snd_addr and from_addr and snd_addr.lower() != from_addr.lower():
            h.append("Sender: " + fmt_addr(snd_name, snd_addr))
        rec = self.recipients()
        for label, key in (("To", 1), ("Cc", 2), ("Bcc", 3)):
            if rec.get(key):
                h.append("%s: %s" % (label, ",\r\n\t".join(rec[key])))
        subj = m.string(0x0037)
        if subj is not None:
            h.append("Subject: " + enc_hdr(subj))
        when = m.time_prop(0x0039) or m.time_prop(0x0E06) or m.time_prop(0x3007)
        if when:
            h.append("Date: " + email.utils.format_datetime(when))
        for pid, name in ((0x1035, "Message-ID"), (0x1042, "In-Reply-To"), (0x1039, "References")):
            v = m.string(pid)
            if v:
                h.append("%s: %s" % (name, v))
        imp = m.int_prop(0x0017)
        if imp == 2:
            h.append("Importance: high")
        elif imp == 0:
            h.append("Importance: low")
        h.append("MIME-Version: 1.0")
        return [(x.split(":", 1)[0], [l for l in x.split("\r\n")]) for x in h]

    # ---- bodies ----
    def get_html(self):
        """-> (html_bytes or None, charset or None, html_str or None)"""
        m = self.msg
        b = m.binary(0x1013)
        if b:
            b = b.rstrip(b"\x00")
            cs = None
            cpid = m.int_prop(0x3FDE)
            if cpid:
                cs = cp_to_charset(cpid)
            if not cs or not codec_ok(cs):
                mm = re.search(rb"charset\s*=\s*[\"']?([A-Za-z0-9_\-:.]+)", b[:4096], re.I)
                cs = mm.group(1).decode() if mm else "utf-8"
            return b, cs, None
        s = m.string(0x1013)
        if s:
            return None, None, s
        rtf = self.get_rtf()
        if rtf and rtf_kind(rtf) == "html":
            try:
                return None, None, rtf_to_html(rtf)
            except Exception as e:
                self.warn.append("RTF->HTML failed: %s" % e)
        return None, None, None

    def get_rtf(self):
        if not hasattr(self, "_rtf"):
            self._rtf = None
            b = self.msg.binary(0x1009)
            if b:
                try:
                    self._rtf = decompress_rtf(b)
                except Exception as e:
                    self.warn.append("compressed RTF unreadable: %s" % e)
        return self._rtf

    # ---- attachments ----
    def attachments(self):
        res = []
        for sub in self.msg.substorages("__attach_version1.0_"):
            a = MsgStorage(self.ole, self.msg.prefix + [sub], "attach", self.msg.codepage)
            method = a.int_prop(0x3705) or 1
            info = {
                "filename": a.string(0x3707) or a.string(0x3704) or a.string(0x3001),
                "mime": a.string(0x370E),
                "cid": a.string(0x3712),
                "location": a.string(0x3713),
                "hidden": bool(a.int_prop(0x7FFE)),
                "flags": a.int_prop(0x3714) or 0,
                "method": method,
                "data": None,
                "embedded": None,
                "store": a,
            }
            if method == 5:     # embedded message
                emb_prefix = a.prefix + ["__substg1.0_3701000D"]
                if self.ole.exists("/".join(emb_prefix)):
                    try:
                        sub_conv = Converter(self.ole, emb_prefix, "embedded",
                                             self.msg.codepage, self.warn)
                        info["embedded"] = sub_conv.convert()
                    except Exception as e:
                        self.warn.append("embedded message failed: %s" % e)
            elif method == 6:   # OLE object
                d = a.binary(0x3701)
                if d is None:
                    self.warn.append("OLE-object attachment '%s' stored as storage; "
                                     "saved its raw streams only" % info["filename"])
                info["data"] = d or b""
            elif method in (2, 3, 4, 7):  # by reference
                path = a.string(0x370D) or a.string(0x3708)
                self.warn.append("attachment by reference (not embedded in .msg): %s" % path)
                info["data"] = None
                info["reference"] = path
            else:
                info["data"] = a.binary(0x3701) or b""
            res.append(info)
        return res

    def attachment_part(self, att, inline):
        if att.get("embedded") is not None:
            eml = att["embedded"]
            hdrs = []
            disp = "inline" if inline else "attachment"
            if att["filename"]:
                hdrs.append(param_header("Content-Disposition", disp, [("filename", att["filename"])]))
            else:
                hdrs.append("Content-Disposition: " + disp)
            p = Part("message/rfc822", headers=hdrs, body=eml,
                     cte="8bit" if cte_fits(eml, "8bit") else "binary")
            if att["filename"]:
                p.ctype_params = [("name", att["filename"])]
            return p
        if att.get("reference") is not None and att["data"] is None:
            return Part("message/external-body",
                        body=("Content-Type: application/octet-stream\r\n\r\n").encode(),
                        ctype_params=[("access-type", "local-file"),
                                      ("name", att["reference"] or "")],
                        cte="7bit")
        data = att["data"] or b""
        mime = (att["mime"] or "").strip().lower() or guess_mime(att["filename"])
        params = [("name", att["filename"])] if att["filename"] else []
        hdrs = []
        disp = "inline" if inline else "attachment"
        dparams = [("filename", att["filename"])] if att["filename"] else []
        hdrs.append(param_header("Content-Disposition", disp, dparams))
        if att["cid"]:
            cid = att["cid"].strip()
            if not cid.startswith("<"):
                cid = "<%s>" % cid
            hdrs.append("Content-ID: " + cid)
        if att["location"]:
            hdrs.append("Content-Location: " + enc_hdr(att["location"]))
        return Part(mime, headers=hdrs, body=data, ctype_params=params, cte="base64")

    # ---- main ----
    def convert(self):
        m = self.msg
        msg_class = (m.string(0x001A) or "").upper()
        raw_headers = m.string(0x007D)
        dropped = []
        if raw_headers and raw_headers.strip():
            fields, dropped = split_header_fields(raw_headers)
            from_transport = True
        else:
            fields = self.build_headers_from_mapi()
            from_transport = False
        if dropped:
            self.warn.append("non-header line(s) in transport headers omitted: %r" % dropped)

        def find(name):
            for i, (n, _) in enumerate(fields):
                if n.lower() == name:
                    return i
            return None

        i_ct, i_cte = find("content-type"), find("content-transfer-encoding")
        orig_ct_val = field_value(fields[i_ct][1]) if i_ct is not None else None
        orig_cte_val = field_value(fields[i_cte][1]).lower() if i_cte is not None else None
        orig_type, orig_params = parse_ct(orig_ct_val)

        atts = self.attachments()

        # ----- S/MIME: the stored blob IS the original body -----
        if msg_class.startswith("IPM.NOTE.SMIME") and atts and atts[0]["data"]:
            body_part = self._smime_part(msg_class, atts[0], orig_type, orig_params)
        else:
            body_part = self._build_body(atts, orig_type, orig_params, from_transport)

        return self._assemble(fields, i_ct, i_cte, orig_type, orig_params,
                              orig_cte_val, body_part)

    def _smime_part(self, msg_class, att, orig_type, orig_params):
        data = att["data"]
        if "MULTIPARTSIGNED" in msg_class:
            # Blob may start with its own MIME headers
            head_end = data.find(b"\r\n\r\n")
            if head_end > 0 and re.match(rb"(?i)^(content-|mime-version)", data):
                head = data[:head_end].decode("utf-8", "replace")
                flds, _ = split_header_fields(head)
                ctv = None
                for n, l in flds:
                    if n.lower() == "content-type":
                        ctv = field_value(l)
                t, p = parse_ct(ctv)
                part = Part(t or "multipart/signed", body=data[head_end + 4:], cte=None)
                part.raw_ct = ctv
                part.opaque = True
                return part
            t, p = (orig_type, orig_params) if orig_type == "multipart/signed" else ("multipart/signed", {})
            part = Part(t, body=data, cte=None)
            part.raw_ct = orig_ct_param_string(t, p) if p else None
            part.opaque = True
            return part
        # opaque signed / encrypted
        p = Part("application/pkcs7-mime", body=data, cte="base64",
                 ctype_params=[("smime-type", "enveloped-data" if "SMIME" in msg_class and "SIGNED" not in msg_class else "signed-data"),
                               ("name", att["filename"] or "smime.p7m")],
                 headers=[param_header("Content-Disposition", "attachment",
                                       [("filename", att["filename"] or "smime.p7m")])])
        return p

    def _build_body(self, atts, orig_type, orig_params, from_transport):
        m = self.msg
        html_bytes, html_cs, html_str = self.get_html()
        has_html = html_bytes is not None or html_str is not None
        text = m.string(0x1000)
        rtf = self.get_rtf()
        native_rtf = rtf if (rtf and rtf_kind(rtf) == "rtf") else None

        # which body parts to emit, guided by the original structure
        want_text, want_html = True, has_html
        if from_transport and orig_type:
            if orig_type == "text/html" and has_html:
                want_text = False
            elif orig_type == "text/plain":
                want_html = False
        if text is None and has_html:
            want_text = False
        if not has_html:
            want_html = False

        # html cid references -> inline vs attachment
        html_for_scan = html_str if html_str is not None else (
            html_bytes.decode("latin-1") if html_bytes else "")
        referenced = set(x.lower() for x in re.findall(r"cid:([^\"'\s>)]+)", html_for_scan, re.I))
        inline, regular = [], []
        for a in atts:
            cid = (a["cid"] or "").strip("<> ").lower()
            if want_html and cid and (cid in referenced or a["flags"] & 0x4):
                inline.append(a)
            else:
                regular.append(a)

        alts = []
        if want_text:
            alts.append(self._text_part("text/plain", text or "", orig_type, orig_params))
        if want_html:
            if html_bytes is not None:
                hb = norm_crlf(html_bytes.decode("latin-1")).encode("latin-1")
                alts.append(Part("text/html", body=hb, ctype_params=[("charset", html_cs)],
                                 cte=pick_cte(hb, True)))
            else:
                alts.append(self._text_part("text/html", html_str, orig_type, orig_params))
        if native_rtf is not None and not want_html:
            alts.append(Part("text/rtf", body=native_rtf, cte=pick_cte(native_rtf, True)))
        if not alts:
            alts.append(self._text_part("text/plain", "", orig_type, orig_params))

        node = alts[0] if len(alts) == 1 else Part("multipart/alternative", children=alts,
                                                   boundary=new_boundary())
        if inline:
            node = Part("multipart/related",
                        children=[node] + [self.attachment_part(a, True) for a in inline],
                        boundary=new_boundary(), ctype_params=[("type", "text/html" if node.ctype == "text/html" else node.ctype)])
        if regular:
            node = Part("multipart/mixed",
                        children=[node] + [self.attachment_part(a, False) for a in regular],
                        boundary=new_boundary())
        return node

    def _text_part(self, ctype, text, orig_type, orig_params):
        text = norm_crlf(text)
        charset = "utf-8"
        if orig_type == ctype and orig_params.get("charset"):
            cs = orig_params["charset"]
            if codec_ok(cs):
                try:
                    data = text.encode(cs)
                    return Part(ctype, body=data, ctype_params=[("charset", cs)],
                                cte=pick_cte(data, True))
                except UnicodeEncodeError:
                    pass
        try:
            data = text.encode("ascii")
            charset = "us-ascii"
        except UnicodeEncodeError:
            data = text.encode("utf-8")
        return Part(ctype, body=data, ctype_params=[("charset", charset)], cte=pick_cte(data, True))

    def _assemble(self, fields, i_ct, i_cte, orig_type, orig_params, orig_cte, part):
        """Merge original header fields with the rebuilt body."""
        keep_ct = False
        keep_cte = False
        opaque = getattr(part, "opaque", False)

        if orig_type and orig_type == part.ctype:
            if part.children is not None:
                b = orig_params.get("boundary")
                if b and b.encode() not in b"".join(c.render() for c in part.children):
                    part.boundary = b
                    keep_ct = True
            elif opaque:
                keep_ct = True
            else:
                mine = dict((k.lower(), v) for k, v in part.ctype_params)
                cs_o = (orig_params.get("charset") or "us-ascii").lower()
                cs_m = (mine.get("charset") or "us-ascii").lower()
                if cs_o == cs_m or (cs_o in ("us-ascii", "ascii") and all(b < 128 for b in part.body)):
                    keep_ct = True
        elif opaque and getattr(part, "raw_ct", None) and orig_type == part.ctype:
            keep_ct = True

        if part.children is None and not opaque:
            if keep_ct and cte_fits(part.body, orig_cte or "7bit"):
                part.cte = orig_cte or "7bit"
                keep_cte = True
            elif keep_ct:
                part.cte = part.cte or pick_cte(part.body, part.ctype.startswith("text/"))
        else:
            keep_cte = orig_cte in (None, "7bit", "8bit", "binary")

        out_fields = []
        mime_seen = False
        for idx, (name, lines) in enumerate(fields):
            ln = name.lower()
            if ln == "mime-version":
                mime_seen = True
            if idx == i_ct and not keep_ct:
                out_fields.append(["X-MSG2EML-Original-" + lines[0]] + lines[1:])
                continue
            if idx == i_cte and not keep_cte:
                out_fields.append(["X-MSG2EML-Original-" + lines[0]] + lines[1:])
                continue
            if idx == i_ct and keep_ct and part.children is not None:
                # make sure the kept boundary is the one we used
                pass
            out_fields.append(lines)

        new_lines = []
        if not mime_seen:
            new_lines.append("MIME-Version: 1.0")
        if not keep_ct:
            if opaque and getattr(part, "raw_ct", None):
                new_lines.append("Content-Type: " + part.raw_ct)
            else:
                new_lines.append(part.ct_line())
        if not keep_cte:
            if part.children is None and part.cte:
                new_lines.append("Content-Transfer-Encoding: " + part.cte)
            elif part.children is None and opaque:
                new_lines.append("Content-Transfer-Encoding: 7bit")
        elif i_cte is None and part.children is None and part.cte and part.cte != "7bit":
            new_lines.append("Content-Transfer-Encoding: " + part.cte)

        # insert new MIME fields where the originals were (or at the end)
        if new_lines:
            pos = None
            for cand in (i_ct, i_cte):
                if cand is not None:
                    pos = cand + 1 if pos is None else min(pos, cand + 1)
            if pos is None:
                out_fields += [[l] for l in new_lines]
            else:
                out_fields[pos:pos] = [[l] for l in new_lines]

        head = fix_surrogates("\r\n".join("\r\n".join(f) for f in out_fields)).encode("utf-8")
        if opaque:
            body = part.body if part.cte in (None, "7bit", "8bit", "binary") else encode_body(part.body, part.cte)
        else:
            body = part.payload()
            if part.children is not None:
                body = CRLF + body
        return head + CRLF + CRLF + body


def orig_ct_param_string(t, p):
    return t + "".join('; %s="%s"' % (k, v) for k, v in p.items())


def guess_mime(filename):
    import mimetypes
    if filename:
        t, _ = mimetypes.guess_type(filename)
        if t:
            return t
    return "application/octet-stream"


# --------------------------------------------------------------------------
# Sidecar: dump every MAPI property
# --------------------------------------------------------------------------
_PROPSETS = {1: "PS_MAPI", 2: "PS_PUBLIC_STRINGS"}


def named_props(ole):
    res = {}
    try:
        guids = ole.openstream("__nameid_version1.0/__substg1.0_00020102").read()
        entries = ole.openstream("__nameid_version1.0/__substg1.0_00030102").read()
        strings = ole.openstream("__nameid_version1.0/__substg1.0_00040102").read()
    except Exception:
        return res
    for off in range(0, len(entries) - 7, 8):
        nid, idxkind = struct.unpack_from("<II", entries, off)
        kind = idxkind & 1
        gidx = (idxkind >> 1) & 0x7FFF
        pidx = idxkind >> 16
        if gidx in _PROPSETS:
            gs = _PROPSETS[gidx]
        else:
            g = guids[(gidx - 3) * 16:(gidx - 2) * 16]
            gs = str(uuid.UUID(bytes_le=g)) if len(g) == 16 else "?"
        if kind == 1:
            ln = struct.unpack_from("<I", strings, nid)[0]
            name = strings[nid + 4:nid + 4 + ln].decode("utf-16-le", "replace")
        else:
            name = "0x%04X" % nid
        res[0x8000 + pidx] = "%s:%s" % (gs, name)
    return res


def dump_storage(store, names):
    props = {}
    for (pid, ptype), path in sorted(store.streams.items()):
        key = "0x%04X%04X" % (pid, ptype)
        data = store.ole.openstream(path).read()
        if ptype == 0x001F:
            val = data.decode("utf-16-le", "replace").rstrip("\x00")
        elif ptype == 0x001E:
            val = data.decode(safe_codec(cp_to_charset(store.codepage)), "replace").rstrip("\x00")
        else:
            val = {"base64": base64.b64encode(data).decode()}
        props[key] = {"name": names.get(pid), "value": val}
    for pid, (ptype, raw) in sorted(store.fixed.items()):
        key = "0x%04X%04X" % (pid, ptype)
        if key in props:
            continue
        if ptype == 0x0040:
            t = store.time_prop(pid)
            val = t.isoformat() if t else None
        elif ptype in (0x0002, 0x0003, 0x000B, 0x0014):
            val = store.int_prop(pid)
        elif ptype == 0x0005:
            val = struct.unpack("<d", raw)[0]
        elif ptype == 0x0004:
            val = struct.unpack("<f", raw[:4])[0]
        else:
            continue            # variable-size property already listed from its stream
        props[key] = {"name": names.get(pid), "value": val}
    return props


def dump_mapi(ole):
    names = named_props(ole)

    def walk(prefix, kind):
        s = MsgStorage(ole, prefix, kind)
        node = {"properties": dump_storage(s, names), "recipients": [], "attachments": []}
        for sub in s.substorages("__recip_version1.0_"):
            node["recipients"].append(dump_storage(MsgStorage(ole, prefix + [sub], "recip"), names))
        for sub in s.substorages("__attach_version1.0_"):
            a = MsgStorage(ole, prefix + [sub], "attach")
            entry = {"properties": dump_storage(a, names)}
            emb = prefix + [sub, "__substg1.0_3701000D"]
            if ole.exists("/".join(emb)):
                entry["embedded_message"] = walk(emb, "embedded")
            node["attachments"].append(entry)
        return node
    return walk([], "root")


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------
def convert_file(src, dst, sidecar=False):
    warnings = []
    with olefile.OleFileIO(src) as ole:
        eml = Converter(ole, warnings=warnings).convert()
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        tmp = dst + ".part"
        with open(tmp, "wb") as fh:
            fh.write(eml)
        os.replace(tmp, dst)
        if sidecar:
            with open(os.path.splitext(dst)[0] + ".mapi.json", "w", encoding="utf-8") as fh:
                json.dump(dump_mapi(ole), fh, ensure_ascii=False, indent=1)
    st = os.stat(src)
    os.utime(dst, (st.st_atime, st.st_mtime))
    return warnings


def _job(args):
    src, dst, sidecar = args
    try:
        return src, dst, "ok", convert_file(src, dst, sidecar)
    except Exception as e:
        tb = traceback.extract_tb(e.__traceback__)
        where = "%s line %d" % (tb[-1].name, tb[-1].lineno) if tb else "?"
        return src, dst, "error", ["%s: %s (in %s)" % (type(e).__name__, e, where)]


def main():
    ap = argparse.ArgumentParser(description="Convert Outlook .msg files to .eml with maximum fidelity.")
    ap.add_argument("input", help="folder with .msg files (searched recursively) or a single .msg")
    ap.add_argument("output", help="output folder")
    ap.add_argument("--sidecar", action="store_true",
                    help="also write <name>.mapi.json with every MAPI property")
    ap.add_argument("--overwrite", action="store_true", help="replace existing .eml files")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1, help="parallel workers")
    a = ap.parse_args()

    jobs = []
    if os.path.isfile(a.input):
        base = os.path.dirname(os.path.abspath(a.input))
        files = [os.path.abspath(a.input)]
    else:
        base = os.path.abspath(a.input)
        files = [os.path.join(r, f) for r, _, fs in os.walk(base) for f in fs
                 if f.lower().endswith(".msg")]
    files.sort()
    skipped = 0
    for src in files:
        rel = os.path.relpath(src, base)
        dst = os.path.join(a.output, os.path.splitext(rel)[0] + ".eml")
        if os.path.exists(dst) and not a.overwrite:
            skipped += 1
            continue
        jobs.append((src, dst, a.sidecar))

    print("Found %d .msg files, %d to convert, %d already done." % (len(files), len(jobs), skipped))
    os.makedirs(a.output, exist_ok=True)
    results = []
    if a.jobs > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=a.jobs) as ex:
            futs = [ex.submit(_job, j) for j in jobs]
            for n, f in enumerate(as_completed(futs), 1):
                results.append(f.result())
                if n % 50 == 0 or n == len(jobs):
                    print("  %d/%d" % (n, len(jobs)))
    else:
        for n, j in enumerate(jobs, 1):
            results.append(_job(j))
            if n % 50 == 0 or n == len(jobs):
                print("  %d/%d" % (n, len(jobs)))

    report = os.path.join(a.output, "conversion_report.csv")
    with open(report, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["source", "output", "status", "notes"])
        for src, dst, status, notes in sorted(results):
            w.writerow([src, dst, status, " | ".join(n.strip() for n in notes[:1] if status == "error")
                        or " | ".join(notes)])
    errors = [r for r in results if r[2] == "error"]
    warned = [r for r in results if r[2] == "ok" and r[3]]
    print("Done: %d converted, %d with warnings, %d failed. Report: %s"
          % (len(results) - len(errors), len(warned), len(errors), report))
    for src, _, _, notes in errors[:10]:
        print("  FAILED %s: %s" % (src, notes[0]))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
