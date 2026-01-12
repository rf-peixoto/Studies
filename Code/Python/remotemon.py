#!/usr/bin/env python3

# Setup TG env vars:
#export TELEGRAM_BOT_TOKEN="123456:ABCDEF..."
#export TELEGRAM_CHAT_ID="123456789"

# Normal run:
#sudo -E python3 remotemon.py

import os
import re
import json
import time
import shutil
import socket
import subprocess
from datetime import datetime, timezone

import psutil
import requests


# =========================
# Configuration (edit me)
# =========================

CONFIG = {
    # Telegram
    "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
    "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),

    # General loop
    "interval_seconds": 10,                 # sampling interval
    "state_file": "/var/tmp/mon_state.json",
    "log_file": "/var/log/server_monitor.log",

    # Thresholds
    "ram_alert_pct": 80,
    "disk_alert_pct": 80,
    "inode_alert_pct": 80,
    "swap_alert_pct": 50,

    # CPU load (1-min loadavg as % of logical CPUs)
    "cpu_load_alert_pct": 90,

    # Network anomaly detection
    # "normal" baseline = last 2 hours of samples (rolling).
    # Alert if current rate > max(baseline_mean * factor, baseline_mean + sigma_mult*stddev)
    "net_window_seconds": 2 * 60 * 60,      # 2 hours
    "net_alert_factor": 3.0,                # spike factor vs mean
    "net_alert_sigma_mult": 4.0,            # or N standard deviations
    "net_min_baseline_samples": 60,         # require at least N samples before judging
    "net_cooldown_seconds": 300,            # avoid alert spam for repeated spikes

    # Disk targets
    "disk_paths": ["/"],

    # Optional: check for failed ssh logins by scanning auth logs (best-effort)
    "check_failed_ssh": True,
    "auth_log_candidates": ["/var/log/auth.log", "/var/log/secure"],
    "failed_ssh_window_minutes": 10,
    "failed_ssh_alert_count": 10,

    # Optional: systemd failures (best-effort; requires systemd)
    "check_systemd_failed_units": True,
}

# =========================
# Utilities
# =========================

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def safe_write_log(path: str, line: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line.rstrip() + "\n")
    except Exception:
        # If log path is not writable, fail silently (monitoring should continue)
        pass

def load_state(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(path: str, state: dict) -> None:
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, path)

def send_telegram(msg: str) -> None:
    token = CONFIG["telegram_bot_token"]
    chat_id = CONFIG["telegram_chat_id"]
    if not token or not chat_id:
        safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [WARN] Telegram not configured; message suppressed: {msg}")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": msg}, timeout=10)
    except Exception as e:
        safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [ERROR] Telegram send failed: {e}")

def hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown-host"


# =========================
# Network baseline + anomaly
# =========================

def compute_stats(values):
    # simple mean/stddev; values is a list of floats
    n = len(values)
    if n == 0:
        return (0.0, 0.0)
    mean = sum(values) / n
    if n < 2:
        return (mean, 0.0)
    var = sum((x - mean) ** 2 for x in values) / (n - 1)
    return (mean, var ** 0.5)

def trim_old_samples(samples, window_seconds: int, now_ts: float):
    # samples list of [timestamp, value]
    cutoff = now_ts - window_seconds
    return [s for s in samples if s[0] >= cutoff]

def get_net_rates(prev, curr, dt):
    # prev/curr are dict like {"sent":..., "recv":...}
    if dt <= 0:
        return 0.0, 0.0
    up_bps = max(0, (curr["sent"] - prev["sent"])) / dt
    down_bps = max(0, (curr["recv"] - prev["recv"])) / dt
    return up_bps, down_bps

def snapshot_net_bytes():
    c = psutil.net_io_counters()
    return {"sent": int(c.bytes_sent), "recv": int(c.bytes_recv)}

def format_bps(bps: float) -> str:
    # bytes/sec -> human
    units = ["B/s", "KB/s", "MB/s", "GB/s", "TB/s"]
    v = float(bps)
    i = 0
    while v >= 1024.0 and i < len(units) - 1:
        v /= 1024.0
        i += 1
    return f"{v:.2f} {units[i]}"

def get_conn_summary_top_ips_and_procs(limit=10) -> str:
    """
    Best-effort: use `ss -tunp` to list TCP/UDP sockets with process info.
    This often requires root for full process mapping.
    """
    try:
        out = subprocess.check_output(["ss", "-tunp"], stderr=subprocess.DEVNULL, text=True)
    except Exception:
        return "Connection summary unavailable (missing ss or insufficient permissions)."

    # Parse remote IPs from lines like:
    # ESTAB 0 0 192.168.1.10:22 1.2.3.4:54321 users:(("sshd",pid=123,fd=3))
    ip_counts = {}
    proc_counts = {}

    for line in out.splitlines():
        if ":" not in line:
            continue
        # remote endpoint is typically column near the end; use regex for IPv4/IPv6-ish
        m_ip = re.search(r"\s([0-9a-fA-F\.:]+):\d+\s*$", line)
        if not m_ip:
            # sometimes there is extra "users:" text at end; try looser
            m_ip = re.search(r"\s([0-9a-fA-F\.:]+):\d+\s+users:", line)
        if m_ip:
            rip = m_ip.group(1)
            ip_counts[rip] = ip_counts.get(rip, 0) + 1

        m_proc = re.search(r'users:\(\("([^"]+)"', line)
        if m_proc:
            p = m_proc.group(1)
            proc_counts[p] = proc_counts.get(p, 0) + 1

    top_ips = sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    top_procs = sorted(proc_counts.items(), key=lambda x: x[1], reverse=True)[:limit]

    lines = []
    if top_ips:
        lines.append("Top remote IPs (by socket count): " + ", ".join(f"{ip}({cnt})" for ip, cnt in top_ips))
    else:
        lines.append("Top remote IPs: none parsed")

    if top_procs:
        lines.append("Top processes (by socket count): " + ", ".join(f"{p}({cnt})" for p, cnt in top_procs))
    else:
        lines.append("Top processes: none parsed")

    return "\n".join(lines)

def net_anomaly_check(state: dict, up_bps: float, down_bps: float, now_ts: float) -> (bool, str):
    net = state.setdefault("net", {})
    up_samples = net.setdefault("up_samples", [])
    down_samples = net.setdefault("down_samples", [])

    # Trim + append latest sample
    up_samples[:] = trim_old_samples(up_samples, CONFIG["net_window_seconds"], now_ts)
    down_samples[:] = trim_old_samples(down_samples, CONFIG["net_window_seconds"], now_ts)

    up_samples.append([now_ts, float(up_bps)])
    down_samples.append([now_ts, float(down_bps)])

    # Ensure minimal baseline samples
    if len(up_samples) < CONFIG["net_min_baseline_samples"] or len(down_samples) < CONFIG["net_min_baseline_samples"]:
        return (False, "Baseline building (insufficient samples).")

    up_vals = [v for _, v in up_samples]
    down_vals = [v for _, v in down_samples]

    up_mean, up_std = compute_stats(up_vals)
    down_mean, down_std = compute_stats(down_vals)

    # Avoid super-low mean producing constant triggers
    up_thresh = max(up_mean * CONFIG["net_alert_factor"], up_mean + CONFIG["net_alert_sigma_mult"] * up_std)
    down_thresh = max(down_mean * CONFIG["net_alert_factor"], down_mean + CONFIG["net_alert_sigma_mult"] * down_std)

    is_up_spike = up_bps > up_thresh and up_bps > 0
    is_down_spike = down_bps > down_thresh and down_bps > 0

    cooldown_until = net.get("cooldown_until", 0)
    if now_ts < cooldown_until:
        return (False, "In cooldown window.")

    if is_up_spike or is_down_spike:
        net["cooldown_until"] = now_ts + CONFIG["net_cooldown_seconds"]
        msg = (
            f"Network spike detected.\n"
            f"Current: up {format_bps(up_bps)} / down {format_bps(down_bps)}\n"
            f"Baseline(mean±std): up {format_bps(up_mean)} ± {format_bps(up_std)}; "
            f"down {format_bps(down_mean)} ± {format_bps(down_std)}\n"
            f"Thresholds: up>{format_bps(up_thresh)}, down>{format_bps(down_thresh)}"
        )
        return (True, msg)

    return (False, "No anomaly.")


# =========================
# System checks
# =========================

def check_ram() -> (bool, str):
    vm = psutil.virtual_memory()
    used_pct = vm.percent
    if used_pct >= CONFIG["ram_alert_pct"]:
        return (True, f"RAM usage high: {used_pct:.1f}% (used {vm.used/1024**3:.2f} GiB / total {vm.total/1024**3:.2f} GiB)")
    return (False, "")

def check_swap() -> (bool, str):
    sm = psutil.swap_memory()
    if sm.total <= 0:
        return (False, "")
    if sm.percent >= CONFIG["swap_alert_pct"]:
        return (True, f"Swap usage high: {sm.percent:.1f}% (used {sm.used/1024**3:.2f} GiB / total {sm.total/1024**3:.2f} GiB)")
    return (False, "")

def check_disks() -> list:
    alerts = []
    for p in CONFIG["disk_paths"]:
        try:
            du = shutil.disk_usage(p)
            used_pct = (du.used / du.total) * 100.0 if du.total else 0.0
            if used_pct >= CONFIG["disk_alert_pct"]:
                alerts.append(f"Disk usage high on {p}: {used_pct:.1f}% (used {du.used/1024**3:.2f} GiB / total {du.total/1024**3:.2f} GiB)")
        except Exception:
            continue
    return alerts

def check_inodes() -> list:
    alerts = []
    for p in CONFIG["disk_paths"]:
        try:
            st = os.statvfs(p)
            total = st.f_files
            free = st.f_ffree
            if total <= 0:
                continue
            used = total - free
            used_pct = (used / total) * 100.0
            if used_pct >= CONFIG["inode_alert_pct"]:
                alerts.append(f"Inode usage high on {p}: {used_pct:.1f}% (used {used} / total {total})")
        except Exception:
            continue
    return alerts

def check_cpu_load() -> (bool, str):
    try:
        load1, _, _ = os.getloadavg()
        cpu_count = psutil.cpu_count(logical=True) or 1
        load_pct = (load1 / cpu_count) * 100.0
        if load_pct >= CONFIG["cpu_load_alert_pct"]:
            return (True, f"CPU load high (1-min): {load1:.2f} (~{load_pct:.1f}% of {cpu_count} logical CPUs)")
    except Exception:
        pass
    return (False, "")

def check_reboot(state: dict) -> (bool, str):
    boot_ts = psutil.boot_time()
    last_boot = state.get("last_boot_time")
    state["last_boot_time"] = boot_ts
    if last_boot is None:
        return (False, "")
    if float(last_boot) != float(boot_ts):
        bt = datetime.fromtimestamp(boot_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return (True, f"Reboot detected. New boot time (UTC): {bt}")
    return (False, "")

def check_failed_ssh() -> (bool, str):
    if not CONFIG["check_failed_ssh"]:
        return (False, "")

    log_path = None
    for c in CONFIG["auth_log_candidates"]:
        if os.path.exists(c):
            log_path = c
            break
    if not log_path:
        return (False, "")

    # Best-effort, not perfect: look for "Failed password" lines in last N minutes
    window_sec = CONFIG["failed_ssh_window_minutes"] * 60
    cutoff = time.time() - window_sec
    count = 0
    ip_counts = {}

    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-5000:]  # avoid scanning huge logs
    except Exception:
        return (False, "")

    # syslog timestamps do not include year; we approximate by trusting file recency
    # and only counting lines if file mtime is recent enough.
    try:
        if os.path.getmtime(log_path) < cutoff:
            return (False, "")
    except Exception:
        pass

    for line in lines:
        if "Failed password" not in line:
            continue
        # Extract IP
        m = re.search(r"from\s+([0-9a-fA-F\.:]+)\s+port", line)
        if m:
            ip = m.group(1)
            ip_counts[ip] = ip_counts.get(ip, 0) + 1
        count += 1

    if count >= CONFIG["failed_ssh_alert_count"]:
        top = sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        top_s = ", ".join(f"{ip}({cnt})" for ip, cnt in top) if top else "n/a"
        return (True, f"Possible brute force: {count} 'Failed password' events in ~last {CONFIG['failed_ssh_window_minutes']} minutes. Top IPs: {top_s} (log: {log_path})")

    return (False, "")

def check_systemd_failed_units() -> (bool, str):
    if not CONFIG["check_systemd_failed_units"]:
        return (False, "")
    try:
        out = subprocess.check_output(["systemctl", "--failed", "--no-pager", "--plain"], text=True)
    except Exception:
        return (False, "")
    # If there are failed units, systemctl output typically includes them; heuristic:
    if "0 loaded units listed." in out or "0 loaded units listed" in out:
        return (False, "")
    # Another heuristic: if output contains ".service" lines
    if ".service" in out or ".timer" in out or ".socket" in out:
        # trim to avoid huge Telegram messages
        msg = "\n".join(out.splitlines()[:30])
        return (True, f"systemd has failed units:\n{msg}")
    return (False, "")


# =========================
# Main loop
# =========================

def main():
    h = hostname()
    state = load_state(CONFIG["state_file"])
    prev_net = state.get("prev_net_bytes")
    prev_ts = state.get("prev_net_ts")

    if not prev_net or not prev_ts:
        # initialize
        prev_net = snapshot_net_bytes()
        prev_ts = time.time()
        state["prev_net_bytes"] = prev_net
        state["prev_net_ts"] = prev_ts
        save_state(CONFIG["state_file"], state)

    safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [INFO] Monitor started on host={h} interval={CONFIG['interval_seconds']}s")

    while True:
        try:
            time.sleep(CONFIG["interval_seconds"])
            now_ts = time.time()

            alerts = []

            # Reboot detection
            rb, rb_msg = check_reboot(state)
            if rb:
                alerts.append(rb_msg)

            # RAM / swap / CPU
            ram_hit, ram_msg = check_ram()
            if ram_hit:
                alerts.append(ram_msg)

            swap_hit, swap_msg = check_swap()
            if swap_hit:
                alerts.append(swap_msg)

            cpu_hit, cpu_msg = check_cpu_load()
            if cpu_hit:
                alerts.append(cpu_msg)

            # Disk usage / inodes
            alerts.extend(check_disks())
            alerts.extend(check_inodes())

            # Failed SSH
            ssh_hit, ssh_msg = check_failed_ssh()
            if ssh_hit:
                alerts.append(ssh_msg)

            # systemd failed units
            sd_hit, sd_msg = check_systemd_failed_units()
            if sd_hit:
                alerts.append(sd_msg)

            # Network sampling
            curr_net = snapshot_net_bytes()
            dt = now_ts - float(prev_ts)
            up_bps, down_bps = get_net_rates(prev_net, curr_net, dt)

            net_spike, net_msg = net_anomaly_check(state, up_bps, down_bps, now_ts)
            if net_spike:
                # Add connection summary for "IPs + processes flagged"
                conn_summary = get_conn_summary_top_ips_and_procs(limit=10)
                net_full = net_msg + "\n\n" + conn_summary
                alerts.append(net_full)

                # Also log locally (summarized)
                safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [ALERT] {net_msg.replace(chr(10), ' | ')}")
                safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [INFO] {conn_summary.replace(chr(10), ' | ')}")

            # Update prev net counters in state
            state["prev_net_bytes"] = curr_net
            state["prev_net_ts"] = now_ts

            # Send Telegram if any alerts
            if alerts:
                msg = f"[{h}] ALERT @ {now_utc_iso()}\n\n" + "\n\n".join(f"- {a}" for a in alerts)
                send_telegram(msg)

                # Also log
                safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [ALERT] Sent {len(alerts)} alert(s).")

            save_state(CONFIG["state_file"], state)

        except KeyboardInterrupt:
            safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [INFO] Monitor stopped by user.")
            break
        except Exception as e:
            safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [ERROR] Loop error: {e}")
            # continue running


if __name__ == "__main__":
    main()
