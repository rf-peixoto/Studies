#!/usr/bin/env python3
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
    "00:00:0C": "Cisco", "00:1A:A0": "Dell", "00:50:56": "VMware",
    "00:0C:29": "VMware", "00:15:5D": "Microsoft (Hyper-V)",
    "52:54:00": "QEMU/KVM", "08:00:27": "VirtualBox",
    "B8:27:EB": "Raspberry Pi", "DC:A6:32": "Raspberry Pi",
    "E4:5F:01": "Raspberry Pi", "28:CD:C1": "Raspberry Pi",
    "00:1B:63": "Apple", "00:23:12": "Apple", "F0:18:98": "Apple",
    "A4:C3:F0": "Apple", "3C:22:FB": "Apple", "38:F9:D3": "Apple",
    "18:65:90": "Apple", "AC:BC:32": "Apple", "F4:F1:5A": "Apple",
    "00:1D:AA": "D-Link", "1C:7E:E5": "D-Link", "B0:C5:54": "D-Link",
    "C8:D3:A3": "TP-Link", "50:C7:BF": "TP-Link", "54:AF:97": "TP-Link",
    "EC:08:6B": "TP-Link", "F8:1A:67": "TP-Link", "18:A6:F7": "TP-Link",
    "00:90:4C": "ASUS", "04:92:26": "ASUS", "2C:FD:A1": "ASUS",
    "04:D4:C4": "ASUS", "AC:22:0B": "ASUS", "F8:32:E4": "ASUS",
    "00:26:5A": "Netgear", "A0:21:B7": "Netgear", "20:E5:2A": "Netgear",
    "C0:FF:D4": "Netgear", "9C:D3:6D": "Netgear",
    "00:18:E7": "Linksys/Cisco", "00:23:69": "Linksys",
    "00:1E:E5": "Linksys", "C8:BE:19": "Samsung",
    "34:14:5F": "Samsung", "00:07:AB": "Samsung", "CC:07:AB": "Samsung",
    "70:F9:27": "Samsung", "8C:77:12": "Samsung",
    "B0:72:BF": "Huawei", "CC:96:A0": "Huawei", "00:46:4B": "Huawei",
    "00:E0:FC": "Huawei", "48:57:02": "Huawei",
    "00:08:22": "InPro Comm", "00:04:76": "3Com",
    "00:60:08": "3Com", "00:00:E8": "Accton Technology",
    "FC:EC:DA": "Ubiquiti", "00:27:22": "Ubiquiti", "DC:9F:DB": "Ubiquiti",
    "24:A4:3C": "Ubiquiti", "74:83:C2": "Ubiquiti",
    "00:50:C2": "IEEE Registered", "00:1F:F3": "Apple",
    "78:4F:43": "Google (Nest)", "54:60:09": "Google",
    "F4:F5:D8": "Google", "3C:5A:B4": "Google",
    "00:1A:11": "Google", "94:EB:2C": "Google",
    "68:37:E9": "Amazon/Echo", "44:65:0D": "Amazon",
    "FC:65:DE": "Amazon", "F0:81:73": "Amazon",
    "18:74:2E": "Xiaomi", "F8:A2:D6": "Xiaomi", "00:9E:C8": "Xiaomi",
    "AC:C1:EE": "Intel", "00:21:6B": "Intel", "40:8D:5C": "Intel",
    "F4:06:69": "Intel", "A4:34:D9": "Intel",
    "00:1B:21": "Intel", "10:02:B5": "Intel",
    "00:24:D7": "Motorola", "AC:C9:06": "Motorola",
    "00:16:6C": "Netopia", "00:15:E9": "Dell",
    "18:66:DA": "Dell", "F8:DB:88": "Dell", "14:18:77": "Dell",
    "00:25:90": "Super Micro",
    "A8:A1:59": "Realtek", "00:E0:4C": "Realtek",
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
