#!/usr/bin/env python3

# Hello, user. This code was made by Claude. Yes, Claude made a copy of https://github.com/rvrsh3ll/NETREAPER without telling me.
# The little bastard even cloned the banner. Please, go check the original NETREAPER made by rvrsh3ll


# ============================================================
#   ███╗   ██╗███████╗████████╗██████╗ ███████╗ █████╗ ██████╗ ███████╗██████╗
#   ████╗  ██║██╔════╝╚══██╔══╝██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔════╝██╔══██╗
#   ██╔██╗ ██║█████╗     ██║   ██████╔╝█████╗  ███████║██████╔╝█████╗  ██████╔╝
#   ██║╚██╗██║██╔══╝     ██║   ██╔══██╗██╔══╝  ██╔══██║██╔═══╝ ██╔══╝  ██╔══██╗
#   ██║ ╚████║███████╗   ██║   ██║  ██║███████╗██║  ██║██║     ███████╗██║  ██║
#   ╚═╝  ╚═══╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝
#
#   [ NETWORK QUICKHACK PROTOCOL v2.0.77 ] — ARASAKA COUNTERMEASURES BYPASSED
#   Authored for: Night City Grid Recon  |  Threat Level: CLASSIFIED
# ============================================================

import os, sys, socket, subprocess, threading, time, re, json, ipaddress, struct, argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# ─── Require Python 3.6+ ───────────────────────────────────
if sys.version_info < (3, 6):
    sys.exit("[-] Requires Python 3.6+")

# ─── ANSI Color Palette (Cyberpunk 2077) ───────────────────
R = '\033[0m'          # Reset
BOLD = '\033[1m'
DIM  = '\033[2m'
BLINK = '\033[5m'

# Neon palette
NC = '\033[38;5;51m'   # Neon Cyan      (primary)
NY = '\033[38;5;226m'  # Neon Yellow    (accent)
NP = '\033[38;5;201m'  # Neon Pink/Magenta
NG = '\033[38;5;118m'  # Neon Green     (safe/online)
NO = '\033[38;5;208m'  # Neon Orange    (warning)
NR = '\033[38;5;196m'  # Neon Red       (danger/rogue)
NB = '\033[38;5;27m'   # Neon Blue
GR = '\033[38;5;240m'  # Gray           (dimmed info)
W  = '\033[97m'        # White          (labels)

# Background accents
BG_DARK  = '\033[48;5;232m'
BG_PANEL = '\033[48;5;234m'

# ─── OUI Vendor Database (Top vendors, offline) ────────────
OUI_DB = {
    # ── Apple ──────────────────────────────────────────────────────────
    "00:03:93": "Apple", "00:0A:27": "Apple", "00:0A:95": "Apple",
    "00:11:24": "Apple", "00:14:51": "Apple", "00:16:CB": "Apple",
    "00:17:F2": "Apple", "00:19:E3": "Apple", "00:1B:63": "Apple",
    "00:1C:B3": "Apple", "00:1D:4F": "Apple", "00:1E:52": "Apple",
    "00:21:E9": "Apple", "00:23:12": "Apple", "00:25:00": "Apple",
    "00:26:B0": "Apple", "00:26:BB": "Apple", "04:54:53": "Apple",
    "08:70:45": "Apple", "0C:3E:9F": "Apple", "0C:77:1A": "Apple",
    "10:40:F3": "Apple", "14:10:9F": "Apple", "14:5A:05": "Apple",
    "18:20:32": "Apple", "18:65:90": "Apple", "18:9E:FC": "Apple",
    "18:AF:61": "Apple", "1C:1A:C0": "Apple", "20:78:F0": "Apple",
    "20:A2:E4": "Apple", "20:C9:D0": "Apple", "24:A0:74": "Apple",
    "28:0B:5C": "Apple", "28:CF:DA": "Apple", "28:EF:01": "Apple",
    "2C:BE:08": "Apple", "2C:F0:A2": "Apple", "34:08:BC": "Apple",
    "34:15:9E": "Apple", "34:36:3B": "Apple", "38:0F:4A": "Apple",
    "38:71:DE": "Apple", "38:C9:86": "Apple", "3C:07:54": "Apple",
    "3C:22:FB": "Apple", "40:6C:8F": "Apple", "40:CB:C0": "Apple",
    "44:D8:84": "Apple", "48:74:6E": "Apple", "4C:32:75": "Apple",
    "4C:57:CA": "Apple", "4C:74:BF": "Apple", "50:EA:D6": "Apple",
    "54:26:96": "Apple", "54:AE:27": "Apple", "58:1F:AA": "Apple",
    "5C:59:48": "Apple", "5C:F7:E6": "Apple", "60:03:08": "Apple",
    "60:69:44": "Apple", "60:C5:47": "Apple", "64:20:0C": "Apple",
    "64:A3:CB": "Apple", "68:09:27": "Apple", "68:5B:35": "Apple",
    "6C:4D:73": "Apple", "6C:72:E7": "Apple", "6C:8D:C1": "Apple",
    "6C:94:F8": "Apple", "70:11:24": "Apple", "70:3E:AC": "Apple",
    "70:56:81": "Apple", "70:73:CB": "Apple", "70:EC:E4": "Apple",
    "74:1B:B2": "Apple", "74:E2:F5": "Apple", "78:31:C1": "Apple",
    "7C:6D:62": "Apple", "7C:C3:A1": "Apple", "80:49:71": "Apple",
    "80:92:9F": "Apple", "84:38:35": "Apple", "84:85:06": "Apple",
    "84:FC:FE": "Apple", "88:19:08": "Apple", "88:63:DF": "Apple",
    "8C:2D:AA": "Apple", "90:27:E4": "Apple", "90:72:40": "Apple",
    "94:BF:2D": "Apple", "94:E9:6A": "Apple", "98:01:A7": "Apple",
    "9C:20:7B": "Apple", "9C:F3:87": "Apple", "A0:99:9B": "Apple",
    "A4:5E:60": "Apple", "A8:20:66": "Apple", "A8:86:DD": "Apple",
    "AC:29:3A": "Apple", "AC:61:EA": "Apple", "AC:BC:32": "Apple",
    "B0:65:BD": "Apple", "B0:9F:BA": "Apple", "B4:F0:AB": "Apple",
    "B8:09:8A": "Apple", "B8:17:C2": "Apple", "B8:78:2E": "Apple",
    "B8:C7:5D": "Apple", "BC:67:78": "Apple", "BC:6E:E2": "Apple",
    "C8:BC:C8": "Apple", "CC:08:E0": "Apple", "D0:23:DB": "Apple",
    "D0:E1:40": "Apple", "D4:61:9D": "Apple", "D8:00:4D": "Apple",
    "D8:30:62": "Apple", "DC:0C:5C": "Apple", "DC:37:14": "Apple",
    "E0:5F:45": "Apple", "E0:66:78": "Apple", "E0:AC:CB": "Apple",
    "E4:25:E7": "Apple", "E4:CE:8F": "Apple", "E8:06:88": "Apple",
    "E8:80:2E": "Apple", "EC:85:2F": "Apple", "F0:1D:BC": "Apple",
    "F0:5C:19": "Apple", "F0:CB:8B": "Apple", "F4:1B:A1": "Apple",
    "F4:31:C3": "Apple", "F4:F1:5A": "Apple", "F8:27:93": "Apple",
    "FC:25:3F": "Apple",
    # ── Samsung ────────────────────────────────────────────────────────
    "00:07:AB": "Samsung", "00:12:47": "Samsung", "00:15:99": "Samsung",
    "00:16:32": "Samsung", "00:17:C9": "Samsung", "00:1A:8A": "Samsung",
    "00:1D:25": "Samsung", "00:1E:7D": "Samsung", "00:21:D1": "Samsung",
    "00:23:39": "Samsung", "00:24:54": "Samsung", "00:26:37": "Samsung",
    "08:08:C2": "Samsung", "08:D4:2B": "Samsung", "10:1D:C0": "Samsung",
    "10:30:47": "Samsung", "10:D5:42": "Samsung", "14:32:D1": "Samsung",
    "14:49:E0": "Samsung", "18:3A:2D": "Samsung", "18:3F:47": "Samsung",
    "18:89:5B": "Samsung", "1C:5A:3E": "Samsung", "1C:62:B8": "Samsung",
    "1C:AF:F7": "Samsung", "20:13:E0": "Samsung", "20:55:31": "Samsung",
    "24:4B:03": "Samsung", "28:27:BF": "Samsung", "2C:AE:2B": "Samsung",
    "30:07:4D": "Samsung", "34:14:5F": "Samsung", "34:23:BA": "Samsung",
    "34:AA:8B": "Samsung", "38:01:97": "Samsung", "3C:5A:37": "Samsung",
    "3C:8B:FE": "Samsung", "40:0E:85": "Samsung", "44:4E:1A": "Samsung",
    "44:78:3E": "Samsung", "48:13:7E": "Samsung", "4C:3C:16": "Samsung",
    "50:01:BB": "Samsung", "50:32:75": "Samsung", "5C:3C:27": "Samsung",
    "5C:49:7D": "Samsung", "60:6B:BD": "Samsung", "64:B3:10": "Samsung",
    "68:27:37": "Samsung", "6C:2F:2C": "Samsung", "70:F9:27": "Samsung",
    "74:45:8A": "Samsung", "78:1F:DB": "Samsung", "78:52:1A": "Samsung",
    "7C:1C:4E": "Samsung", "84:25:DB": "Samsung", "84:55:A5": "Samsung",
    "88:32:9B": "Samsung", "88:9B:39": "Samsung", "8C:77:12": "Samsung",
    "90:18:7C": "Samsung", "90:F1:AA": "Samsung", "94:01:C2": "Samsung",
    "94:35:0A": "Samsung", "94:76:B7": "Samsung", "98:52:B1": "Samsung",
    "98:6C:F5": "Samsung", "9C:02:98": "Samsung", "A0:0B:BA": "Samsung",
    "A4:07:B6": "Samsung", "A8:F2:74": "Samsung", "AC:5A:14": "Samsung",
    "B0:47:BF": "Samsung", "B4:3A:28": "Samsung", "B4:EF:FA": "Samsung",
    "B8:5E:7B": "Samsung", "BC:20:A4": "Samsung", "BC:44:86": "Samsung",
    "C0:65:99": "Samsung", "C4:42:02": "Samsung", "C4:73:1E": "Samsung",
    "C8:19:F7": "Samsung", "C8:BE:19": "Samsung", "CC:07:AB": "Samsung",
    "D0:22:BE": "Samsung", "D4:88:90": "Samsung", "D8:57:EF": "Samsung",
    "DC:71:96": "Samsung", "E0:CB:1D": "Samsung", "E4:40:E2": "Samsung",
    "E4:92:FB": "Samsung", "E8:50:8B": "Samsung", "EC:1F:72": "Samsung",
    "EC:9B:F3": "Samsung", "F0:25:B7": "Samsung", "F4:42:8F": "Samsung",
    "F8:04:2E": "Samsung", "F8:77:B8": "Samsung", "FC:A1:3E": "Samsung",
    "FC:F1:36": "Samsung",
    # ── Google / Nest / Chromecast ─────────────────────────────────────
    "00:1A:11": "Google", "3C:5A:B4": "Google", "54:60:09": "Google",
    "54:F2:01": "Google", "48:D6:D5": "Google", "F4:F5:D8": "Google",
    "6C:AD:F8": "Google (Nest)", "80:B7:09": "Google (Nest)",
    "E4:F0:42": "Google (Nest)", "F0:EF:86": "Google (Nest)",
    "78:4F:43": "Google (Chromecast)", "88:4A:EA": "Google (Chromecast)",
    "A4:77:33": "Google (Chromecast)", "FC:AA:14": "Google (Home)",
    "94:EB:2C": "Google",
    # ── Amazon ─────────────────────────────────────────────────────────
    "00:FC:8B": "Amazon", "18:74:2E": "Amazon (Echo)",
    "34:D2:70": "Amazon", "44:65:0D": "Amazon (Fire TV)",
    "4C:EF:C0": "Amazon", "68:37:E9": "Amazon (Echo)",
    "74:C2:46": "Amazon", "84:D6:D0": "Amazon (Echo)",
    "A0:02:DC": "Amazon", "AC:63:BE": "Amazon (Echo)",
    "B4:7C:9C": "Amazon (Kindle)", "F0:27:2D": "Amazon (Echo)",
    "FC:65:DE": "Amazon",
    # ── Microsoft / Xbox ───────────────────────────────────────────────
    "00:15:5D": "Microsoft (Hyper-V)", "00:17:FA": "Microsoft",
    "00:50:F2": "Microsoft", "28:18:78": "Microsoft (Xbox)",
    "30:59:B7": "Microsoft", "48:50:73": "Microsoft",
    "60:45:BD": "Microsoft (Xbox)", "7C:1E:52": "Microsoft (Surface)",
    "C0:33:5E": "Microsoft (Xbox)", "DC:56:E7": "Microsoft (Surface)",
    "E8:D0:55": "Microsoft", "F4:6A:D6": "Microsoft (Xbox)",
    # ── Intel ──────────────────────────────────────────────────────────
    "00:02:B3": "Intel", "00:03:47": "Intel", "00:04:23": "Intel",
    "00:07:E9": "Intel", "00:0E:35": "Intel", "00:0E:D7": "Intel",
    "00:12:F0": "Intel", "00:13:02": "Intel", "00:13:20": "Intel",
    "00:15:00": "Intel", "00:16:76": "Intel", "00:18:DE": "Intel",
    "00:19:D1": "Intel", "00:1B:21": "Intel", "00:1C:BF": "Intel",
    "00:1D:E0": "Intel", "00:1E:64": "Intel", "00:1E:67": "Intel",
    "00:1F:3B": "Intel", "00:21:6A": "Intel", "00:21:6B": "Intel",
    "00:22:FA": "Intel", "00:23:14": "Intel", "00:24:D6": "Intel",
    "00:24:D7": "Intel", "10:02:B5": "Intel", "18:5E:0F": "Intel",
    "24:77:03": "Intel", "28:D2:44": "Intel", "40:8D:5C": "Intel",
    "44:03:A7": "Intel", "48:51:B7": "Intel", "4C:79:6E": "Intel",
    "54:35:30": "Intel", "54:E1:AD": "Intel", "5C:51:4F": "Intel",
    "60:57:18": "Intel", "64:D4:DA": "Intel", "68:5D:43": "Intel",
    "6C:88:14": "Intel", "70:1C:E7": "Intel", "78:92:9C": "Intel",
    "80:19:34": "Intel", "84:3A:4B": "Intel", "8C:8D:28": "Intel",
    "90:48:9A": "Intel", "90:E2:BA": "Intel", "94:65:9C": "Intel",
    "9C:DA:3E": "Intel", "A0:A8:CD": "Intel", "A4:34:D9": "Intel",
    "AC:7B:A1": "Intel", "AC:C1:EE": "Intel", "B4:96:91": "Intel",
    "B8:08:CF": "Intel", "C4:85:08": "Intel", "D0:50:99": "Intel",
    "E4:B3:18": "Intel", "F4:06:69": "Intel", "F8:63:3F": "Intel",
    # ── Cisco ──────────────────────────────────────────────────────────
    "00:00:0C": "Cisco", "00:01:42": "Cisco", "00:01:63": "Cisco",
    "00:01:96": "Cisco", "00:02:16": "Cisco", "00:02:FC": "Cisco",
    "00:03:31": "Cisco", "00:03:6B": "Cisco", "00:0B:46": "Cisco",
    "00:0D:BC": "Cisco", "00:0E:38": "Cisco", "00:0F:8F": "Cisco",
    "00:10:07": "Cisco", "00:10:F6": "Cisco", "00:11:20": "Cisco",
    "00:12:80": "Cisco", "00:13:19": "Cisco", "00:14:1B": "Cisco",
    "00:15:2B": "Cisco", "00:16:46": "Cisco", "00:17:0E": "Cisco",
    "00:18:18": "Cisco", "00:19:06": "Cisco", "00:1A:2F": "Cisco",
    "00:1B:53": "Cisco", "00:1C:57": "Cisco", "00:1D:70": "Cisco",
    "00:1E:13": "Cisco", "00:1E:7A": "Cisco", "00:1F:26": "Cisco",
    "00:22:55": "Cisco", "00:23:5E": "Cisco", "00:24:13": "Cisco",
    "00:25:45": "Cisco", "00:26:99": "Cisco", "00:27:0D": "Cisco",
    "00:30:19": "Cisco", "00:30:80": "Cisco", "00:40:96": "Cisco",
    "00:50:0F": "Cisco", "00:60:2F": "Cisco", "00:60:3E": "Cisco",
    "00:60:70": "Cisco", "00:90:21": "Cisco", "00:90:6D": "Cisco",
    "00:90:86": "Cisco", "58:BC:27": "Cisco (Meraki)",
    "88:15:44": "Cisco (Meraki)", "AC:17:C8": "Cisco (Meraki)",
    "E8:65:D4": "Cisco (Meraki)", "0C:75:BD": "Cisco (Meraki)",
    "4C:4E:35": "Cisco (Meraki)", "88:F0:31": "Cisco (Meraki)",
    # ── TP-Link ────────────────────────────────────────────────────────
    "00:23:CD": "TP-Link", "00:27:19": "TP-Link", "04:18:D6": "TP-Link",
    "08:95:2A": "TP-Link", "10:FE:ED": "TP-Link", "14:CC:20": "TP-Link",
    "18:A6:F7": "TP-Link", "1C:3B:F3": "TP-Link", "20:DC:E6": "TP-Link",
    "24:69:68": "TP-Link", "28:28:5D": "TP-Link", "2C:3B:7D": "TP-Link",
    "3C:46:D8": "TP-Link", "40:16:9F": "TP-Link", "44:AD:D9": "TP-Link",
    "48:8F:5A": "TP-Link", "4C:5E:0C": "TP-Link", "50:C7:BF": "TP-Link",
    "54:AF:97": "TP-Link", "54:C8:0F": "TP-Link", "60:A4:4C": "TP-Link",
    "60:E3:27": "TP-Link", "64:70:02": "TP-Link", "6C:4B:90": "TP-Link",
    "74:DA:38": "TP-Link", "78:A1:06": "TP-Link", "80:35:C1": "TP-Link",
    "84:16:F9": "TP-Link", "88:A2:5E": "TP-Link", "90:F6:52": "TP-Link",
    "94:0C:6D": "TP-Link", "98:DA:C4": "TP-Link", "9C:A6:15": "TP-Link",
    "A0:F3:C1": "TP-Link", "AC:84:C6": "TP-Link", "B0:4E:26": "TP-Link",
    "B0:95:8E": "TP-Link", "B4:B0:24": "TP-Link", "C0:4A:00": "TP-Link",
    "C4:6E:1F": "TP-Link", "C8:3A:35": "TP-Link", "CC:32:E5": "TP-Link",
    "D4:6E:0E": "TP-Link", "D8:07:B6": "TP-Link", "DC:FE:18": "TP-Link",
    "E0:28:6D": "TP-Link", "E4:F8:9C": "TP-Link", "E8:DE:27": "TP-Link",
    "EC:08:6B": "TP-Link", "F0:C8:50": "TP-Link", "F4:F2:6D": "TP-Link",
    "F8:1A:67": "TP-Link",
    # ── Netgear ────────────────────────────────────────────────────────
    "00:09:5B": "Netgear", "00:0F:B5": "Netgear", "00:14:6C": "Netgear",
    "00:18:4D": "Netgear", "00:1B:2F": "Netgear", "00:1E:2A": "Netgear",
    "00:1F:33": "Netgear", "00:22:3F": "Netgear", "00:24:B2": "Netgear",
    "00:26:F2": "Netgear", "20:E5:2A": "Netgear", "28:C6:8E": "Netgear",
    "2C:B0:5D": "Netgear", "30:46:9A": "Netgear", "44:94:FC": "Netgear",
    "4C:60:DE": "Netgear", "58:EF:68": "Netgear", "6C:B0:CE": "Netgear",
    "74:44:01": "Netgear", "7C:AF:F2": "Netgear", "80:CC:9C": "Netgear",
    "84:1B:5E": "Netgear", "9C:D3:6D": "Netgear", "A0:21:B7": "Netgear",
    "A0:40:A0": "Netgear", "B0:39:56": "Netgear", "C0:3F:0E": "Netgear",
    "C0:FF:D4": "Netgear", "CC:40:D0": "Netgear", "E0:46:9A": "Netgear",
    "E0:91:F5": "Netgear",
    # ── ASUS ───────────────────────────────────────────────────────────
    "00:0C:6E": "ASUS", "00:11:2F": "ASUS", "00:13:D4": "ASUS",
    "00:15:F2": "ASUS", "00:17:31": "ASUS", "00:18:F3": "ASUS",
    "00:1A:92": "ASUS", "00:1D:60": "ASUS", "00:1E:8C": "ASUS",
    "00:22:15": "ASUS", "00:23:54": "ASUS", "00:24:8C": "ASUS",
    "00:26:18": "ASUS", "00:90:4C": "ASUS", "04:92:26": "ASUS",
    "08:60:6E": "ASUS", "10:78:D2": "ASUS", "14:DA:E9": "ASUS",
    "1C:87:2C": "ASUS", "20:CF:30": "ASUS", "24:4B:FE": "ASUS",
    "2C:FD:A1": "ASUS", "2C:56:DC": "ASUS", "30:85:A9": "ASUS",
    "38:D5:47": "ASUS", "40:16:7E": "ASUS", "48:5D:60": "ASUS",
    "4C:ED:DE": "ASUS", "50:46:5D": "ASUS", "54:04:A6": "ASUS",
    "5C:FF:35": "ASUS", "60:45:CB": "ASUS", "64:66:B3": "ASUS",
    "6C:FD:B9": "ASUS", "74:D0:2B": "ASUS", "78:24:AF": "ASUS",
    "7C:10:C9": "ASUS", "80:1F:02": "ASUS", "88:D7:F6": "ASUS",
    "90:E6:BA": "ASUS", "AC:22:0B": "ASUS", "B0:6E:BF": "ASUS",
    "BC:EE:7B": "ASUS", "C8:60:00": "ASUS", "D4:5D:DF": "ASUS",
    "D8:50:E6": "ASUS", "E0:3F:49": "ASUS", "E4:70:B8": "ASUS",
    "F0:79:59": "ASUS", "F8:32:E4": "ASUS", "FC:34:97": "ASUS",
    # ── D-Link ─────────────────────────────────────────────────────────
    "00:05:5D": "D-Link", "00:0D:88": "D-Link", "00:0F:3D": "D-Link",
    "00:11:95": "D-Link", "00:13:46": "D-Link", "00:15:E9": "D-Link",
    "00:17:9A": "D-Link", "00:19:5B": "D-Link", "00:1B:11": "D-Link",
    "00:1C:F0": "D-Link", "00:1E:58": "D-Link", "00:21:91": "D-Link",
    "00:22:B0": "D-Link", "00:24:01": "D-Link", "1C:7E:E5": "D-Link",
    "1C:BD:B9": "D-Link", "28:10:7B": "D-Link", "34:08:04": "D-Link",
    "40:F0:2F": "D-Link", "48:EE:0C": "D-Link", "4C:00:82": "D-Link",
    "54:B8:02": "D-Link", "58:D5:6E": "D-Link", "5C:D9:98": "D-Link",
    "60:63:4C": "D-Link", "78:54:2E": "D-Link", "84:C9:B2": "D-Link",
    "B0:C5:54": "D-Link", "BC:F6:85": "D-Link", "C4:A8:1D": "D-Link",
    # ── Huawei ─────────────────────────────────────────────────────────
    "00:18:82": "Huawei", "00:1E:10": "Huawei", "00:25:9E": "Huawei",
    "00:46:4B": "Huawei", "00:9A:CD": "Huawei", "00:E0:FC": "Huawei",
    "04:02:1F": "Huawei", "04:B0:E7": "Huawei", "04:BD:88": "Huawei",
    "04:C0:6F": "Huawei", "04:F9:38": "Huawei", "08:7A:4C": "Huawei",
    "0C:96:BF": "Huawei", "10:1B:54": "Huawei", "10:47:80": "Huawei",
    "10:C6:1F": "Huawei", "14:B9:68": "Huawei", "18:C5:8A": "Huawei",
    "1C:8E:5C": "Huawei", "20:08:ED": "Huawei", "20:F1:7C": "Huawei",
    "24:09:95": "Huawei", "24:DA:33": "Huawei", "28:31:52": "Huawei",
    "2C:9D:1E": "Huawei", "30:D1:7E": "Huawei", "34:29:12": "Huawei",
    "38:37:8B": "Huawei", "3C:47:11": "Huawei", "40:4D:8E": "Huawei",
    "40:CB:A8": "Huawei", "44:6A:B7": "Huawei", "48:57:02": "Huawei",
    "4C:54:99": "Huawei", "4C:8B:EF": "Huawei", "50:68:0A": "Huawei",
    "50:9F:27": "Huawei", "54:51:1B": "Huawei", "58:2A:F7": "Huawei",
    "5C:63:BF": "Huawei", "60:DE:44": "Huawei", "64:3E:8C": "Huawei",
    "68:13:24": "Huawei", "70:54:D2": "Huawei", "70:72:3C": "Huawei",
    "74:04:F1": "Huawei", "74:A0:63": "Huawei", "78:1D:BA": "Huawei",
    "7C:60:97": "Huawei", "80:71:7A": "Huawei", "84:A8:E4": "Huawei",
    "8C:34:FD": "Huawei", "90:17:AC": "Huawei", "94:04:9C": "Huawei",
    "94:77:2B": "Huawei", "9C:28:EF": "Huawei", "9C:74:1A": "Huawei",
    "A4:99:47": "Huawei", "AC:4E:91": "Huawei", "B4:CD:27": "Huawei",
    "B8:08:D7": "Huawei", "BC:25:E0": "Huawei", "C4:07:2F": "Huawei",
    "C4:72:95": "Huawei", "C8:51:95": "Huawei", "CC:96:A0": "Huawei",
    "D0:D4:12": "Huawei", "D4:20:B0": "Huawei", "D8:12:65": "Huawei",
    "DC:D2:FC": "Huawei", "E0:19:54": "Huawei", "E4:68:A3": "Huawei",
    "E8:08:8B": "Huawei", "EC:23:3D": "Huawei", "F4:4C:7F": "Huawei",
    "F8:01:13": "Huawei", "F8:3D:FF": "Huawei", "FC:3F:DB": "Huawei",
    # ── Xiaomi ─────────────────────────────────────────────────────────
    "00:9E:C8": "Xiaomi", "0C:1D:AF": "Xiaomi", "20:34:FB": "Xiaomi",
    "28:6C:07": "Xiaomi", "34:80:B3": "Xiaomi", "38:A4:ED": "Xiaomi",
    "3C:BD:3E": "Xiaomi", "44:25:5C": "Xiaomi", "50:8F:4C": "Xiaomi",
    "50:EC:50": "Xiaomi", "54:48:E6": "Xiaomi", "58:44:98": "Xiaomi",
    "58:CB:52": "Xiaomi", "64:09:80": "Xiaomi", "64:CC:2E": "Xiaomi",
    "68:DF:DD": "Xiaomi", "6C:5A:B0": "Xiaomi", "74:51:BA": "Xiaomi",
    "78:11:DC": "Xiaomi", "7C:49:EB": "Xiaomi", "8C:BE:BE": "Xiaomi",
    "98:FA:E3": "Xiaomi", "9C:99:A0": "Xiaomi", "A4:50:46": "Xiaomi",
    "A8:9C:ED": "Xiaomi", "B0:E2:35": "Xiaomi", "B4:0B:44": "Xiaomi",
    "C4:0B:CB": "Xiaomi", "C8:DE:57": "Xiaomi", "D4:97:0B": "Xiaomi",
    "F0:B4:29": "Xiaomi", "F4:8B:32": "Xiaomi", "F8:A2:D6": "Xiaomi",
    "FC:64:BA": "Xiaomi",
    # ── Raspberry Pi Foundation ────────────────────────────────────────
    "B8:27:EB": "Raspberry Pi", "DC:A6:32": "Raspberry Pi",
    "E4:5F:01": "Raspberry Pi", "28:CD:C1": "Raspberry Pi",
    "D8:3A:DD": "Raspberry Pi",
    # ── Espressif / ESP8266 / ESP32 (IoT) ─────────────────────────────
    "10:52:1C": "Espressif (IoT)", "18:FE:34": "Espressif (IoT)",
    "24:0A:C4": "Espressif (IoT)", "24:62:AB": "Espressif (IoT)",
    "30:AE:A4": "Espressif (IoT)", "3C:71:BF": "Espressif (IoT)",
    "40:F5:20": "Espressif (IoT)", "4C:11:AE": "Espressif (IoT)",
    "50:02:91": "Espressif (IoT)", "5C:CF:7F": "Espressif (IoT)",
    "60:01:94": "Espressif (IoT)", "68:C6:3A": "Espressif (IoT)",
    "70:03:9F": "Espressif (IoT)", "7C:87:CE": "Espressif (IoT)",
    "80:7D:3A": "Espressif (IoT)", "84:0D:8E": "Espressif (IoT)",
    "84:CC:A8": "Espressif (IoT)", "8C:AA:B5": "Espressif (IoT)",
    "90:97:D5": "Espressif (IoT)", "A0:20:A6": "Espressif (IoT)",
    "A4:7B:9D": "Espressif (IoT)", "AC:0B:FB": "Espressif (IoT)",
    "B4:E6:2D": "Espressif (IoT)", "BC:DD:C2": "Espressif (IoT)",
    "C4:4F:33": "Espressif (IoT)", "CC:50:E3": "Espressif (IoT)",
    "D8:F1:5B": "Espressif (IoT)", "DC:4F:22": "Espressif (IoT)",
    "E0:98:06": "Espressif (IoT)", "E8:DB:84": "Espressif (IoT)",
    "EC:FA:BC": "Espressif (IoT)", "F4:CF:A2": "Espressif (IoT)",
    # ── Virtualization ─────────────────────────────────────────────────
    "00:0C:29": "VMware", "00:50:56": "VMware", "00:05:69": "VMware",
    "08:00:27": "VirtualBox", "52:54:00": "QEMU/KVM",
    "00:16:3E": "Xen / OpenStack",
    # ── Dell ───────────────────────────────────────────────────────────
    "00:06:5B": "Dell", "00:08:74": "Dell", "00:0B:DB": "Dell",
    "00:0D:56": "Dell", "00:0F:1F": "Dell", "00:11:43": "Dell",
    "00:12:3F": "Dell", "00:13:72": "Dell", "00:14:22": "Dell",
    "00:15:C5": "Dell", "00:16:F0": "Dell", "00:18:8B": "Dell",
    "00:19:B9": "Dell", "00:1C:23": "Dell", "00:1D:09": "Dell",
    "00:1E:4F": "Dell", "00:21:70": "Dell", "00:22:19": "Dell",
    "00:23:AE": "Dell", "00:24:E8": "Dell", "00:25:64": "Dell",
    "00:26:B9": "Dell", "14:18:77": "Dell", "18:03:73": "Dell",
    "18:66:DA": "Dell", "1C:40:24": "Dell", "20:04:0F": "Dell",
    "24:B6:FD": "Dell", "28:F1:0E": "Dell", "34:17:EB": "Dell",
    "3C:A8:2A": "Dell", "40:A8:F0": "Dell", "44:A8:42": "Dell",
    "48:4D:7E": "Dell", "4C:C9:5E": "Dell", "50:9A:4C": "Dell",
    "54:9F:35": "Dell", "5C:26:0A": "Dell", "5C:F9:DD": "Dell",
    "60:36:DD": "Dell", "68:05:CA": "Dell", "6C:2B:59": "Dell",
    "74:86:7A": "Dell", "78:2B:CB": "Dell", "84:7B:EB": "Dell",
    "90:B1:1C": "Dell", "98:90:96": "Dell", "9C:EB:E8": "Dell",
    "A4:1F:72": "Dell", "A4:4C:11": "Dell", "AC:16:2D": "Dell",
    "B0:83:FE": "Dell", "B8:2A:72": "Dell", "BC:30:5B": "Dell",
    "C8:1F:66": "Dell", "D4:AE:52": "Dell", "D8:D3:85": "Dell",
    "E4:98:D6": "Dell", "F0:4D:A2": "Dell", "F8:DB:88": "Dell",
    # ── HP / HPE ───────────────────────────────────────────────────────
    "00:01:E6": "HP", "00:02:A5": "HP", "00:04:EA": "HP",
    "00:08:02": "HP", "00:09:4B": "HP", "00:0A:57": "HP",
    "00:0B:CD": "HP", "00:0D:9D": "HP", "00:0E:7F": "HP",
    "00:11:0A": "HP", "00:12:79": "HP", "00:13:21": "HP",
    "00:14:38": "HP", "00:15:60": "HP", "00:16:35": "HP",
    "00:17:08": "HP", "00:18:FE": "HP", "00:19:BB": "HP",
    "00:1A:4B": "HP", "00:1B:78": "HP", "00:1C:C4": "HP",
    "00:1E:0B": "HP", "00:1F:29": "HP", "00:21:5A": "HP",
    "00:22:64": "HP", "00:23:7D": "HP", "00:24:81": "HP",
    "00:25:B3": "HP", "00:26:55": "HP", "00:30:6E": "HP",
    "00:50:8B": "HP", "00:60:B0": "HP", "10:60:4B": "HP",
    "18:A9:05": "HP", "1C:98:EC": "HP", "20:67:7C": "HP",
    "28:92:4A": "HP", "2C:41:38": "HP", "38:22:D8": "HP",
    "3C:D9:2B": "HP", "40:B0:34": "HP", "48:0F:CF": "HP",
    "5C:B9:01": "HP", "6C:3B:E5": "HP", "70:10:6F": "HP",
    "78:AC:C0": "HP", "80:C1:6E": "HP", "84:34:97": "HP",
    "8C:DC:D4": "HP", "98:E7:F4": "HP", "9C:8E:99": "HP",
    "A0:D3:C1": "HP", "B4:99:BA": "HP", "BC:EA:FA": "HP",
    "C4:34:6B": "HP", "C8:CB:B8": "HP", "D4:C9:EF": "HP",
    "D8:9D:67": "HP", "EC:B1:D7": "HP", "F0:92:1C": "HP",
    # ── Lenovo ─────────────────────────────────────────────────────────
    "00:0F:20": "Lenovo", "00:21:CC": "Lenovo", "04:7D:7B": "Lenovo",
    "0C:8B:FD": "Lenovo", "10:65:30": "Lenovo", "18:1D:EA": "Lenovo",
    "20:7C:8F": "Lenovo", "2C:4D:54": "Lenovo", "38:B1:DB": "Lenovo",
    "3C:97:0E": "Lenovo", "40:98:AD": "Lenovo", "44:85:00": "Lenovo",
    "54:EE:75": "Lenovo", "5C:93:A2": "Lenovo", "6C:5C:14": "Lenovo",
    "70:E2:84": "Lenovo", "78:2B:46": "Lenovo", "80:86:F2": "Lenovo",
    "84:2B:2B": "Lenovo", "90:2B:34": "Lenovo", "AC:61:75": "Lenovo",
    "B8:88:E3": "Lenovo", "C0:38:96": "Lenovo", "C8:5B:76": "Lenovo",
    "D0:37:45": "Lenovo", "E0:94:67": "Lenovo", "F0:DE:F1": "Lenovo",
    # ── Sony / PlayStation ─────────────────────────────────────────────
    "00:01:4A": "Sony", "00:04:20": "Sony", "00:0A:D9": "Sony",
    "00:13:A9": "Sony", "00:19:C5": "Sony", "00:1A:80": "Sony",
    "00:1D:0D": "Sony", "00:1E:A9": "Sony", "00:24:BE": "Sony (PlayStation)",
    "04:2F:B4": "Sony", "10:4F:A8": "Sony", "18:54:CF": "Sony",
    "1C:98:C1": "Sony (PlayStation)", "28:0D:FC": "Sony",
    "30:17:C8": "Sony", "70:2A:D5": "Sony", "78:84:3C": "Sony",
    "7C:B7:33": "Sony", "84:C7:EA": "Sony", "8C:9C:12": "Sony",
    "A8:E3:EE": "Sony", "AC:9B:0A": "Sony", "E0:AE:5E": "Sony",
    # ── Nintendo ───────────────────────────────────────────────────────
    "00:09:BF": "Nintendo", "00:16:56": "Nintendo", "00:17:AB": "Nintendo",
    "00:19:1D": "Nintendo", "00:1A:E9": "Nintendo", "00:1B:EA": "Nintendo",
    "00:1C:BE": "Nintendo", "00:1E:35": "Nintendo", "00:1F:32": "Nintendo",
    "00:21:47": "Nintendo", "00:22:D7": "Nintendo", "00:24:44": "Nintendo",
    "00:24:F3": "Nintendo", "00:25:A0": "Nintendo", "00:26:59": "Nintendo",
    "40:D2:8A": "Nintendo (Switch)", "98:B6:E9": "Nintendo (Switch)",
    "A4:C0:E1": "Nintendo (3DS)", "B8:AE:6E": "Nintendo (Switch)",
    "E0:0C:7F": "Nintendo (Wii U)",
    # ── Ubiquiti ───────────────────────────────────────────────────────
    "00:15:6D": "Ubiquiti", "00:27:22": "Ubiquiti", "24:A4:3C": "Ubiquiti",
    "44:D9:E7": "Ubiquiti", "68:72:51": "Ubiquiti", "74:83:C2": "Ubiquiti",
    "78:8A:20": "Ubiquiti", "80:2A:A8": "Ubiquiti", "DC:9F:DB": "Ubiquiti",
    "E0:63:DA": "Ubiquiti", "F0:9F:C2": "Ubiquiti", "FC:EC:DA": "Ubiquiti",
    # ── Mikrotik ───────────────────────────────────────────────────────
    "00:0C:42": "Mikrotik", "2C:C8:1B": "Mikrotik", "6C:3B:6B": "Mikrotik",
    "8C:88:2B": "Mikrotik", "B8:69:F4": "Mikrotik", "CC:2D:E0": "Mikrotik",
    "D4:CA:6D": "Mikrotik", "E4:8D:8C": "Mikrotik",
    # ── Fortinet ───────────────────────────────────────────────────────
    "00:09:0F": "Fortinet", "08:5B:0E": "Fortinet",
    "70:4C:A5": "Fortinet", "90:6C:AC": "Fortinet", "A8:C0:43": "Fortinet",
    # ── Juniper ────────────────────────────────────────────────────────
    "00:10:DB": "Juniper", "00:12:1E": "Juniper", "00:19:E2": "Juniper",
    "00:1F:12": "Juniper", "2C:6B:F5": "Juniper", "3C:61:04": "Juniper",
    "40:B5:C1": "Juniper", "44:F4:77": "Juniper", "58:00:BB": "Juniper",
    "7C:EB:E2": "Juniper",
    # ── Aruba Networks ─────────────────────────────────────────────────
    "00:0B:86": "Aruba Networks", "00:24:6C": "Aruba Networks",
    "20:4C:03": "Aruba Networks", "24:DE:C6": "Aruba Networks",
    "40:E3:D6": "Aruba Networks", "6C:F3:7F": "Aruba Networks",
    "84:D4:7E": "Aruba Networks", "94:B4:0F": "Aruba Networks",
    "AC:A3:1E": "Aruba Networks",
    # ── Synology (NAS) ─────────────────────────────────────────────────
    "00:11:32": "Synology", "BC:5F:F4": "Synology", "00:50:43": "Synology",
    # ── QNAP (NAS) ─────────────────────────────────────────────────────
    "00:08:9B": "QNAP", "24:5E:BE": "QNAP", "28:C2:DD": "QNAP",
    "6C:CF:39": "QNAP",
    # ── Western Digital ────────────────────────────────────────────────
    "00:90:A9": "Western Digital", "00:14:EE": "Western Digital",
    # ── AVM Fritz!Box ──────────────────────────────────────────────────
    "00:04:0E": "AVM (Fritz!Box)", "3C:A6:2F": "AVM (Fritz!Box)",
    "A0:63:91": "AVM (Fritz!Box)", "C4:86:E9": "AVM (Fritz!Box)",
    "DC:39:6F": "AVM (Fritz!Box)", "B4:D7:3D": "AVM (Fritz!Box)",
    # ── Arris (Cable Modems) ────────────────────────────────────────────
    "00:17:EE": "Arris", "00:1C:10": "Arris", "00:21:80": "Arris",
    "00:26:B8": "Arris", "40:0E:22": "Arris", "44:E4:37": "Arris",
    "48:9D:24": "Arris", "50:39:55": "Arris", "AC:87:A3": "Arris",
    "D4:05:98": "Arris", "E4:83:26": "Arris",
    # ── Sagemcom ───────────────────────────────────────────────────────
    "00:1E:92": "Sagemcom", "2C:95:69": "Sagemcom",
    "30:87:30": "Sagemcom", "D8:23:27": "Sagemcom",
    # ── ZTE ────────────────────────────────────────────────────────────
    "00:19:C6": "ZTE", "00:26:ED": "ZTE", "28:2C:B2": "ZTE",
    "3C:76:4F": "ZTE", "40:62:31": "ZTE", "58:6D:8F": "ZTE",
    "60:02:B4": "ZTE", "68:AB:1E": "ZTE", "7C:B2:57": "ZTE",
    "8C:A6:DF": "ZTE", "A0:7A:C2": "ZTE", "AC:F1:DF": "ZTE",
    "CC:A2:23": "ZTE",
    # ── Printers ───────────────────────────────────────────────────────
    "00:00:48": "Epson",   "00:26:AB": "Epson",   "28:50:E7": "Epson",
    "64:EB:8C": "Epson",   "AC:18:26": "Epson",   "EC:A8:6B": "Epson",
    "00:00:85": "Canon",   "00:1E:8F": "Canon",   "08:00:46": "Canon",
    "40:B0:76": "Canon",   "90:1B:0E": "Canon",   "AC:E8:7B": "Canon",
    "C4:62:EA": "Canon",
    "00:00:F4": "Brother", "00:1B:A9": "Brother", "00:80:77": "Brother",
    "30:05:5C": "Brother", "74:27:EA": "Brother", "98:22:EF": "Brother",
    "BC:5C:4C": "Brother", "E0:7C:13": "Brother",
    "00:21:B7": "Lexmark", "00:04:AC": "Lexmark",
    # ── Linksys ────────────────────────────────────────────────────────
    "00:06:25": "Linksys", "00:0C:41": "Linksys", "00:12:17": "Linksys",
    "00:13:10": "Linksys", "00:14:BF": "Linksys", "00:16:B6": "Linksys",
    "00:18:39": "Linksys", "00:18:F8": "Linksys", "00:1A:70": "Linksys",
    "00:1D:7E": "Linksys", "00:20:E0": "Linksys", "00:21:29": "Linksys",
    "00:22:6B": "Linksys", "00:23:69": "Linksys",
    # ── LG Electronics ─────────────────────────────────────────────────
    "00:1C:62": "LG Electronics", "00:1E:75": "LG Electronics",
    "00:26:E2": "LG Electronics", "04:D6:AA": "LG Electronics",
    "18:67:B0": "LG Electronics", "1C:08:C1": "LG Electronics",
    "20:AB:37": "LG Electronics", "30:CD:A7": "LG Electronics",
    "34:31:11": "LG Electronics", "48:59:29": "LG Electronics",
    "50:CC:F8": "LG Electronics", "6C:C0:EB": "LG Electronics",
    "70:66:55": "LG Electronics", "78:59:5E": "LG Electronics",
    "80:F6:2E": "LG Electronics", "88:36:6C": "LG Electronics",
    "94:02:9A": "LG Electronics", "A0:39:F7": "LG Electronics",
    "BC:F5:AC": "LG Electronics", "C4:36:6C": "LG Electronics",
    "DC:0B:34": "LG Electronics", "E8:5B:5B": "LG Electronics",
    # ── Sonos ──────────────────────────────────────────────────────────
    "00:0E:58": "Sonos", "34:7E:5C": "Sonos", "54:2A:1B": "Sonos",
    "5C:AA:FD": "Sonos", "78:28:CA": "Sonos", "94:9F:3E": "Sonos",
    "B8:E9:37": "Sonos",
    # ── Philips Hue / Signify ──────────────────────────────────────────
    "00:17:88": "Philips Hue", "EC:B5:FA": "Philips Hue",
    # ── Roku ───────────────────────────────────────────────────────────
    "08:05:81": "Roku", "AC:3A:7A": "Roku", "B0:A7:37": "Roku",
    "CC:6D:A0": "Roku", "D8:31:CF": "Roku", "DC:3A:5E": "Roku",
    "F4:EC:38": "Roku",
    # ── Ring ───────────────────────────────────────────────────────────
    "B0:09:DA": "Ring (Amazon)",
    # ── Super Micro ────────────────────────────────────────────────────
    "00:25:90": "Super Micro", "0C:C4:7A": "Super Micro",
    "3C:EC:EF": "Super Micro", "AC:1F:6B": "Super Micro",
    # ── Realtek ────────────────────────────────────────────────────────
    "00:E0:4C": "Realtek", "A8:A1:59": "Realtek", "6C:5C:3D": "Realtek",
    # ── 3Com ───────────────────────────────────────────────────────────
    "00:01:02": "3Com", "00:04:75": "3Com", "00:0A:5E": "3Com",
    "00:10:4B": "3Com", "00:20:AF": "3Com", "00:60:08": "3Com",
    # ── Tuya Smart ─────────────────────────────────────────────────────
    "70:5A:0F": "Tuya Smart", "7C:01:91": "Tuya Smart",
    # ── MSI ────────────────────────────────────────────────────────────
    "00:50:6A": "MSI", "00:D0:59": "MSI",
    # ── Gigabyte ───────────────────────────────────────────────────────
    "00:16:17": "Gigabyte", "1C:6F:65": "Gigabyte", "50:E5:49": "Gigabyte",
    # ── Acer ───────────────────────────────────────────────────────────
    "00:16:D3": "Acer", "00:1A:73": "Acer", "08:62:66": "Acer",
    "50:AF:73": "Acer",
}

COMMON_PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
    53: "DNS", 80: "HTTP", 110: "POP3", 135: "RPC",
    139: "NetBIOS", 143: "IMAP", 443: "HTTPS", 445: "SMB",
    3389: "RDP", 8080: "HTTP-Alt", 8443: "HTTPS-Alt",
    1883: "MQTT", 5900: "VNC", 3306: "MySQL", 5432: "PostgreSQL",
    27017: "MongoDB", 6379: "Redis", 11211: "Memcached",
}

# ─── Utility helpers ────────────────────────────────────────
def clr():
    os.system('cls' if os.name == 'nt' else 'clear')

def ts():
    return datetime.now().strftime("%H:%M:%S")

def banner():
    print(f"""
{NC}{BOLD}╔══════════════════════════════════════════════════════════════════════════╗{R}
{NC}║{NY}{BOLD}  ▓▓  NETREAPER v2.0.77  ▓▓  NETWORK QUICKHACK PROTOCOL  ▓▓  ONLINE  ▓▓  {NC}║{R}
{NC}╠══════════════════════════════════════════════════════════════════════════╣{R}
{NC}║  {GR}Jack in. Identify rogue ICE. Map the grid. Stay ghost.                  {NC}║{R}
{NC}║  {GR}Operator: {W}Anonymous{GR}  │  Timestamp: {W}{ts()}{GR}  │  Platform: {W}{sys.platform.upper():<8}{GR}        {NC}║{R}
{NC}╚══════════════════════════════════════════════════════════════════════════╝{R}
""")

def divider(label="", char="─", width=74, color=NC):
    if label:
        side = (width - len(label) - 2) // 2
        print(f"{color}{char * side} {NY}{BOLD}{label}{R}{color} {char * side}{R}")
    else:
        print(f"{color}{char * width}{R}")

def status(msg, level="info"):
    icons = {"info": f"{NC}◈", "ok": f"{NG}◆", "warn": f"{NO}◉", "bad": f"{NR}✖", "scan": f"{NP}◐"}
    ic = icons.get(level, icons["info"])
    print(f"  {ic}{R} {GR}[{ts()}]{R}  {msg}")

def spin_label(label, stop_event, interval=0.1):
    frames = ["◐", "◓", "◑", "◒"]
    i = 0
    while not stop_event.is_set():
        print(f"\r  {NP}{frames[i % 4]}{R}  {label}   ", end="", flush=True)
        time.sleep(interval)
        i += 1
    print(f"\r{' ' * 60}\r", end="", flush=True)

# ─── Network Detection ──────────────────────────────────────
def get_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except:
        return None

def get_network_range(ip, prefix=24):
    net = ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False)
    return str(net)

def detect_gateway():
    try:
        if sys.platform == "win32":
            out = subprocess.check_output("ipconfig", text=True)
            for line in out.splitlines():
                if "Default Gateway" in line and "." in line:
                    return line.split(":")[-1].strip()
        else:
            out = subprocess.check_output(
                ["ip", "route", "show", "default"], text=True, stderr=subprocess.DEVNULL
            )
            parts = out.split()
            if "via" in parts:
                return parts[parts.index("via") + 1]
    except:
        pass
    return None

# ─── Ping & ARP ─────────────────────────────────────────────
def ping_host(ip, timeout=1):
    """Return True if host responds to ping."""
    try:
        if sys.platform == "win32":
            cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), str(ip)]
        else:
            cmd = ["ping", "-c", "1", "-W", str(timeout), str(ip)]
        result = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout + 1
        )
        return result.returncode == 0
    except:
        return False

def arp_scan_host(ip):
    """
    Send ARP via system 'arp' command after pinging.
    Returns MAC or None.
    """
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(["arp", "-a", str(ip)], text=True, stderr=subprocess.DEVNULL)
            match = re.search(r"([\da-fA-F]{2}[:-]){5}[\da-fA-F]{2}", out)
        else:
            out = subprocess.check_output(["arp", "-n", str(ip)], text=True, stderr=subprocess.DEVNULL)
            match = re.search(r"([\da-fA-F]{2}[:-]){5}[\da-fA-F]{2}", out)
        if match:
            return match.group(0).upper().replace("-", ":")
    except:
        pass
    return None

def read_arp_cache():
    """Read full ARP cache from /proc/net/arp (Linux) or arp -a (others)."""
    cache = {}
    try:
        if sys.platform == "linux":
            with open("/proc/net/arp") as f:
                for line in f.readlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 4 and parts[3] != "00:00:00:00:00:00":
                        cache[parts[0]] = parts[3].upper()
        else:
            out = subprocess.check_output(["arp", "-a"], text=True, stderr=subprocess.DEVNULL)
            for line in out.splitlines():
                ip_m = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)", line)
                mac_m = re.search(r"([\da-fA-F]{2}[:-]){5}[\da-fA-F]{2}", line)
                if ip_m and mac_m:
                    cache[ip_m.group(1)] = mac_m.group(0).upper().replace("-", ":")
    except:
        pass
    return cache

def resolve_hostname(ip):
    try:
        return socket.gethostbyaddr(str(ip))[0]
    except:
        return None

def lookup_vendor(mac):
    if not mac or len(mac) < 8:
        return "Unknown"
    prefix = mac[:8].upper()
    return OUI_DB.get(prefix, "Unknown")

def classify_device(vendor, hostname, ports):
    v = (vendor or "").lower()
    h = (hostname or "").lower()
    p = ports or []
    if any(x in v for x in ["apple", "samsung", "xiaomi", "motorola"]):
        if any(x in h for x in ["iphone", "ipad", "android", "phone"]):
            return "📱 Mobile"
        return "💻 Endpoint"
    if any(x in v for x in ["raspberry", "arduino", "espressif"]):
        return "🤖 IoT/SBC"
    if any(x in v for x in ["cisco", "netgear", "tp-link", "d-link", "asus", "linksys", "ubiquiti", "netopia"]):
        return "🌐 Network Gear"
    if any(x in v for x in ["vmware", "virtualbox", "qemu", "hyper-v", "kvm"]):
        return "🖥️  Virtual"
    if any(x in v for x in ["amazon", "google", "nest"]):
        return "🔊 Smart Speaker"
    if 3389 in p:
        return "🖥️  Windows PC"
    if 22 in p and 80 not in p:
        return "🐧 Linux/Server"
    if 80 in p or 443 in p:
        return "🌐 Web Server"
    return "❓ Unknown"

# ─── Port Scanner ───────────────────────────────────────────
def scan_ports(ip, ports=None, timeout=0.5):
    if ports is None:
        ports = list(COMMON_PORTS.keys())
    open_ports = []
    for port in ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                if s.connect_ex((str(ip), port)) == 0:
                    open_ports.append(port)
        except:
            pass
    return open_ports

# ─── Core Sweep ─────────────────────────────────────────────
def sweep_host(ip, arp_cache, do_ports=True):
    ip_str = str(ip)
    alive = ping_host(ip_str) or ip_str in arp_cache
    if not alive:
        return None

    mac = arp_cache.get(ip_str) or arp_scan_host(ip_str)
    hostname = resolve_hostname(ip_str)
    vendor = lookup_vendor(mac) if mac else "Unknown"
    ports = scan_ports(ip_str, list(COMMON_PORTS.keys()), timeout=0.4) if do_ports else []
    device_type = classify_device(vendor, hostname, ports)

    return {
        "ip": ip_str,
        "mac": mac or "??:??:??:??:??:??",
        "hostname": hostname or "—",
        "vendor": vendor,
        "type": device_type,
        "ports": ports,
        "ts": ts(),
    }

# ─── Result Printer ─────────────────────────────────────────
def print_device(d, index, gateway_ip, local_ip):
    ip      = d["ip"]
    mac     = d["mac"]
    host    = d["hostname"]
    vendor  = d["vendor"]
    dtype   = d["type"]
    ports   = d["ports"]

    # Threat coloring
    is_local   = ip == local_ip
    is_gateway = ip == gateway_ip
    is_unknown = vendor == "Unknown" and host == "—"

    if is_gateway:
        ip_color = NC + BOLD
        tag = f"  {NY}[GATEWAY]{R}"
    elif is_local:
        ip_color = NG + BOLD
        tag = f"  {NG}[YOU]{R}"
    elif is_unknown:
        ip_color = NR + BOLD + BLINK
        tag = f"  {NR}[ROGUE?]{R}"
    else:
        ip_color = NY + BOLD
        tag = ""

    # Port list
    if ports:
        port_str = "  ".join(
            f"{NP}{p}{GR}/{COMMON_PORTS.get(p, '?')}{R}"
            for p in sorted(ports)
        )
    else:
        port_str = f"{GR}none detected{R}"

    idx_str = f"{GR}{index:02d}{R}"
    print(f"\n  {NC}┌─ {idx_str}  {ip_color}{ip:<16}{R}{tag}")
    print(f"  {NC}│{R}  {GR}MAC    {R}  {W}{mac}{R}   {GR}│{R}  {GR}Vendor{R}  {NO}{vendor}{R}")
    print(f"  {NC}│{R}  {GR}Host   {R}  {W}{host:<36}{R}")
    print(f"  {NC}│{R}  {GR}Type   {R}  {dtype:<20}  {GR}Seen{R}  {GR}{d['ts']}{R}")
    if ports:
        print(f"  {NC}│{R}  {GR}Ports  {R}  {port_str}")
    print(f"  {NC}└{'─' * 60}{R}")

# ─── Export ─────────────────────────────────────────────────
def export_results(devices, outfile="netreaper_results.json"):
    path = os.path.abspath(outfile)
    with open(path, "w") as f:
        json.dump({"scan_time": str(datetime.now()), "devices": devices}, f, indent=2)
    return path

# ─── Main ───────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="NETREAPER — Cyberpunk Network Scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-r", "--range",  help="CIDR range to scan (e.g. 192.168.1.0/24)")
    parser.add_argument("-t", "--threads", type=int, default=100, help="Parallel threads (default: 100)")
    parser.add_argument("-p", "--no-ports", action="store_true", help="Skip port scanning")
    parser.add_argument("-e", "--export", metavar="FILE", help="Export results to JSON file")
    parser.add_argument("-s", "--stealth", action="store_true", help="Slower, quieter scan (25 threads, no ports)")
    args = parser.parse_args()

    clr()
    banner()

    # ── Network Setup ──────────────────────────────────────
    local_ip  = get_local_ip()
    gateway   = detect_gateway()
    net_range = args.range or (get_network_range(local_ip) if local_ip else None)

    if not net_range:
        status(f"{NR}Could not determine network range. Use -r to specify.{R}", "bad")
        sys.exit(1)

    do_ports = not (args.no_ports or args.stealth)
    threads  = 25 if args.stealth else args.threads

    divider("SYSTEM LINK ESTABLISHED")
    status(f"Local IP   : {NY}{BOLD}{local_ip}{R}", "ok")
    status(f"Gateway    : {NC}{gateway or 'unknown'}{R}", "ok")
    status(f"Scan Range : {NY}{net_range}{R}", "ok")
    status(f"Mode       : {NP}{'STEALTH' if args.stealth else 'AGGRESSIVE'}{R}  │  Threads: {NY}{threads}{R}  │  Port Scan: {NG if do_ports else NR}{'ON' if do_ports else 'OFF'}{R}", "ok")
    divider()

    # ── Pre-load ARP cache ─────────────────────────────────
    status("Loading ARP cache...", "scan")
    arp_cache = read_arp_cache()
    if arp_cache:
        status(f"ARP cache: {NY}{len(arp_cache)}{R} entries pre-loaded", "ok")

    time.sleep(0.3)

    # ── Hosts list ─────────────────────────────────────────
    try:
        network  = ipaddress.IPv4Network(net_range, strict=False)
        hosts    = list(network.hosts())
    except ValueError as e:
        status(f"{NR}Invalid range: {e}{R}", "bad")
        sys.exit(1)

    total    = len(hosts)
    divider(f"INITIATING SWEEP — {total} ADDRESSES")

    found    = []
    lock     = threading.Lock()
    done     = [0]
    bar_stop = threading.Event()

    def progress():
        bar_width = 40
        while not bar_stop.is_set():
            pct = done[0] / total
            filled = int(bar_width * pct)
            bar = (f"{NG}{'█' * filled}{GR}{'░' * (bar_width - filled)}{R}")
            print(
                f"\r  {NP}◈{R}  [{bar}{R}]  {NY}{done[0]:4}/{total}{R}  "
                f"{GR}Found: {NG}{len(found):3}{R}   ",
                end="", flush=True
            )
            time.sleep(0.15)
        print(f"\r{' ' * 80}\r", end="", flush=True)

    pt = threading.Thread(target=progress, daemon=True)
    pt.start()

    def worker(ip):
        result = sweep_host(ip, arp_cache, do_ports=do_ports)
        with lock:
            done[0] += 1
            if result:
                found.append(result)
        return result

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {executor.submit(worker, ip): ip for ip in hosts}
        for _ in as_completed(futures):
            pass

    bar_stop.set()
    pt.join()
    time.sleep(0.1)

    # ── Results ────────────────────────────────────────────
    found.sort(key=lambda d: ipaddress.IPv4Address(d["ip"]))

    print()
    divider(f"GRID MAP — {len(found)} DEVICE(S) DETECTED")
    print()

    if not found:
        status(f"{NR}No live hosts found. The net is dark.{R}", "bad")
    else:
        for i, d in enumerate(found, 1):
            print_device(d, i, gateway, local_ip)

    # ── Threat summary ─────────────────────────────────────
    rogues = [d for d in found if d["vendor"] == "Unknown" and d["hostname"] == "—" and d["ip"] not in [local_ip, gateway]]
    exposed = [d for d in found if any(p in d["ports"] for p in [23, 135, 139, 445, 3389, 5900])]

    print()
    divider("THREAT ASSESSMENT")
    status(f"Total devices  : {NY}{BOLD}{len(found)}{R}", "info")
    status(f"Unidentified   : {NR if rogues else NG}{BOLD}{len(rogues)}{R}  {'← INVESTIGATE' if rogues else ''}", "warn" if rogues else "ok")
    status(f"Exposed ports  : {NR if exposed else NG}{BOLD}{len(exposed)}{R}  {GR}(Telnet/RDP/VNC/SMB){R}", "warn" if exposed else "ok")

    if rogues:
        print()
        status(f"{NR}{BOLD}ROGUE CANDIDATES:{R}", "bad")
        for r in rogues:
            print(f"    {NR}►  {BOLD}{r['ip']:<18}{R}  MAC: {W}{r['mac']}{R}")

    if exposed:
        print()
        status(f"{NO}{BOLD}HIGH-RISK DEVICES (open dangerous ports):{R}", "warn")
        for d in exposed:
            risky = [COMMON_PORTS[p] for p in d["ports"] if p in [23, 135, 139, 445, 3389, 5900]]
            print(f"    {NO}►  {BOLD}{d['ip']:<18}{R}  {NR}{', '.join(risky)}{R}")

    # ── Export ─────────────────────────────────────────────
    if args.export or len(found) > 0:
        outfile = args.export or "netreaper_results.json"
        path = export_results(found, outfile)
        print()
        status(f"Results saved → {NY}{path}{R}", "ok")

    print()
    divider("JACK OUT")
    print(f"\n  {GR}Scan completed at {NY}{ts()}{GR}. Stay ghost, netrunner.{R}\n")

# ─── Entry ──────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  {NR}◈  SCAN ABORTED — Jack pulled.{R}\n")
        sys.exit(0)
