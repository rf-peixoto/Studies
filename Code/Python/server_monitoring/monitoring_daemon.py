#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import time
import socket
import argparse
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import psutil


# ------------------------------------------------------------
# Helpers de config
# ------------------------------------------------------------

DEFAULT_CONFIG = {
    "interval_seconds": 60,
    "alert_mode": "verbose",
    "disk": {
        "default_warning": 80,
        "default_critical": 90,
        "check_inodes": True,
        "mount_overrides": {
            "/var": {"warning": 70, "critical": 90, "check_inodes": True}
        },
        "exclude_fs_types": ["tmpfs", "devtmpfs", "squashfs"],
        "exclude_mount_points": ["/run", "/boot/efi"]
    },
    "memory": {
        "warning": 80,
        "critical": 90,
        "swap_warning": 10,
        "swap_critical": 30
    },
    "telegram": {
        "bot_token": "PUT_YOUR_TOKEN_HERE",
        "chat_id": 0
    }
}


def load_or_create_config(path: str):
    if not os.path.isfile(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        print(f"Default setup saved at {path}")
        print("Edit 'telegram.bot_token' and 'telegram.chat_id' and try again")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Minimum check:
    if cfg["telegram"]["bot_token"] == "PUT_YOUR_TOKEN_HERE" or cfg["telegram"]["chat_id"] == 0:
        print("Invalid Telegram credentials. Check setup file.")
        sys.exit(1)

    return cfg


# ------------------------------------------------------------
# Utils
# ------------------------------------------------------------

def get_hostname():
    return socket.gethostname()


def get_primary_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"


def get_uptime():
    boot = psutil.boot_time()
    now = time.time()
    delta = int(now - boot)
    days = delta // 86400
    delta %= 86400
    hours = delta // 3600
    delta %= 3600
    minutes = delta // 60
    seconds = delta % 60
    return f"{days}d {hours:02d}h {minutes:02d}m {seconds:02d}s"


# ------------------------------------------------------------
# Memory
# ------------------------------------------------------------

def check_memory(cfg):
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()

    mem_percent = vm.percent
    swap_percent = sm.percent if sm.total > 0 else 0

    warning = (
        mem_percent >= cfg["memory"]["warning"]
        or (swap_percent >= cfg["memory"]["swap_warning"] and sm.total > 0)
    )
    critical = (
        mem_percent >= cfg["memory"]["critical"]
        or (swap_percent >= cfg["memory"]["swap_critical"] and sm.total > 0)
    )

    status = "OK"
    if critical:
        status = "CRITICAL"
    elif warning:
        status = "WARNING"

    return {
        "status": status,
        "ram": {
            "total": vm.total,
            "used": vm.total - vm.available,
            "available": vm.available,
            "percent": mem_percent,
        },
        "swap": {
            "total": sm.total,
            "used": sm.used,
            "percent": swap_percent,
        }
    }


# ------------------------------------------------------------
# Disks
# ------------------------------------------------------------

def get_inodes_usage(mountpoint):
    try:
        st = os.statvfs(mountpoint)
        total = st.f_files
        free = st.f_ffree
        used = total - free
        if total == 0:
            return 0
        return used / total * 100
    except Exception:
        return 0


def check_disks(cfg):
    partitions = psutil.disk_partitions(all=False)

    mounts = []
    status = "OK"
    for p in partitions:
        if p.fstype in cfg["disk"]["exclude_fs_types"]:
            continue
        if p.mountpoint in cfg["disk"]["exclude_mount_points"]:
            continue

        try:
            usage = psutil.disk_usage(p.mountpoint)
        except PermissionError:
            continue

        m_cfg = cfg["disk"]["mount_overrides"].get(p.mountpoint, {})
        warn_th = m_cfg.get("warning", cfg["disk"]["default_warning"])
        crit_th = m_cfg.get("critical", cfg["disk"]["default_critical"])
        check_inodes = m_cfg.get("check_inodes", cfg["disk"]["check_inodes"])

        inodes_percent = get_inodes_usage(p.mountpoint) if check_inodes else None

        m_status = "OK"
        if usage.percent >= crit_th or (inodes_percent is not None and inodes_percent >= crit_th):
            m_status = "CRITICAL"
        elif usage.percent >= warn_th or (inodes_percent is not None and inodes_percent >= warn_th):
            m_status = "WARNING"

        mounts.append({
            "device": p.device,
            "mount": p.mountpoint,
            "fstype": p.fstype,
            "used": usage.used,
            "total": usage.total,
            "percent": usage.percent,
            "inodes_percent": inodes_percent,
            "status": m_status
        })

        # Estado geral do disco baseado no pior caso
        if m_status == "CRITICAL":
            status = "CRITICAL"
        elif m_status == "WARNING" and status != "CRITICAL":
            status = "WARNING"

    return {"status": status, "mounts": mounts}


# ------------------------------------------------------------
# Proccess
# ------------------------------------------------------------

def get_top_processes_by_memory(n=5):
    procs = []
    for p in psutil.process_iter(["pid", "name", "username", "memory_info", "memory_percent"]):
        try:
            rss = p.info["memory_info"].rss
            procs.append((rss, p))
        except Exception:
            continue
    procs.sort(reverse=True, key=lambda x: x[0])
    top = []
    for _, p in procs[:n]:
        try:
            top.append({
                "pid": p.pid,
                "name": p.info["name"],
                "user": p.info["username"],
                "rss": p.info["memory_info"].rss,
                "percent": p.info["memory_percent"]
            })
        except Exception:
            continue
    return top


# ------------------------------------------------------------
# Alerts
# ------------------------------------------------------------

def fmt_bytes(num):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} PB"


def format_summary_message(mem, disks):
    h = get_hostname()
    ip = get_primary_ip()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    msg = []
    msg.append(f"[{max(mem['status'], disks['status'])}] Resource usage on {h}")
    msg.append(f"Time: {ts}")
    msg.append(f"Host: {h} ({ip})")
    msg.append("")

    msg.append("Memory:")
    msg.append(f"- RAM: {mem['ram']['percent']:.1f}% used ({fmt_bytes(mem['ram']['used'])} / {fmt_bytes(mem['ram']['total'])})")
    if mem["swap"]["total"] > 0:
        msg.append(f"- Swap: {mem['swap']['percent']:.1f}% used ({fmt_bytes(mem['swap']['used'])} / {fmt_bytes(mem['swap']['total'])})")
    msg.append("")

    msg.append("Disk:")
    for m in disks["mounts"]:
        if m["status"] != "OK":
            msg.append(f"- {m['mount']}: {m['percent']:.1f}% used ({fmt_bytes(m['used'])} / {fmt_bytes(m['total'])})")
    if len([m for m in disks["mounts"] if m["status"] != "OK"]) == 0:
        msg.append("- All healthy")

    return "\n".join(msg)


def format_verbose_message(mem, disks):
    h = get_hostname()
    ip = get_primary_ip()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    load = os.getloadavg()
    uptime = get_uptime()

    msg = []
    msg.append(f"[{max(mem['status'], disks['status'])}] Resource usage on {h}")
    msg.append(f"Time: {ts}")
    msg.append(f"Host: {h} ({ip})")
    msg.append("")

    msg.append("System:")
    msg.append(f"- Load: {load[0]:.2f} / {load[1]:.2f} / {load[2]:.2f}")
    msg.append(f"- Uptime: {uptime}")
    msg.append("")

    msg.append("Memory:")
    msg.append(f"- RAM: {mem['ram']['percent']:.1f}% used ({fmt_bytes(mem['ram']['used'])} / {fmt_bytes(mem['ram']['total'])}), available: {fmt_bytes(mem['ram']['available'])}")
    if mem["swap"]["total"] > 0:
        msg.append(f"- Swap: {mem['swap']['percent']:.1f}% used ({fmt_bytes(mem['swap']['used'])} / {fmt_bytes(mem['swap']['total'])})")
    msg.append("")

    msg.append("Disks:")
    for m in disks["mounts"]:
        line = f"- {m['device']} on {m['mount']}: {m['percent']:.1f}% used ({fmt_bytes(m['used'])} / {fmt_bytes(m['total'])})"
        if m["inodes_percent"] is not None:
            line += f", inodes: {m['inodes_percent']:.1f}%"
        line += f" [{m['status']}]"
        msg.append(line)
    msg.append("")

    msg.append("Top memory processes:")
    top = get_top_processes_by_memory(5)
    for i, p in enumerate(top, 1):
        msg.append(f"{i}) {p['name']} (pid {p['pid']}, user {p['user']}) – {fmt_bytes(p['rss'])} ({p['percent']:.1f}%)")
    msg.append("")

    return "\n".join(msg)


# ------------------------------------------------------------
# Telegram
# ------------------------------------------------------------

def send_telegram_message(cfg, text):
    token = cfg["telegram"]["bot_token"]
    chat_id = cfg["telegram"]["chat_id"]

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "Markdown"
    }
    encoded = urllib.parse.urlencode(data).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=encoded)
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as e:
        print(f"Erro ao enviar mensagem Telegram: {e}", file=sys.stderr)


# ------------------------------------------------------------
# Main Loop
# ------------------------------------------------------------

def main_loop(cfg, mode, once=False):
    prev_status = {"memory": "OK", "disks": "OK"}
    last_critical_time = {"memory": None, "disks": None}
    cooldown = timedelta(minutes=30)

    while True:
        mem = check_memory(cfg)
        disks = check_disks(cfg)

        current_status_mem = mem["status"]
        current_status_disks = disks["status"]

        # Decide se deve enviar alerta
        send_alert = False

        # Memória
        if current_status_mem != prev_status["memory"]:
            send_alert = True
        elif current_status_mem == "CRITICAL":
            if last_critical_time["memory"] is None or datetime.now() - last_critical_time["memory"] > cooldown:
                send_alert = True

        # Disco
        if current_status_disks != prev_status["disks"]:
            send_alert = True
        elif current_status_disks == "CRITICAL":
            if last_critical_time["disks"] is None or datetime.now() - last_critical_time["disks"] > cooldown:
                send_alert = True

        # Gera mensagem
        if send_alert and (current_status_mem != "OK" or current_status_disks != "OK"):
            if mode == "summary":
                msg = format_summary_message(mem, disks)
            else:
                msg = format_verbose_message(mem, disks)
            send_telegram_message(cfg, msg)

            if current_status_mem == "CRITICAL":
                last_critical_time["memory"] = datetime.now()
            if current_status_disks == "CRITICAL":
                last_critical_time["disks"] = datetime.now()

        prev_status["memory"] = current_status_mem
        prev_status["disks"] = current_status_disks

        if once:
            break

        time.sleep(cfg["interval_seconds"])


# ------------------------------------------------------------
# .entry_point
# ------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Server resource monitor")
    parser.add_argument("--config", type=str, default=None, help="Path to config file")
    parser.add_argument("--mode", type=str, choices=["summary", "verbose"], default=None, help="Alert mode override")
    parser.add_argument("--once", action="store_true", help="Run one check and exit")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = args.config if args.config else os.path.join(script_dir, "server_monitor.json")

    cfg = load_or_create_config(config_path)
    mode = args.mode if args.mode else cfg["alert_mode"]

    main_loop(cfg, mode, args.once)


if __name__ == "__main__":
    main()
