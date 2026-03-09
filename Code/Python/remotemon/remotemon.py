#!/usr/bin/env python3

import json
import os
import re
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import psutil
import requests


CONFIG = {
    # Telegram
    "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
    "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),

    # Runtime
    "interval_seconds": 10,
    "state_file": "/var/tmp/mon_state.json",
    "log_file": "/var/log/server_monitor.log",

    # Thresholds
    "ram_alert_pct": 80,
    "disk_alert_pct": 80,
    "inode_alert_pct": 80,
    "swap_alert_pct": 50,
    "cpu_load_alert_pct": 90,

    # Alert behavior
    "default_alert_cooldown_seconds": 900,
    "recovery_alerts_enabled": True,

    # CPU / RAM process snapshots
    "top_process_limit": 5,
    "cpu_process_sample_seconds": 0.25,

    # Network anomaly detection
    "net_window_seconds": 2 * 60 * 60,
    "net_alert_factor": 3.0,
    "net_alert_sigma_mult": 4.0,
    "net_min_baseline_samples": 60,
    "net_cooldown_seconds": 300,
    "net_connection_summary_limit": 10,

    # Filesystems
    "disk_paths": ["/"],

    # SSH auth failure checks
    "check_failed_ssh": True,
    "auth_log_candidates": ["/var/log/auth.log", "/var/log/secure"],
    "failed_ssh_window_minutes": 10,
    "failed_ssh_alert_count": 10,
    "failed_ssh_log_tail_lines": 5000,

    # systemd
    "check_systemd_failed_units": True,
    "systemd_failed_units_limit": 10,

    # Telegram safety
    "telegram_message_max_chars": 3500,
}


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown-host"


def safe_write_log(path: str, line: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line.rstrip() + "\n")
    except Exception:
        pass


def load_state(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(path: str, state: Dict[str, Any]) -> None:
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, path)


def format_bytes(num: float) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    value = float(num)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{value:.2f} PiB"


def format_bps(bps: float) -> str:
    units = ["B/s", "KiB/s", "MiB/s", "GiB/s", "TiB/s"]
    value = float(bps)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{value:.2f} TiB/s"


def make_alert(
    key: str,
    severity: str,
    category: str,
    summary: str,
    details: Optional[List[str]] = None,
    threshold: Optional[str] = None,
    action: Optional[str] = None,
    status: str = "firing",
) -> Dict[str, Any]:
    return {
        "key": key,
        "severity": severity.upper(),
        "category": category,
        "summary": summary.strip(),
        "details": details or [],
        "threshold": threshold,
        "action": action,
        "status": status,
    }


def render_alert(alert: Dict[str, Any]) -> str:
    prefix = "ALERT" if alert.get("status") == "firing" else "RECOVERY"

    lines = [
        f"{prefix} [{alert['severity']}] {alert['category']}",
        f"Summary: {alert['summary']}",
    ]

    if alert.get("threshold"):
        lines.append(f"Threshold: {alert['threshold']}")

    details = alert.get("details") or []
    if details:
        lines.append("Details:")
        lines.extend(f"  - {item}" for item in details)

    if alert.get("action"):
        lines.append(f"Suggested action: {alert['action']}")

    return "\n".join(lines)


def split_message(text: str, max_chars: int) -> List[str]:
    if len(text) <= max_chars:
        return [text]

    parts = []
    current = []

    for block in text.split("\n\n"):
        candidate = "\n\n".join(current + [block]).strip()
        if current and len(candidate) > max_chars:
            parts.append("\n\n".join(current).strip())
            current = [block]
        else:
            current.append(block)

    if current:
        parts.append("\n\n".join(current).strip())

    if not parts:
        return [text[:max_chars]]

    return parts


def send_telegram(msg: str) -> None:
    token = CONFIG["telegram_bot_token"]
    chat_id = CONFIG["telegram_chat_id"]

    if not token or not chat_id:
        safe_write_log(
            CONFIG["log_file"],
            f"{now_utc_iso()} [WARN] Telegram not configured; message suppressed: {msg[:500]}",
        )
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    for chunk in split_message(msg, CONFIG["telegram_message_max_chars"]):
        try:
            requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": chunk,
                },
                timeout=10,
            )
        except Exception as e:
            safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [ERROR] Telegram send failed: {e}")


def render_telegram_message(host: str, alerts: List[Dict[str, Any]]) -> str:
    counts: Dict[str, int] = {}
    firing_count = 0
    recovery_count = 0

    for a in alerts:
        counts[a["severity"]] = counts.get(a["severity"], 0) + 1
        if a.get("status") == "firing":
            firing_count += 1
        else:
            recovery_count += 1

    sev_summary = ", ".join(f"{sev}={count}" for sev, count in sorted(counts.items()))

    header = [
        "SERVER MONITOR",
        f"Host: {host}",
        f"Time (UTC): {now_utc_iso()}",
        f"Items: total={len(alerts)}, alerts={firing_count}, recoveries={recovery_count}",
    ]
    if sev_summary:
        header.append(f"Severity mix: {sev_summary}")

    body = []
    for idx, alert in enumerate(alerts, 1):
        body.append(f"#{idx}")
        body.append(render_alert(alert))

    return "\n".join(header) + "\n\n" + "\n\n".join(body)


def compute_stats(values: List[float]) -> Tuple[float, float]:
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    var = sum((x - mean) ** 2 for x in values) / (n - 1)
    return mean, var ** 0.5


def trim_old_samples(samples: List[List[float]], window_seconds: int, now_ts: float) -> List[List[float]]:
    cutoff = now_ts - window_seconds
    return [sample for sample in samples if sample[0] >= cutoff]


def snapshot_net_bytes() -> Dict[str, int]:
    c = psutil.net_io_counters()
    return {
        "sent": int(c.bytes_sent),
        "recv": int(c.bytes_recv),
    }


def get_net_rates(prev: Dict[str, int], curr: Dict[str, int], dt: float) -> Tuple[float, float]:
    if dt <= 0:
        return 0.0, 0.0
    up_bps = max(0, (curr["sent"] - prev["sent"])) / dt
    down_bps = max(0, (curr["recv"] - prev["recv"])) / dt
    return up_bps, down_bps


def collect_top_processes(limit: int = 5, sort_by: str = "memory") -> List[str]:
    """
    Returns best-effort formatted process lines.

    sort_by:
      - "memory": sort by RSS descending
      - "cpu": sort by cpu_percent descending
    """
    rows: List[Dict[str, Any]] = []

    try:
        procs = list(
            psutil.process_iter(
                ["pid", "name", "username", "memory_info", "memory_percent", "cpu_percent"]
            )
        )
    except Exception:
        return ["Process snapshot unavailable"]

    if sort_by == "cpu":
        try:
            for p in procs:
                try:
                    p.cpu_percent(interval=None)
                except Exception:
                    pass
            time.sleep(CONFIG["cpu_process_sample_seconds"])
            for p in procs:
                try:
                    p.info["cpu_percent"] = p.cpu_percent(interval=None)
                except Exception:
                    p.info["cpu_percent"] = 0.0
        except Exception:
            pass

    for p in procs:
        try:
            info = p.info
            pid = info.get("pid")
            name = info.get("name") or "unknown"
            user = info.get("username") or "unknown"
            cpu_pct = float(info.get("cpu_percent") or 0.0)
            mem_pct = float(info.get("memory_percent") or 0.0)

            rss = 0
            mem_info = info.get("memory_info")
            if mem_info is not None:
                rss = int(getattr(mem_info, "rss", 0) or 0)

            rows.append(
                {
                    "pid": pid,
                    "name": name,
                    "user": user,
                    "cpu_pct": cpu_pct,
                    "mem_pct": mem_pct,
                    "rss": rss,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception:
            continue

    if sort_by == "cpu":
        rows.sort(key=lambda x: (x["cpu_pct"], x["rss"]), reverse=True)
        top = rows[:limit]
        if not top:
            return ["No CPU-heavy processes visible"]
        return [
            f"{r['name']} [pid={r['pid']}, user={r['user']}] "
            f"cpu={r['cpu_pct']:.1f}% mem={r['mem_pct']:.1f}% rss={format_bytes(r['rss'])}"
            for r in top
        ]

    rows.sort(key=lambda x: (x["rss"], x["mem_pct"]), reverse=True)
    top = rows[:limit]
    if not top:
        return ["No memory-heavy processes visible"]
    return [
        f"{r['name']} [pid={r['pid']}, user={r['user']}] "
        f"mem={r['mem_pct']:.1f}% rss={format_bytes(r['rss'])} cpu={r['cpu_pct']:.1f}%"
        for r in top
    ]


def get_conn_summary_top_ips_and_procs(limit: int = 10) -> Tuple[List[str], List[str]]:
    """
    Best-effort socket/process summary using `ss -tunp`.
    """
    try:
        out = subprocess.check_output(["ss", "-tunp"], stderr=subprocess.DEVNULL, text=True)
    except Exception:
        return (
            ["Connection summary unavailable (missing ss or insufficient permissions)."],
            [],
        )

    ip_counts: Dict[str, int] = {}
    proc_counts: Dict[str, int] = {}

    for line in out.splitlines():
        if ":" not in line:
            continue

        m_ip = re.search(r"\s([0-9a-fA-F\.:]+):\d+\s*$", line)
        if not m_ip:
            m_ip = re.search(r"\s([0-9a-fA-F\.:]+):\d+\s+users:", line)
        if m_ip:
            rip = m_ip.group(1)
            ip_counts[rip] = ip_counts.get(rip, 0) + 1

        m_proc = re.search(r'users:\(\("([^"]+)"', line)
        if m_proc:
            proc_name = m_proc.group(1)
            proc_counts[proc_name] = proc_counts.get(proc_name, 0) + 1

    top_ips = sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    top_procs = sorted(proc_counts.items(), key=lambda x: x[1], reverse=True)[:limit]

    ip_lines: List[str] = []
    proc_lines: List[str] = []

    if top_ips:
        ip_lines.append(
            "Top remote IPs by socket count: "
            + ", ".join(f"{ip}({cnt})" for ip, cnt in top_ips)
        )
    else:
        ip_lines.append("No remote IPs could be parsed from socket output.")

    if top_procs:
        proc_lines.append(
            "Top processes by socket count: "
            + ", ".join(f"{p}({cnt})" for p, cnt in top_procs)
        )
    else:
        proc_lines.append("No process/socket mappings could be parsed.")

    return ip_lines, proc_lines


def should_emit_alert(state: Dict[str, Any], alert_key: str, active: bool, now_ts: float) -> bool:
    alerts_state = state.setdefault("alerts", {})
    slot = alerts_state.setdefault(
        alert_key,
        {
            "active": False,
            "last_sent_ts": 0.0,
        },
    )

    cooldown = CONFIG["default_alert_cooldown_seconds"]

    if active:
        if not slot["active"]:
            slot["active"] = True
            slot["last_sent_ts"] = now_ts
            return True

        if now_ts - float(slot.get("last_sent_ts", 0.0)) >= cooldown:
            slot["last_sent_ts"] = now_ts
            return True

        return False

    if slot["active"]:
        slot["active"] = False
        slot["last_sent_ts"] = now_ts
        return bool(CONFIG["recovery_alerts_enabled"])

    return False


def mark_alert_inactive_without_emit(state: Dict[str, Any], alert_key: str) -> None:
    alerts_state = state.setdefault("alerts", {})
    slot = alerts_state.setdefault(
        alert_key,
        {
            "active": False,
            "last_sent_ts": 0.0,
        },
    )
    slot["active"] = False


def net_anomaly_check(state: Dict[str, Any], up_bps: float, down_bps: float, now_ts: float) -> Optional[Dict[str, Any]]:
    net = state.setdefault("net", {})
    up_samples = net.setdefault("up_samples", [])
    down_samples = net.setdefault("down_samples", [])

    up_samples[:] = trim_old_samples(up_samples, CONFIG["net_window_seconds"], now_ts)
    down_samples[:] = trim_old_samples(down_samples, CONFIG["net_window_seconds"], now_ts)

    up_samples.append([now_ts, float(up_bps)])
    down_samples.append([now_ts, float(down_bps)])

    if len(up_samples) < CONFIG["net_min_baseline_samples"] or len(down_samples) < CONFIG["net_min_baseline_samples"]:
        mark_alert_inactive_without_emit(state, "network_spike")
        return None

    up_vals = [v for _, v in up_samples]
    down_vals = [v for _, v in down_samples]

    up_mean, up_std = compute_stats(up_vals)
    down_mean, down_std = compute_stats(down_vals)

    up_thresh = max(
        up_mean * CONFIG["net_alert_factor"],
        up_mean + CONFIG["net_alert_sigma_mult"] * up_std,
    )
    down_thresh = max(
        down_mean * CONFIG["net_alert_factor"],
        down_mean + CONFIG["net_alert_sigma_mult"] * down_std,
    )

    is_up_spike = up_bps > up_thresh and up_bps > 0
    is_down_spike = down_bps > down_thresh and down_bps > 0
    active = is_up_spike or is_down_spike

    if not should_emit_alert(state, "network_spike", active, now_ts):
        return None

    if active:
        ip_lines, proc_lines = get_conn_summary_top_ips_and_procs(
            limit=CONFIG["net_connection_summary_limit"]
        )

        directions = []
        if is_up_spike:
            directions.append("upload")
        if is_down_spike:
            directions.append("download")

        return make_alert(
            key="network_spike",
            severity="warning",
            category="NETWORK",
            summary=f"Traffic spike detected affecting {', '.join(directions)} traffic.",
            threshold=f"upload > {format_bps(up_thresh)} or download > {format_bps(down_thresh)}",
            details=[
                f"Current upload rate: {format_bps(up_bps)}",
                f"Current download rate: {format_bps(down_bps)}",
                f"Upload baseline: mean {format_bps(up_mean)}, stddev {format_bps(up_std)}",
                f"Download baseline: mean {format_bps(down_mean)}, stddev {format_bps(down_std)}",
                *ip_lines,
                *proc_lines,
            ],
            action="Inspect active connections and verify whether the traffic pattern is expected.",
            status="firing",
        )

    return make_alert(
        key="network_spike",
        severity="info",
        category="NETWORK",
        summary="Traffic returned below anomaly threshold.",
        details=[
            f"Current upload rate: {format_bps(up_bps)}",
            f"Current download rate: {format_bps(down_bps)}",
        ],
        action="No immediate action unless users still report unexpected network activity.",
        status="recovery",
    )


def check_ram(state: Dict[str, Any], now_ts: float) -> Optional[Dict[str, Any]]:
    vm = psutil.virtual_memory()
    active = vm.percent >= CONFIG["ram_alert_pct"]

    if not should_emit_alert(state, "ram_high", active, now_ts):
        return None

    if active:
        top_mem = collect_top_processes(
            limit=CONFIG["top_process_limit"],
            sort_by="memory",
        )
        return make_alert(
            key="ram_high",
            severity="warning",
            category="MEMORY",
            summary=f"RAM usage is above threshold at {vm.percent:.1f}%.",
            threshold=f">= {CONFIG['ram_alert_pct']}%",
            details=[
                f"Used: {format_bytes(vm.used)}",
                f"Available: {format_bytes(vm.available)}",
                f"Total: {format_bytes(vm.total)}",
                "Top memory processes:",
                *top_mem,
            ],
            action="Inspect memory-heavy processes and verify whether the host is under expected workload.",
            status="firing",
        )

    return make_alert(
        key="ram_high",
        severity="info",
        category="MEMORY",
        summary=f"RAM usage recovered to {vm.percent:.1f}%.",
        details=[
            f"Used: {format_bytes(vm.used)}",
            f"Available: {format_bytes(vm.available)}",
            f"Total: {format_bytes(vm.total)}",
        ],
        action="No action required unless memory pressure is recurring.",
        status="recovery",
    )


def check_swap(state: Dict[str, Any], now_ts: float) -> Optional[Dict[str, Any]]:
    sm = psutil.swap_memory()
    if sm.total <= 0:
        mark_alert_inactive_without_emit(state, "swap_high")
        return None

    active = sm.percent >= CONFIG["swap_alert_pct"]

    if not should_emit_alert(state, "swap_high", active, now_ts):
        return None

    if active:
        return make_alert(
            key="swap_high",
            severity="warning",
            category="SWAP",
            summary=f"Swap usage is elevated at {sm.percent:.1f}%.",
            threshold=f">= {CONFIG['swap_alert_pct']}%",
            details=[
                f"Used: {format_bytes(sm.used)}",
                f"Free: {format_bytes(sm.free)}",
                f"Total: {format_bytes(sm.total)}",
            ],
            action="Check for memory pressure, swapping, or runaway processes.",
            status="firing",
        )

    return make_alert(
        key="swap_high",
        severity="info",
        category="SWAP",
        summary=f"Swap usage recovered to {sm.percent:.1f}%.",
        details=[
            f"Used: {format_bytes(sm.used)}",
            f"Free: {format_bytes(sm.free)}",
            f"Total: {format_bytes(sm.total)}",
        ],
        action="No action required unless swap usage rises again.",
        status="recovery",
    )


def check_disks(state: Dict[str, Any], now_ts: float) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []

    for path in CONFIG["disk_paths"]:
        try:
            du = shutil.disk_usage(path)
            used_pct = (du.used / du.total) * 100.0 if du.total else 0.0
            key = f"disk_high:{path}"
            active = used_pct >= CONFIG["disk_alert_pct"]

            if not should_emit_alert(state, key, active, now_ts):
                continue

            if active:
                alerts.append(
                    make_alert(
                        key=key,
                        severity="warning",
                        category="DISK",
                        summary=f"Disk usage on {path} is above threshold at {used_pct:.1f}%.",
                        threshold=f">= {CONFIG['disk_alert_pct']}%",
                        details=[
                            f"Used: {format_bytes(du.used)}",
                            f"Free: {format_bytes(du.free)}",
                            f"Total: {format_bytes(du.total)}",
                        ],
                        action=f"Review large files, logs, backups, caches, and growth under {path}.",
                        status="firing",
                    )
                )
            else:
                alerts.append(
                    make_alert(
                        key=key,
                        severity="info",
                        category="DISK",
                        summary=f"Disk usage on {path} recovered to {used_pct:.1f}%.",
                        details=[
                            f"Used: {format_bytes(du.used)}",
                            f"Free: {format_bytes(du.free)}",
                            f"Total: {format_bytes(du.total)}",
                        ],
                        action="No action required unless filesystem growth resumes.",
                        status="recovery",
                    )
                )
        except Exception:
            continue

    return alerts


def check_inodes(state: Dict[str, Any], now_ts: float) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []

    for path in CONFIG["disk_paths"]:
        try:
            st = os.statvfs(path)
            total = st.f_files
            free = st.f_ffree
            if total <= 0:
                mark_alert_inactive_without_emit(state, f"inodes_high:{path}")
                continue

            used = total - free
            used_pct = (used / total) * 100.0
            key = f"inodes_high:{path}"
            active = used_pct >= CONFIG["inode_alert_pct"]

            if not should_emit_alert(state, key, active, now_ts):
                continue

            if active:
                alerts.append(
                    make_alert(
                        key=key,
                        severity="warning",
                        category="INODES",
                        summary=f"Inode usage on {path} is above threshold at {used_pct:.1f}%.",
                        threshold=f">= {CONFIG['inode_alert_pct']}%",
                        details=[
                            f"Used inodes: {used}",
                            f"Free inodes: {free}",
                            f"Total inodes: {total}",
                        ],
                        action="Look for directories containing very large counts of small files.",
                        status="firing",
                    )
                )
            else:
                alerts.append(
                    make_alert(
                        key=key,
                        severity="info",
                        category="INODES",
                        summary=f"Inode usage on {path} recovered to {used_pct:.1f}%.",
                        details=[
                            f"Used inodes: {used}",
                            f"Free inodes: {free}",
                            f"Total inodes: {total}",
                        ],
                        action="No action required unless inode pressure returns.",
                        status="recovery",
                    )
                )
        except Exception:
            continue

    return alerts


def check_cpu_load(state: Dict[str, Any], now_ts: float) -> Optional[Dict[str, Any]]:
    try:
        load1, _, _ = os.getloadavg()
        cpu_count = psutil.cpu_count(logical=True) or 1
        load_pct = (load1 / cpu_count) * 100.0
    except Exception:
        return None

    active = load_pct >= CONFIG["cpu_load_alert_pct"]

    if not should_emit_alert(state, "cpu_load_high", active, now_ts):
        return None

    if active:
        top_cpu = collect_top_processes(
            limit=CONFIG["top_process_limit"],
            sort_by="cpu",
        )
        return make_alert(
            key="cpu_load_high",
            severity="warning",
            category="CPU",
            summary=f"1-minute CPU load is elevated at approximately {load_pct:.1f}% of logical capacity.",
            threshold=f">= {CONFIG['cpu_load_alert_pct']}%",
            details=[
                f"1-minute load average: {load1:.2f}",
                f"Logical CPU count: {cpu_count}",
                "Top CPU processes:",
                *top_cpu,
            ],
            action="Inspect CPU-intensive processes and verify whether sustained load is expected.",
            status="firing",
        )

    return make_alert(
        key="cpu_load_high",
        severity="info",
        category="CPU",
        summary=f"1-minute CPU load recovered to approximately {load_pct:.1f}% of logical capacity.",
        details=[
            f"1-minute load average: {load1:.2f}",
            f"Logical CPU count: {cpu_count}",
        ],
        action="No action required unless CPU pressure returns.",
        status="recovery",
    )


def check_reboot(state: Dict[str, Any], now_ts: float) -> Optional[Dict[str, Any]]:
    boot_ts = psutil.boot_time()
    last_boot = state.get("last_boot_time")
    state["last_boot_time"] = boot_ts

    if last_boot is None:
        mark_alert_inactive_without_emit(state, "system_reboot")
        return None

    active = float(last_boot) != float(boot_ts)

    if not should_emit_alert(state, "system_reboot", active, now_ts):
        return None

    if active:
        boot_utc = datetime.fromtimestamp(boot_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return make_alert(
            key="system_reboot",
            severity="critical",
            category="SYSTEM",
            summary="System reboot detected.",
            details=[
                f"New boot time (UTC): {boot_utc}",
            ],
            action="Verify whether the reboot was expected and review startup and service health.",
            status="firing",
        )

    return None


def check_failed_ssh(state: Dict[str, Any], now_ts: float) -> Optional[Dict[str, Any]]:
    if not CONFIG["check_failed_ssh"]:
        mark_alert_inactive_without_emit(state, "failed_ssh")
        return None

    log_path = None
    for candidate in CONFIG["auth_log_candidates"]:
        if os.path.exists(candidate):
            log_path = candidate
            break

    if not log_path:
        mark_alert_inactive_without_emit(state, "failed_ssh")
        return None

    cutoff = time.time() - (CONFIG["failed_ssh_window_minutes"] * 60)
    count = 0
    ip_counts: Dict[str, int] = {}

    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-CONFIG["failed_ssh_log_tail_lines"] :]
    except Exception:
        return None

    try:
        if os.path.getmtime(log_path) < cutoff:
            active = False
            if not should_emit_alert(state, "failed_ssh", active, now_ts):
                return None
            return make_alert(
                key="failed_ssh",
                severity="info",
                category="AUTH",
                summary="SSH authentication failure activity returned below alert threshold.",
                details=[f"Log source: {log_path}"],
                action="No action required unless failed logins resume.",
                status="recovery",
            )
    except Exception:
        pass

    for line in lines:
        if "Failed password" not in line:
            continue
        m = re.search(r"from\s+([0-9a-fA-F\.:]+)\s+port", line)
        if m:
            ip = m.group(1)
            ip_counts[ip] = ip_counts.get(ip, 0) + 1
        count += 1

    active = count >= CONFIG["failed_ssh_alert_count"]

    if not should_emit_alert(state, "failed_ssh", active, now_ts):
        return None

    if active:
        top = sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        top_s = ", ".join(f"{ip}({cnt})" for ip, cnt in top) if top else "none parsed"

        return make_alert(
            key="failed_ssh",
            severity="warning",
            category="AUTH",
            summary="Repeated SSH authentication failures detected; possible brute-force activity.",
            threshold=(
                f">= {CONFIG['failed_ssh_alert_count']} failed password events in "
                f"~{CONFIG['failed_ssh_window_minutes']} minutes"
            ),
            details=[
                f"Approximate failed events counted: {count}",
                f"Top source IPs: {top_s}",
                f"Log source: {log_path}",
            ],
            action="Review SSH exposure, block abusive sources, and confirm whether these attempts are expected.",
            status="firing",
        )

    return make_alert(
        key="failed_ssh",
        severity="info",
        category="AUTH",
        summary="SSH authentication failure activity returned below alert threshold.",
        details=[
            f"Approximate failed events counted: {count}",
            f"Log source: {log_path}",
        ],
        action="No action required unless failed logins resume.",
        status="recovery",
    )


def check_systemd_failed_units(state: Dict[str, Any], now_ts: float) -> Optional[Dict[str, Any]]:
    if not CONFIG["check_systemd_failed_units"]:
        mark_alert_inactive_without_emit(state, "systemd_failed_units")
        return None

    try:
        out = subprocess.check_output(
            ["systemctl", "--failed", "--no-pager", "--plain"],
            text=True,
        )
    except Exception:
        return None

    no_failed = "0 loaded units listed." in out or "0 loaded units listed" in out
    failed_lines = [
        line.strip()
        for line in out.splitlines()
        if ".service" in line or ".timer" in line or ".socket" in line
    ]

    active = (not no_failed) and bool(failed_lines)

    if not should_emit_alert(state, "systemd_failed_units", active, now_ts):
        return None

    if active:
        trimmed = failed_lines[: CONFIG["systemd_failed_units_limit"]]
        return make_alert(
            key="systemd_failed_units",
            severity="warning",
            category="SYSTEMD",
            summary="One or more systemd units are in failed state.",
            details=trimmed,
            action="Run 'systemctl --failed' and inspect recent journal logs for the affected units.",
            status="firing",
        )

    return make_alert(
        key="systemd_failed_units",
        severity="info",
        category="SYSTEMD",
        summary="No failed systemd units remain.",
        action="No action required unless services begin failing again.",
        status="recovery",
    )


def main() -> None:
    host = hostname()
    state = load_state(CONFIG["state_file"])

    prev_net = state.get("prev_net_bytes")
    prev_ts = state.get("prev_net_ts")

    if not prev_net or not prev_ts:
        prev_net = snapshot_net_bytes()
        prev_ts = time.time()
        state["prev_net_bytes"] = prev_net
        state["prev_net_ts"] = prev_ts
        save_state(CONFIG["state_file"], state)

    safe_write_log(
        CONFIG["log_file"],
        f"{now_utc_iso()} [INFO] Monitor started on host={host} interval={CONFIG['interval_seconds']}s",
    )

    while True:
        try:
            time.sleep(CONFIG["interval_seconds"])
            now_ts = time.time()
            alerts: List[Dict[str, Any]] = []

            for checker in (
                lambda: check_reboot(state, now_ts),
                lambda: check_ram(state, now_ts),
                lambda: check_swap(state, now_ts),
                lambda: check_cpu_load(state, now_ts),
                lambda: check_failed_ssh(state, now_ts),
                lambda: check_systemd_failed_units(state, now_ts),
            ):
                alert = checker()
                if alert:
                    alerts.append(alert)

            alerts.extend(check_disks(state, now_ts))
            alerts.extend(check_inodes(state, now_ts))

            curr_net = snapshot_net_bytes()
            dt = now_ts - float(prev_ts)
            up_bps, down_bps = get_net_rates(prev_net, curr_net, dt)

            net_alert = net_anomaly_check(state, up_bps, down_bps, now_ts)
            if net_alert:
                alerts.append(net_alert)

            state["prev_net_bytes"] = curr_net
            state["prev_net_ts"] = now_ts

            if alerts:
                msg = render_telegram_message(host, alerts)
                send_telegram(msg)
                safe_write_log(
                    CONFIG["log_file"],
                    f"{now_utc_iso()} [ALERT] Sent {len(alerts)} item(s).",
                )

                for alert in alerts:
                    safe_write_log(
                        CONFIG["log_file"],
                        f"{now_utc_iso()} [{alert['status'].upper()}] "
                        f"{alert['category']} {alert['summary']}",
                    )

            save_state(CONFIG["state_file"], state)

        except KeyboardInterrupt:
            safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [INFO] Monitor stopped by user.")
            break
        except Exception as e:
            safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [ERROR] Loop error: {e}")


if __name__ == "__main__":
    main()
