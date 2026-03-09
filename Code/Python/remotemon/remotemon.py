#!/usr/bin/env python3

import json
import os
import re
import shutil
import socket
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import psutil
import requests


CONFIG = {
    # Telegram
    "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
    "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),

    # Runtime
    "interval_seconds": 15,
    "state_file": "/var/tmp/remotemon_state.json",
    "log_file": "/var/log/remotemon.log",
    "watchdog_file": "/var/tmp/remotemon.watchdog",
    "snapshot_dir": "/var/tmp/remotemon-snapshots",
    "snapshot_retention_days": 7,

    # Thresholds
    "ram_alert_pct": 85,
    "disk_alert_pct": 85,
    "inode_alert_pct": 85,
    "swap_alert_pct": 50,
    "cpu_load_alert_pct": 90,
    "journal_burst_error_count": 20,
    "cpu_process_sample_seconds": 0.30,
    "top_process_limit": 5,

    # Alert behavior
    "default_alert_cooldown_seconds": 900,
    "critical_alert_cooldown_seconds": 300,
    "recovery_alerts_enabled": True,
    "escalate_after_repeats": 3,
    "quiet_hours_enabled": False,
    "quiet_hours_start": 23,
    "quiet_hours_end": 7,
    "quiet_hours_min_severity": "CRITICAL",
    "boot_suppression_seconds": 180,
    "maintenance_until_epoch": 0,
    "heartbeat_hours": 6,
    "startup_message": True,

    # Digest / low-value events
    "digest_for_low_severity": True,
    "digest_flush_seconds": 1800,

    # Filesystems
    "disk_paths": ["/"],
    "triage_dir_depth": 2,
    "triage_top_n": 5,

    # Network anomaly detection
    "net_window_seconds": 2 * 60 * 60,
    "net_alert_factor": 3.0,
    "net_alert_sigma_mult": 4.0,
    "net_min_baseline_samples": 60,
    "net_connection_summary_limit": 10,
    "new_outbound_connection_cooldown_seconds": 1800,
    "new_listen_port_cooldown_seconds": 1800,

    # Authentication / sudo
    "check_failed_ssh": True,
    "auth_log_candidates": ["/var/log/auth.log", "/var/log/secure"],
    "failed_ssh_window_minutes": 10,
    "failed_ssh_alert_count": 10,
    "failed_ssh_log_tail_lines": 6000,
    "alert_new_ssh_source": True,
    "alert_root_ssh_login": True,
    "sudo_watch_users": [],

    # Security telemetry
    "watch_tmp_exec": True,
    "watch_deleted_running_exec": True,
    "watch_suspicious_chains": True,
    "watch_paths_integrity": [
        "/etc/passwd",
        "/etc/shadow",
        "/etc/ssh/sshd_config",
        "/root/.ssh/authorized_keys",
    ],

    # systemd / service-aware monitoring
    "check_systemd_failed_units": True,
    "systemd_failed_units_limit": 10,
    "required_services": [
        # Example:
        # {
        #   "name": "nginx",
        #   "unit": "nginx.service",
        #   "ports": [80, 443],
        #   "tcp_checks": [{"host": "127.0.0.1", "port": 80}],
        #   "http_checks": ["http://127.0.0.1/healthz"],
        #   "depends_on_ports": [8080],
        # }
    ],

    # External command timeouts
    "command_timeout_seconds": 8,

    # Telegram safety
    "telegram_message_max_chars": 3500,
}

SEVERITY_ORDER = {"INFO": 0, "WARNING": 1, "HIGH": 2, "CRITICAL": 3}


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown-host"


def utc_from_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def safe_write_log(path: str, line: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line.rstrip() + "\n")
    except Exception:
        pass


def run_cmd(cmd: List[str], timeout: Optional[int] = None) -> Tuple[int, str, str]:
    timeout = timeout or CONFIG["command_timeout_seconds"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


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


def split_message(text: str, max_chars: int) -> List[str]:
    if len(text) <= max_chars:
        return [text]
    parts: List[str] = []
    current: List[str] = []
    for block in text.split("\n\n"):
        candidate = "\n\n".join(current + [block]).strip()
        if current and len(candidate) > max_chars:
            parts.append("\n\n".join(current).strip())
            current = [block]
        else:
            current.append(block)
    if current:
        parts.append("\n\n".join(current).strip())
    return parts or [text[:max_chars]]


def send_telegram(msg: str) -> bool:
    token = CONFIG["telegram_bot_token"]
    chat_id = CONFIG["telegram_chat_id"]
    if not token or not chat_id:
        safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [WARN] Telegram not configured; suppressed")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    ok = True
    for chunk in split_message(msg, CONFIG["telegram_message_max_chars"]):
        try:
            resp = requests.post(url, json={"chat_id": chat_id, "text": chunk}, timeout=10)
            if not resp.ok:
                ok = False
                safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [ERROR] Telegram send failed http={resp.status_code} body={resp.text[:300]}")
        except Exception as e:
            ok = False
            safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [ERROR] Telegram send failed: {e}")
    return ok


def make_alert(
    key: str,
    severity: str,
    category: str,
    summary: str,
    details: Optional[List[str]] = None,
    threshold: Optional[str] = None,
    action: Optional[str] = None,
    status: str = "firing",
    snapshot_path: Optional[str] = None,
    digest_eligible: Optional[bool] = None,
) -> Dict[str, Any]:
    sev = severity.upper()
    return {
        "key": key,
        "severity": sev,
        "category": category,
        "summary": summary.strip(),
        "details": details or [],
        "threshold": threshold,
        "action": action,
        "status": status,
        "snapshot_path": snapshot_path,
        "digest_eligible": digest_eligible if digest_eligible is not None else sev in {"INFO", "WARNING"},
    }


def render_alert(alert: Dict[str, Any]) -> str:
    prefix = {
        "firing": "ALERT",
        "still_firing": "STILL FIRING",
        "escalated": "ESCALATED",
        "recovery": "RECOVERY",
    }.get(alert.get("status", "firing"), "ALERT")
    lines = [
        f"{prefix} [{alert['severity']}] {alert['category']}",
        f"Summary: {alert['summary']}",
    ]
    if alert.get("threshold"):
        lines.append(f"Threshold: {alert['threshold']}")
    details = alert.get("details") or []
    if details:
        lines.append("Details:")
        lines.extend(f"  - {d}" for d in details)
    if alert.get("snapshot_path"):
        lines.append(f"Snapshot: {alert['snapshot_path']}")
    if alert.get("action"):
        lines.append(f"Suggested action: {alert['action']}")
    return "\n".join(lines)


def render_telegram_message(host: str, alerts: List[Dict[str, Any]]) -> str:
    counts: Dict[str, int] = {}
    status_counts: Dict[str, int] = {}
    for a in alerts:
        counts[a["severity"]] = counts.get(a["severity"], 0) + 1
        st = a.get("status", "firing")
        status_counts[st] = status_counts.get(st, 0) + 1
    sev_summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x: SEVERITY_ORDER.get(x[0], 99)))
    st_summary = ", ".join(f"{k}={v}" for k, v in sorted(status_counts.items()))
    header = [
        "REMOTEMON",
        f"Host: {host}",
        f"Time (UTC): {now_utc_iso()}",
        f"Items: {len(alerts)}",
    ]
    if sev_summary:
        header.append(f"Severity mix: {sev_summary}")
    if st_summary:
        header.append(f"State mix: {st_summary}")
    body: List[str] = []
    for idx, alert in enumerate(alerts, 1):
        body.append(f"#{idx}")
        body.append(render_alert(alert))
    return "\n".join(header) + "\n\n" + "\n\n".join(body)


def severity_at_least(a: str, b: str) -> bool:
    return SEVERITY_ORDER.get(a.upper(), 0) >= SEVERITY_ORDER.get(b.upper(), 0)


def in_quiet_hours() -> bool:
    if not CONFIG["quiet_hours_enabled"]:
        return False
    now_hour = datetime.now().hour
    start = int(CONFIG["quiet_hours_start"])
    end = int(CONFIG["quiet_hours_end"])
    if start == end:
        return True
    if start < end:
        return start <= now_hour < end
    return now_hour >= start or now_hour < end


def under_boot_suppression() -> bool:
    return (time.time() - psutil.boot_time()) < CONFIG["boot_suppression_seconds"]


def under_maintenance() -> bool:
    return time.time() < float(CONFIG.get("maintenance_until_epoch", 0) or 0)


def should_suppress_delivery(alert: Dict[str, Any]) -> bool:
    if under_maintenance() and alert.get("severity") != "CRITICAL":
        return True
    if under_boot_suppression() and alert.get("severity") != "CRITICAL":
        return True
    if in_quiet_hours() and not severity_at_least(alert["severity"], CONFIG["quiet_hours_min_severity"]):
        return True
    return False


def get_alert_cooldown(alert: Dict[str, Any]) -> int:
    if alert["severity"] == "CRITICAL":
        return int(CONFIG["critical_alert_cooldown_seconds"])
    return int(CONFIG["default_alert_cooldown_seconds"])


def alert_transition(state: Dict[str, Any], alert: Dict[str, Any], active: bool, now_ts: float) -> Optional[Dict[str, Any]]:
    alerts_state = state.setdefault("alerts", {})
    slot = alerts_state.setdefault(alert["key"], {
        "active": False,
        "first_fired_ts": 0.0,
        "last_seen_ts": 0.0,
        "last_sent_ts": 0.0,
        "repeat_count": 0,
        "state": "inactive",
    })
    cooldown = get_alert_cooldown(alert)

    if active:
        slot["last_seen_ts"] = now_ts
        if not slot["active"]:
            slot["active"] = True
            slot["first_fired_ts"] = now_ts
            slot["repeat_count"] = 1
            slot["state"] = "firing"
            out = dict(alert)
            out["status"] = "firing"
            return out

        slot["repeat_count"] = int(slot.get("repeat_count", 0)) + 1
        next_state = "escalated" if slot["repeat_count"] >= int(CONFIG["escalate_after_repeats"]) else "still_firing"
        if now_ts - float(slot.get("last_sent_ts", 0.0)) >= cooldown:
            slot["state"] = next_state
            out = dict(alert)
            out["status"] = next_state
            return out
        return None

    if slot["active"]:
        slot["active"] = False
        slot["state"] = "inactive"
        if CONFIG["recovery_alerts_enabled"]:
            out = dict(alert)
            out["status"] = "recovery"
            return out
    return None


def finalize_sent_alert_state(state: Dict[str, Any], alert: Dict[str, Any], now_ts: float) -> None:
    slot = state.setdefault("alerts", {}).setdefault(alert["key"], {})
    slot["last_sent_ts"] = now_ts
    slot["last_status"] = alert.get("status")


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
    return {"sent": int(c.bytes_sent), "recv": int(c.bytes_recv)}


def get_net_rates(prev: Dict[str, int], curr: Dict[str, int], dt: float) -> Tuple[float, float]:
    if dt <= 0:
        return 0.0, 0.0
    return max(0.0, curr["sent"] - prev["sent"]) / dt, max(0.0, curr["recv"] - prev["recv"]) / dt


def process_name(pid: int) -> str:
    try:
        return psutil.Process(pid).name()
    except Exception:
        return "unknown"


def get_process_snapshot(pid: int) -> Dict[str, Any]:
    p = psutil.Process(pid)
    info: Dict[str, Any] = {
        "pid": pid,
        "name": "unknown",
        "user": "unknown",
        "ppid": None,
        "parent_name": "unknown",
        "cpu_pct": 0.0,
        "rss": 0,
        "threads": 0,
        "open_files": 0,
        "create_time": None,
        "age_seconds": None,
        "exe": None,
        "cmdline": None,
        "connections": [],
        "children": [],
    }
    with p.oneshot():
        info["name"] = p.name()
        info["user"] = p.username()
        info["ppid"] = p.ppid()
        info["parent_name"] = process_name(p.ppid()) if p.ppid() else "none"
        info["cpu_pct"] = p.cpu_percent(interval=None)
        mi = p.memory_info()
        info["rss"] = int(getattr(mi, "rss", 0) or 0)
        info["threads"] = p.num_threads()
        try:
            info["open_files"] = len(p.open_files())
        except Exception:
            info["open_files"] = 0
        ct = p.create_time()
        info["create_time"] = utc_from_ts(ct)
        info["age_seconds"] = int(time.time() - ct)
        try:
            info["exe"] = p.exe()
        except Exception:
            info["exe"] = None
        try:
            info["cmdline"] = " ".join(p.cmdline())[:400]
        except Exception:
            info["cmdline"] = None
        try:
            conns = p.net_connections(kind="inet")
            items = []
            for c in conns[:10]:
                lip = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "-"
                rip = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "-"
                items.append(f"{c.status} {lip} -> {rip}")
            info["connections"] = items
        except Exception:
            info["connections"] = []
        try:
            kids = p.children(recursive=True)[:15]
            info["children"] = [f"{k.name()}({k.pid})" for k in kids]
        except Exception:
            info["children"] = []
    return info


def format_process_snapshot(info: Dict[str, Any]) -> List[str]:
    lines = [
        f"proc={info['name']} pid={info['pid']} user={info['user']} cpu={info['cpu_pct']:.1f}% rss={format_bytes(info['rss'])}",
        f"parent={info['parent_name']}({info['ppid']}) threads={info['threads']} open_files={info['open_files']}",
    ]
    if info.get("create_time"):
        lines.append(f"started={info['create_time']} age={format_duration(info['age_seconds'] or 0)}")
    if info.get("exe"):
        lines.append(f"exe={info['exe']}")
    if info.get("cmdline"):
        lines.append(f"cmd={info['cmdline']}")
    if info.get("connections"):
        lines.append("conns=" + "; ".join(info["connections"][:5]))
    if info.get("children"):
        lines.append("children=" + ", ".join(info["children"][:8]))
    return lines


def prime_cpu_counters() -> List[psutil.Process]:
    procs = list(psutil.process_iter(["pid", "name", "username", "memory_info", "memory_percent"]))
    for p in procs:
        try:
            p.cpu_percent(interval=None)
        except Exception:
            pass
    time.sleep(CONFIG["cpu_process_sample_seconds"])
    return procs


def collect_top_process_rows(limit: int = 5, sort_by: str = "memory") -> List[Dict[str, Any]]:
    try:
        procs = prime_cpu_counters() if sort_by == "cpu" else list(psutil.process_iter(["pid", "name", "username", "memory_info", "memory_percent"]))
    except Exception:
        return []
    rows: List[Dict[str, Any]] = []
    for p in procs:
        try:
            with p.oneshot():
                rss = int(getattr(p.memory_info(), "rss", 0) or 0)
                rows.append({
                    "pid": p.pid,
                    "name": p.name(),
                    "user": p.username() or "unknown",
                    "cpu_pct": p.cpu_percent(interval=None) if sort_by == "cpu" else 0.0,
                    "mem_pct": p.memory_percent(),
                    "rss": rss,
                    "threads": p.num_threads(),
                    "open_files": len(p.open_files()) if hasattr(p, "open_files") else 0,
                })
        except Exception:
            continue
    if sort_by == "cpu":
        rows.sort(key=lambda x: (x["cpu_pct"], x["rss"]), reverse=True)
    elif sort_by == "open_files":
        rows.sort(key=lambda x: (x["open_files"], x["rss"]), reverse=True)
    elif sort_by == "threads":
        rows.sort(key=lambda x: (x["threads"], x["rss"]), reverse=True)
    else:
        rows.sort(key=lambda x: (x["rss"], x["mem_pct"]), reverse=True)
    return rows[:limit]


def render_top_process_rows(rows: List[Dict[str, Any]], label: str) -> List[str]:
    if not rows:
        return [f"{label}: unavailable"]
    out = [label + ":"]
    for r in rows:
        out.append(
            f"{r['name']} pid={r['pid']} user={r['user']} cpu={r['cpu_pct']:.1f}% mem={r['mem_pct']:.1f}% rss={format_bytes(r['rss'])} threads={r['threads']} open_files={r['open_files']}"
        )
    return out


def get_conn_summary_top_ips_and_procs(limit: int = 10) -> Tuple[List[str], List[str]]:
    try:
        conns = psutil.net_connections(kind="inet")
    except Exception:
        return (["Connection summary unavailable."], [])
    ip_counts: Counter = Counter()
    proc_counts: Counter = Counter()
    for c in conns:
        if c.raddr:
            ip_counts[c.raddr.ip] += 1
        if c.pid:
            proc_counts[process_name(c.pid)] += 1
    ip_lines = [
        "Top remote IPs by socket count: " + ", ".join(f"{ip}({cnt})" for ip, cnt in ip_counts.most_common(limit))
    ] if ip_counts else ["No remote IPs currently visible."]
    proc_lines = [
        "Top processes by socket count: " + ", ".join(f"{p}({cnt})" for p, cnt in proc_counts.most_common(limit))
    ] if proc_counts else ["No process/socket mappings visible."]
    return ip_lines, proc_lines


def test_tcp(host: str, port: int, timeout: float = 2.0) -> Tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"tcp://{host}:{port} reachable"
    except Exception as e:
        return False, f"tcp://{host}:{port} failed: {e}"


def test_http(url: str, timeout: float = 4.0) -> Tuple[bool, str]:
    try:
        r = requests.get(url, timeout=timeout)
        return r.ok, f"{url} http={r.status_code}"
    except Exception as e:
        return False, f"{url} failed: {e}"


def systemd_show(unit: str, props: List[str]) -> Dict[str, str]:
    cmd = ["systemctl", "show", unit, "--no-pager"]
    for p in props:
        cmd.extend(["-p", p])
    rc, out, _ = run_cmd(cmd)
    if rc != 0:
        return {}
    data: Dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            data[k] = v
    return data


def journal_tail(unit: Optional[str] = None, priority: Optional[str] = None, lines: int = 20) -> List[str]:
    cmd = ["journalctl", "--no-pager", "-n", str(lines)]
    if unit:
        cmd.extend(["-u", unit])
    if priority:
        cmd.extend(["-p", priority])
    rc, out, _ = run_cmd(cmd)
    if rc != 0:
        return []
    return [l for l in out.splitlines() if l.strip()][-lines:]


def cleanup_old_snapshots() -> None:
    path = CONFIG["snapshot_dir"]
    os.makedirs(path, exist_ok=True)
    cutoff = time.time() - (int(CONFIG["snapshot_retention_days"]) * 86400)
    try:
        for name in os.listdir(path):
            full = os.path.join(path, name)
            try:
                if os.path.isfile(full) and os.path.getmtime(full) < cutoff:
                    os.remove(full)
            except Exception:
                continue
    except Exception:
        pass


def create_forensics_bundle(host: str, alert: Dict[str, Any]) -> Optional[str]:
    try:
        os.makedirs(CONFIG["snapshot_dir"], exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", alert["key"])
        path = os.path.join(CONFIG["snapshot_dir"], f"{host}_{safe_key}_{ts}.txt")
        sections: List[Tuple[str, List[str]]] = []
        commands = [
            ("ps auxwf", ["ps", "auxwf"]),
            ("ss -tunp", ["ss", "-tunp"]),
            ("systemctl --failed", ["systemctl", "--failed", "--no-pager", "--plain"]),
            ("journalctl -p err -n 100", ["journalctl", "-p", "err", "-n", "100", "--no-pager"]),
            ("df -h", ["df", "-h"]),
            ("df -i", ["df", "-i"]),
            ("vmstat", ["vmstat"]),
            ("iostat", ["iostat"]),
        ]
        for title, cmd in commands:
            rc, out, err = run_cmd(cmd, timeout=10)
            body = out if out else err if err else f"rc={rc} no output"
            sections.append((title, body.splitlines()))

        rows_cpu = collect_top_process_rows(limit=10, sort_by="cpu")
        rows_mem = collect_top_process_rows(limit=10, sort_by="memory")
        rows_threads = collect_top_process_rows(limit=10, sort_by="threads")
        sections.append(("top cpu processes", render_top_process_rows(rows_cpu, "top cpu processes")))
        sections.append(("top memory processes", render_top_process_rows(rows_mem, "top memory processes")))
        sections.append(("top threaded processes", render_top_process_rows(rows_threads, "top threaded processes")))

        with open(path, "w", encoding="utf-8") as f:
            f.write(f"remotemon snapshot\nhost={host}\ntime_utc={now_utc_iso()}\nalert_key={alert['key']}\nsummary={alert['summary']}\n\n")
            for title, lines in sections:
                f.write(f"==== {title} ====\n")
                for line in lines:
                    f.write(line.rstrip() + "\n")
                f.write("\n")
        return path
    except Exception as e:
        safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [ERROR] snapshot failed: {e}")
        return None


def queue_or_send(host: str, state: Dict[str, Any], alerts: List[Dict[str, Any]], now_ts: float) -> None:
    to_send: List[Dict[str, Any]] = []
    digest = state.setdefault("digest", {"items": [], "last_flush_ts": 0.0})
    for alert in alerts:
        if should_suppress_delivery(alert):
            safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [INFO] delivery suppressed key={alert['key']} status={alert.get('status')}")
            continue
        if CONFIG["digest_for_low_severity"] and alert.get("digest_eligible") and alert.get("status") == "firing":
            digest["items"].append({
                "time": now_utc_iso(),
                "severity": alert["severity"],
                "category": alert["category"],
                "summary": alert["summary"],
            })
            continue
        to_send.append(alert)

    if digest["items"] and (now_ts - float(digest.get("last_flush_ts", 0.0)) >= CONFIG["digest_flush_seconds"]):
        items = digest["items"][:20]
        digest_alert = make_alert(
            key="digest.low_severity",
            severity="INFO",
            category="DIGEST",
            summary=f"Low-severity digest with {len(items)} item(s).",
            details=[f"{x['time']} {x['severity']} {x['category']}: {x['summary']}" for x in items],
            action="Review recurring low-severity events and promote thresholds if they matter operationally.",
            status="firing",
            digest_eligible=False,
        )
        to_send.append(digest_alert)
        digest["items"] = []
        digest["last_flush_ts"] = now_ts

    if not to_send:
        return

    msg = render_telegram_message(host, to_send)
    ok = send_telegram(msg)
    for alert in to_send:
        finalize_sent_alert_state(state, alert, now_ts)
        safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [{alert['status'].upper()}] {alert['category']} {alert['summary']}")
    if not ok:
        state["telegram_fail_count"] = int(state.get("telegram_fail_count", 0)) + 1
    else:
        state["telegram_fail_count"] = 0


def net_anomaly_check(state: Dict[str, Any], up_bps: float, down_bps: float, now_ts: float) -> Optional[Dict[str, Any]]:
    net = state.setdefault("net", {})
    up_samples = net.setdefault("up_samples", [])
    down_samples = net.setdefault("down_samples", [])
    up_samples[:] = trim_old_samples(up_samples, CONFIG["net_window_seconds"], now_ts)
    down_samples[:] = trim_old_samples(down_samples, CONFIG["net_window_seconds"], now_ts)
    up_samples.append([now_ts, float(up_bps)])
    down_samples.append([now_ts, float(down_bps)])
    if len(up_samples) < CONFIG["net_min_baseline_samples"] or len(down_samples) < CONFIG["net_min_baseline_samples"]:
        return None
    up_vals = [v for _, v in up_samples]
    down_vals = [v for _, v in down_samples]
    up_mean, up_std = compute_stats(up_vals)
    down_mean, down_std = compute_stats(down_vals)
    up_thresh = max(up_mean * CONFIG["net_alert_factor"], up_mean + CONFIG["net_alert_sigma_mult"] * up_std)
    down_thresh = max(down_mean * CONFIG["net_alert_factor"], down_mean + CONFIG["net_alert_sigma_mult"] * down_std)
    active = (up_bps > up_thresh and up_bps > 0) or (down_bps > down_thresh and down_bps > 0)
    base = make_alert(
        key="network_spike",
        severity="WARNING",
        category="NETWORK",
        summary="Traffic spike detected." if active else "Traffic returned below anomaly threshold.",
        threshold=f"upload > {format_bps(up_thresh)} or download > {format_bps(down_thresh)}",
        details=[
            f"Current upload rate: {format_bps(up_bps)}",
            f"Current download rate: {format_bps(down_bps)}",
            f"Upload baseline: mean {format_bps(up_mean)}, stddev {format_bps(up_std)}",
            f"Download baseline: mean {format_bps(down_mean)}, stddev {format_bps(down_std)}",
            *get_conn_summary_top_ips_and_procs(limit=CONFIG["net_connection_summary_limit"])[0],
            *get_conn_summary_top_ips_and_procs(limit=CONFIG["net_connection_summary_limit"])[1],
        ],
        action="Inspect active connections and confirm whether the traffic pattern is expected.",
    )
    return alert_transition(state, base, active, now_ts)


def check_ram(state: Dict[str, Any], now_ts: float) -> Optional[Dict[str, Any]]:
    vm = psutil.virtual_memory()
    active = vm.percent >= CONFIG["ram_alert_pct"]
    rows = collect_top_process_rows(limit=3, sort_by="memory") if active else []
    details = [
        f"Used: {format_bytes(vm.used)}",
        f"Available: {format_bytes(vm.available)}",
        f"Total: {format_bytes(vm.total)}",
    ]
    if active and rows:
        details.extend(render_top_process_rows(rows, "Top RSS"))
        try:
            details.extend(format_process_snapshot(get_process_snapshot(rows[0]["pid"])))
        except Exception:
            pass
    base = make_alert(
        key="ram_high",
        severity="WARNING",
        category="MEMORY",
        summary=f"RAM usage {'is above threshold' if active else 'recovered'} at {vm.percent:.1f}%.",
        threshold=f">= {CONFIG['ram_alert_pct']}%",
        details=details,
        action="Inspect memory-heavy processes and validate whether RSS growth is expected.",
    )
    return alert_transition(state, base, active, now_ts)


def check_swap(state: Dict[str, Any], now_ts: float) -> Optional[Dict[str, Any]]:
    sm = psutil.swap_memory()
    if sm.total <= 0:
        return None
    active = sm.percent >= CONFIG["swap_alert_pct"]
    base = make_alert(
        key="swap_high",
        severity="WARNING",
        category="SWAP",
        summary=f"Swap usage {'is elevated' if active else 'recovered'} at {sm.percent:.1f}%.",
        threshold=f">= {CONFIG['swap_alert_pct']}%",
        details=[f"Used: {format_bytes(sm.used)}", f"Free: {format_bytes(sm.free)}", f"Total: {format_bytes(sm.total)}"],
        action="Check for memory pressure, swapping, or processes with monotonic RSS growth.",
    )
    return alert_transition(state, base, active, now_ts)


def get_top_dirs_by_size(path: str, limit: int = 5, depth: int = 2) -> List[str]:
    rc, out, _ = run_cmd(["du", "-x", f"--max-depth={depth}", "-h", path], timeout=20)
    if rc != 0 or not out:
        return []
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines[-limit:]


def get_top_inode_dirs(path: str, limit: int = 5) -> List[str]:
    rc, out, _ = run_cmd(["bash", "-lc", f"find {path} -xdev -mindepth 1 -maxdepth 2 -printf '%h\n' 2>/dev/null | sort | uniq -c | sort -nr | head -n {limit}"], timeout=20)
    if rc != 0 or not out:
        return []
    return [l.strip() for l in out.splitlines() if l.strip()]


def get_deleted_open_files(limit: int = 5) -> List[str]:
    rc, out, _ = run_cmd(["bash", "-lc", f"lsof -nP +L1 2>/dev/null | head -n {limit + 1}"], timeout=10)
    if rc != 0 or not out:
        return []
    return [l.strip() for l in out.splitlines()[1:limit + 1] if l.strip()]


def check_disks(state: Dict[str, Any], now_ts: float) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    for path in CONFIG["disk_paths"]:
        try:
            du = shutil.disk_usage(path)
            used_pct = (du.used / du.total) * 100.0 if du.total else 0.0
        except Exception:
            continue
        active = used_pct >= CONFIG["disk_alert_pct"]
        details = [f"Used: {format_bytes(du.used)}", f"Free: {format_bytes(du.free)}", f"Total: {format_bytes(du.total)}"]
        if active:
            sized = get_top_dirs_by_size(path, limit=CONFIG["triage_top_n"], depth=CONFIG["triage_dir_depth"])
            if sized:
                details.append("Top directories by size:")
                details.extend(sized)
            deleted = get_deleted_open_files(limit=CONFIG["triage_top_n"])
            if deleted:
                details.append("Deleted but open files:")
                details.extend(deleted)
        base = make_alert(
            key=f"disk_high:{path}",
            severity="WARNING",
            category="DISK",
            summary=f"Disk usage on {path} {'is above threshold' if active else 'recovered'} at {used_pct:.1f}%.",
            threshold=f">= {CONFIG['disk_alert_pct']}%",
            details=details,
            action=f"Review large directories, deleted-open files, and growth under {path}.",
        )
        out = alert_transition(state, base, active, now_ts)
        if out:
            alerts.append(out)
    return alerts


def check_inodes(state: Dict[str, Any], now_ts: float) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    for path in CONFIG["disk_paths"]:
        try:
            st = os.statvfs(path)
            total = st.f_files
            free = st.f_ffree
            if total <= 0:
                continue
            used = total - free
            used_pct = (used / total) * 100.0
        except Exception:
            continue
        active = used_pct >= CONFIG["inode_alert_pct"]
        details = [f"Used inodes: {used}", f"Free inodes: {free}", f"Total inodes: {total}"]
        if active:
            heavy = get_top_inode_dirs(path, limit=CONFIG["triage_top_n"])
            if heavy:
                details.append("Top file-count-heavy directories:")
                details.extend(heavy)
        base = make_alert(
            key=f"inodes_high:{path}",
            severity="WARNING",
            category="INODES",
            summary=f"Inode usage on {path} {'is above threshold' if active else 'recovered'} at {used_pct:.1f}%.",
            threshold=f">= {CONFIG['inode_alert_pct']}%",
            details=details,
            action="Look for directories with extreme small-file accumulation.",
        )
        out = alert_transition(state, base, active, now_ts)
        if out:
            alerts.append(out)
    return alerts


def check_cpu_load(state: Dict[str, Any], now_ts: float) -> Optional[Dict[str, Any]]:
    try:
        load1, load5, _ = os.getloadavg()
        cpu_count = psutil.cpu_count(logical=True) or 1
        load_pct = (load1 / cpu_count) * 100.0
    except Exception:
        return None
    active = load_pct >= CONFIG["cpu_load_alert_pct"]
    details = [f"1-minute load average: {load1:.2f}", f"5-minute load average: {load5:.2f}", f"Logical CPU count: {cpu_count}"]
    if active:
        rows_cpu = collect_top_process_rows(limit=3, sort_by="cpu")
        rows_threads = collect_top_process_rows(limit=3, sort_by="threads")
        details.extend(render_top_process_rows(rows_cpu, "Top CPU"))
        details.extend(render_top_process_rows(rows_threads, "Top thread count"))
        if rows_cpu:
            try:
                details.extend(format_process_snapshot(get_process_snapshot(rows_cpu[0]["pid"])))
            except Exception:
                pass
    base = make_alert(
        key="cpu_load_high",
        severity="WARNING",
        category="CPU",
        summary=f"CPU load {'is elevated' if active else 'recovered'} at approximately {load_pct:.1f}% of logical capacity.",
        threshold=f">= {CONFIG['cpu_load_alert_pct']}%",
        details=details,
        action="Inspect CPU-heavy processes and correlate with I/O wait or blocked services.",
    )
    return alert_transition(state, base, active, now_ts)


def check_reboot(state: Dict[str, Any], now_ts: float) -> Optional[Dict[str, Any]]:
    boot_ts = psutil.boot_time()
    last_boot = state.get("last_boot_time")
    state["last_boot_time"] = boot_ts
    if last_boot is None:
        return None
    active = float(last_boot) != float(boot_ts)
    details = [f"New boot time (UTC): {utc_from_ts(boot_ts)}"]
    if active:
        service_summaries = []
        for spec in CONFIG["required_services"][:5]:
            unit = spec.get("unit")
            if not unit:
                continue
            props = systemd_show(unit, ["ActiveState", "SubState"])
            service_summaries.append(f"{unit}: {props.get('ActiveState', 'unknown')}/{props.get('SubState', 'unknown')}")
        if service_summaries:
            details.append("Core service states after reboot:")
            details.extend(service_summaries)
    base = make_alert(
        key="system_reboot",
        severity="CRITICAL",
        category="SYSTEM",
        summary="System reboot detected." if active else "No reboot change remains active.",
        details=details,
        action="Verify whether the reboot was expected and confirm core services are healthy.",
        digest_eligible=False,
    )
    return alert_transition(state, base, active, now_ts)


def read_auth_lines() -> Tuple[Optional[str], List[str]]:
    log_path = None
    for candidate in CONFIG["auth_log_candidates"]:
        if os.path.exists(candidate):
            log_path = candidate
            break
    if not log_path:
        return None, []
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            return log_path, f.readlines()[-CONFIG["failed_ssh_log_tail_lines"]:]
    except Exception:
        return log_path, []


def check_auth_activity(state: Dict[str, Any], now_ts: float) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    if not CONFIG["check_failed_ssh"]:
        return alerts
    log_path, lines = read_auth_lines()
    if not log_path:
        return alerts
    failed_count = 0
    failed_ips: Counter = Counter()
    success_ips: Counter = Counter()
    root_success = []
    sudo_hits = []
    for line in lines:
        if "Failed password" in line:
            failed_count += 1
            m = re.search(r"from\s+([0-9a-fA-F\.:]+)\s+port", line)
            if m:
                failed_ips[m.group(1)] += 1
        if "Accepted" in line and "sshd" in line:
            m_ip = re.search(r"from\s+([0-9a-fA-F\.:]+)\s+port", line)
            m_user = re.search(r"for\s+(invalid user\s+)?([^\s]+)", line)
            ip = m_ip.group(1) if m_ip else "unknown"
            user = m_user.group(2) if m_user else "unknown"
            success_ips[ip] += 1
            if user == "root":
                root_success.append(line.strip())
        if "sudo:" in line and "COMMAND=" in line:
            if not CONFIG["sudo_watch_users"]:
                sudo_hits.append(line.strip())
            else:
                if any(f" {u} :" in line for u in CONFIG["sudo_watch_users"]):
                    sudo_hits.append(line.strip())

    brute_active = failed_count >= CONFIG["failed_ssh_alert_count"]
    brute = make_alert(
        key="failed_ssh",
        severity="WARNING",
        category="AUTH",
        summary="Repeated SSH authentication failures detected." if brute_active else "SSH authentication failure activity recovered.",
        threshold=f">= {CONFIG['failed_ssh_alert_count']} failed password events in recent log tail",
        details=[f"Approximate failed events counted: {failed_count}", f"Top source IPs: {', '.join(f'{ip}({cnt})' for ip, cnt in failed_ips.most_common(10)) or 'none'}", f"Log source: {log_path}"],
        action="Review SSH exposure, block abusive sources, and confirm whether attempts are expected.",
    )
    out = alert_transition(state, brute, brute_active, now_ts)
    if out:
        alerts.append(out)

    if CONFIG["alert_new_ssh_source"] and success_ips:
        seen = state.setdefault("seen_ssh_success_ips", {})
        new_ips = [ip for ip in success_ips if ip not in seen]
        for ip in success_ips:
            seen[ip] = now_ts
        active = bool(new_ips)
        base = make_alert(
            key="ssh_success_new_source",
            severity="HIGH",
            category="AUTH",
            summary="Successful SSH login from previously unseen source IP." if active else "No unseen successful SSH source remains active.",
            details=[f"New source IPs: {', '.join(new_ips) or 'none'}", f"Recent successful source distribution: {', '.join(f'{ip}({cnt})' for ip, cnt in success_ips.most_common(10))}"],
            action="Confirm the source IPs are legitimate administrative origins.",
            digest_eligible=False,
        )
        out = alert_transition(state, base, active, now_ts)
        if out:
            alerts.append(out)

    if CONFIG["alert_root_ssh_login"]:
        active = bool(root_success)
        base = make_alert(
            key="ssh_root_login",
            severity="HIGH",
            category="AUTH",
            summary="Successful SSH root login detected." if active else "No successful SSH root login remains active.",
            details=root_success[-5:] if root_success else [f"Log source: {log_path}"],
            action="Validate that direct root SSH access is intended.",
            digest_eligible=False,
        )
        out = alert_transition(state, base, active, now_ts)
        if out:
            alerts.append(out)

    active = bool(sudo_hits)
    base = make_alert(
        key="sudo_usage",
        severity="INFO",
        category="AUTH",
        summary="Recent sudo activity detected." if active else "No watched sudo activity remains active.",
        details=sudo_hits[-5:] if sudo_hits else [f"Log source: {log_path}"],
        action="Validate privileged command usage if it was not planned.",
    )
    out = alert_transition(state, base, active, now_ts)
    if out:
        alerts.append(out)
    return alerts


def check_systemd_failed_units(state: Dict[str, Any], now_ts: float) -> Optional[Dict[str, Any]]:
    if not CONFIG["check_systemd_failed_units"]:
        return None
    rc, out, _ = run_cmd(["systemctl", "--failed", "--no-pager", "--plain"])
    if rc != 0:
        return None
    no_failed = "0 loaded units listed" in out
    failed_lines = [l.strip() for l in out.splitlines() if ".service" in l or ".socket" in l or ".timer" in l]
    active = (not no_failed) and bool(failed_lines)
    details = failed_lines[: CONFIG["systemd_failed_units_limit"]]
    if active and details:
        first_unit = details[0].split()[0]
        j = journal_tail(first_unit, priority="err", lines=10)
        if j:
            details.append(f"Recent journal errors for {first_unit}:")
            details.extend(j[-5:])
    base = make_alert(
        key="systemd_failed_units",
        severity="WARNING",
        category="SYSTEMD",
        summary="One or more systemd units are in failed state." if active else "No failed systemd units remain.",
        details=details or ["No failed units detected."],
        action="Inspect unit status, restart counters, and recent journal errors.",
    )
    return alert_transition(state, base, active, now_ts)


def current_listen_ports() -> Dict[str, List[int]]:
    result: Dict[str, List[int]] = defaultdict(list)
    try:
        for c in psutil.net_connections(kind="inet"):
            if c.status == psutil.CONN_LISTEN and c.laddr and c.pid:
                result[process_name(c.pid)].append(int(c.laddr.port))
    except Exception:
        pass
    return {k: sorted(set(v)) for k, v in result.items()}


def check_new_listening_ports(state: Dict[str, Any], now_ts: float) -> Optional[Dict[str, Any]]:
    current = current_listen_ports()
    prev = state.setdefault("listen_ports", {})
    state["listen_ports"] = current
    new_items = []
    for proc, ports in current.items():
        prev_ports = set(prev.get(proc, []))
        for port in ports:
            if port not in prev_ports:
                new_items.append(f"{proc}:{port}")
    active = bool(new_items)
    base = make_alert(
        key="new_listening_port",
        severity="HIGH",
        category="SECURITY",
        summary="New listening port detected." if active else "No newly observed listening ports remain active.",
        details=new_items[:20] if new_items else ["No new listening ports observed."],
        action="Confirm that each newly listening socket belongs to an expected service rollout.",
        digest_eligible=False,
    )
    return alert_transition(state, base, active, now_ts)


def check_new_outbound_remotes(state: Dict[str, Any], now_ts: float) -> Optional[Dict[str, Any]]:
    seen = state.setdefault("seen_remote_ips", {})
    new_ips: List[str] = []
    try:
        for c in psutil.net_connections(kind="inet"):
            if c.raddr:
                ip = c.raddr.ip
                if ip not in seen:
                    seen[ip] = now_ts
                    new_ips.append(ip)
    except Exception:
        return None
    active = bool(new_ips)
    base = make_alert(
        key="new_outbound_remote",
        severity="INFO",
        category="NETWORK",
        summary="Outbound connections to unseen remote IPs detected." if active else "No unseen outbound remote IPs remain active.",
        details=[f"New remote IPs: {', '.join(new_ips[:20])}"] if new_ips else ["No new remote IPs observed."],
        action="Validate whether new remote peers correspond to expected application behavior.",
    )
    return alert_transition(state, base, active, now_ts)


def scan_suspicious_processes(state: Dict[str, Any], now_ts: float) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    tmp_hits = []
    deleted_hits = []
    chain_hits = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            exe = p.exe()
            cmd = " ".join(p.cmdline())
            parent = p.parent()
            pname = parent.name() if parent else "none"
            if CONFIG["watch_tmp_exec"] and exe and any(exe.startswith(x) for x in ["/tmp/", "/dev/shm/", "/var/tmp/"]):
                tmp_hits.append(f"{p.name()} pid={p.pid} exe={exe} parent={pname} cmd={cmd[:200]}")
            if CONFIG["watch_deleted_running_exec"] and exe and " (deleted)" in exe:
                deleted_hits.append(f"{p.name()} pid={p.pid} exe={exe} parent={pname}")
            if CONFIG["watch_suspicious_chains"] and parent:
                child = p.name()
                if pname in {"nginx", "apache2", "httpd"} and child in {"sh", "bash", "curl", "wget", "python", "perl"}:
                    chain_hits.append(f"{pname}({parent.pid}) -> {child}({p.pid}) cmd={cmd[:200]}")
        except Exception:
            continue

    for key, sev, summary, items, action in [
        ("tmp_exec", "HIGH", "Process executing from temporary storage detected.", tmp_hits, "Inspect the binary, parent chain, and persistence artifacts immediately."),
        ("deleted_running_exec", "HIGH", "Running executable deleted from disk detected.", deleted_hits, "Capture the process image and confirm whether this is a legitimate package upgrade artifact."),
        ("suspicious_chain", "HIGH", "Suspicious parent/child execution chain detected.", chain_hits, "Review process ancestry and outbound activity for command execution or payload retrieval."),
    ]:
        active = bool(items)
        base = make_alert(
            key=key,
            severity=sev,
            category="SECURITY",
            summary=summary if active else f"Condition cleared for {key}.",
            details=items[:10] if items else ["No matching processes observed."],
            action=action,
            digest_eligible=False,
        )
        out = alert_transition(state, base, active, now_ts)
        if out:
            alerts.append(out)
    return alerts


def file_signature(path: str) -> Optional[str]:
    try:
        st = os.stat(path)
        return f"{st.st_mtime_ns}:{st.st_size}:{st.st_mode}:{st.st_uid}:{st.st_gid}"
    except Exception:
        return None


def check_file_integrity(state: Dict[str, Any], now_ts: float) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    sigs = state.setdefault("file_integrity", {})
    for path in CONFIG["watch_paths_integrity"]:
        sig = file_signature(path)
        prev = sigs.get(path)
        sigs[path] = sig
        if prev is None:
            continue
        active = prev != sig
        base = make_alert(
            key=f"file_change:{path}",
            severity="HIGH",
            category="INTEGRITY",
            summary=f"Watched file changed: {path}" if active else f"Watched file stable again: {path}",
            details=[f"Previous signature: {prev}", f"Current signature: {sig}"],
            action="Validate that the change was expected and originated from an authorized deployment or administration action.",
            digest_eligible=False,
        )
        out = alert_transition(state, base, active, now_ts)
        if out:
            alerts.append(out)
    return alerts


def check_service_awareness(state: Dict[str, Any], now_ts: float) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    for spec in CONFIG["required_services"]:
        name = spec.get("name") or spec.get("unit") or "unnamed-service"
        unit = spec.get("unit")
        details: List[str] = []
        active = False
        if unit:
            props = systemd_show(unit, ["LoadState", "ActiveState", "SubState", "NRestarts", "ExecMainStartTimestamp"])
            details.append(f"unit={unit} state={props.get('ActiveState', 'unknown')}/{props.get('SubState', 'unknown')} load={props.get('LoadState', 'unknown')}")
            if props.get("NRestarts"):
                details.append(f"restart_count={props['NRestarts']}")
                try:
                    if int(props["NRestarts"]) > 0:
                        active = True
                    if int(props["NRestarts"]) >= 3:
                        active = True
                except Exception:
                    pass
            if props.get("ActiveState") != "active":
                active = True
                j = journal_tail(unit, priority="err", lines=15)
                if j:
                    details.append("recent_journal_errors:")
                    details.extend(j[-8:])
        for port in spec.get("ports", []):
            ok = False
            try:
                for c in psutil.net_connections(kind="inet"):
                    if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == int(port):
                        ok = True
                        break
            except Exception:
                pass
            details.append(f"listen_port {port}: {'ok' if ok else 'missing'}")
            if not ok:
                active = True
        for tcp in spec.get("tcp_checks", []):
            ok, msg = test_tcp(tcp.get("host", "127.0.0.1"), int(tcp["port"]))
            details.append(msg)
            if not ok:
                active = True
        for url in spec.get("http_checks", []):
            ok, msg = test_http(url)
            details.append(msg)
            if not ok:
                active = True
        missing_dep_ports = []
        for dep_port in spec.get("depends_on_ports", []):
            ok = False
            try:
                for c in psutil.net_connections(kind="inet"):
                    if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == int(dep_port):
                        ok = True
                        break
            except Exception:
                pass
            if not ok:
                missing_dep_ports.append(dep_port)
        if missing_dep_ports:
            active = True
            details.append(f"dependency ports missing: {', '.join(str(x) for x in missing_dep_ports)}")
        base = make_alert(
            key=f"service_health:{name}",
            severity="HIGH" if active else "INFO",
            category="SERVICE",
            summary=f"Service health problem detected for {name}." if active else f"Service health recovered for {name}.",
            details=details,
            action="Confirm unit state, probe results, dependencies, and recent restart behavior.",
            digest_eligible=False,
        )
        out = alert_transition(state, base, active, now_ts)
        if out:
            alerts.append(out)
    return alerts


def check_journal_patterns(state: Dict[str, Any], now_ts: float) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    recent_err = journal_tail(priority="err", lines=200)
    text = "\n".join(recent_err)
    patterns = [
        ("oom_killer", "CRITICAL", "OOM killer activity detected.", bool(re.search(r"Out of memory|Killed process", text, re.I))),
        ("segfaults", "HIGH", "Segfault or crash pattern detected.", bool(re.search(r"segfault|general protection fault|core dumped", text, re.I))),
        ("fs_errors", "HIGH", "Filesystem error pattern detected.", bool(re.search(r"I/O error|EXT4-fs error|XFS .* error|Remounting filesystem read-only", text, re.I))),
        ("kernel_error_burst", "WARNING", "Recent journal error burst detected.", len(recent_err) >= CONFIG["journal_burst_error_count"]),
    ]
    for key, sev, summary, active in patterns:
        base = make_alert(
            key=key,
            severity=sev,
            category="JOURNAL",
            summary=summary if active else f"Condition cleared for {key}.",
            details=recent_err[-10:] if active else ["No recent matching journal pattern remains active."],
            action="Review kernel and service logs to establish impact and root cause.",
            digest_eligible=sev == "WARNING",
        )
        out = alert_transition(state, base, active, now_ts)
        if out:
            alerts.append(out)
    return alerts


def emit_startup_self_test(host: str, state: Dict[str, Any]) -> None:
    checks = []
    checks.append(f"psutil={'ok' if psutil else 'missing'}")
    checks.append(f"requests={'ok' if requests else 'missing'}")
    for cmd in ["ss", "systemctl", "journalctl"]:
        checks.append(f"{cmd}={'ok' if shutil.which(cmd) else 'missing'}")
    log_path, _ = read_auth_lines()
    checks.append(f"auth_log={'ok' if log_path else 'missing'}")
    checks.append(f"telegram={'configured' if CONFIG['telegram_bot_token'] and CONFIG['telegram_chat_id'] else 'not-configured'}")
    alert = make_alert(
        key="startup_self_test",
        severity="INFO",
        category="SELFTEST",
        summary="remotemon startup self-test completed.",
        details=checks,
        action="Resolve missing dependencies or permissions before treating the monitor as authoritative.",
        digest_eligible=False,
    )
    send_telegram(render_telegram_message(host, [alert]))
    finalize_sent_alert_state(state, alert, time.time())


def check_heartbeat(host: str, state: Dict[str, Any], now_ts: float) -> None:
    last = float(state.get("last_heartbeat_ts", 0.0) or 0.0)
    interval = int(CONFIG["heartbeat_hours"]) * 3600
    if interval <= 0 or now_ts - last < interval:
        return
    alert = make_alert(
        key="heartbeat",
        severity="INFO",
        category="HEARTBEAT",
        summary="remotemon heartbeat.",
        details=[f"host={host}", f"boot_time={utc_from_ts(psutil.boot_time())}", f"state_file={CONFIG['state_file']}", f"watchdog_file={CONFIG['watchdog_file']}"],
        action="No action required.",
        digest_eligible=False,
    )
    if send_telegram(render_telegram_message(host, [alert])):
        state["last_heartbeat_ts"] = now_ts


def update_watchdog_file() -> None:
    try:
        os.makedirs(os.path.dirname(CONFIG["watchdog_file"]), exist_ok=True)
        with open(CONFIG["watchdog_file"], "w", encoding="utf-8") as f:
            f.write(now_utc_iso() + "\n")
    except Exception:
        pass


def maybe_attach_snapshots(host: str, alerts: List[Dict[str, Any]]) -> None:
    for alert in alerts:
        if alert.get("status") in {"firing", "escalated"} and severity_at_least(alert["severity"], "WARNING"):
            alert["snapshot_path"] = create_forensics_bundle(host, alert)


def main() -> None:
    host = hostname()
    state = load_state(CONFIG["state_file"])
    cleanup_old_snapshots()
    prev_net = state.get("prev_net_bytes")
    prev_ts = state.get("prev_net_ts")
    if not prev_net or not prev_ts:
        prev_net = snapshot_net_bytes()
        prev_ts = time.time()
        state["prev_net_bytes"] = prev_net
        state["prev_net_ts"] = prev_ts
        save_state(CONFIG["state_file"], state)
    safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [INFO] remotemon started on host={host} interval={CONFIG['interval_seconds']}s")
    if CONFIG["startup_message"] and not state.get("startup_message_sent"):
        emit_startup_self_test(host, state)
        state["startup_message_sent"] = True
        save_state(CONFIG["state_file"], state)

    while True:
        try:
            time.sleep(CONFIG["interval_seconds"])
            now_ts = time.time()
            alerts: List[Dict[str, Any]] = []

            for checker in [
                lambda: check_reboot(state, now_ts),
                lambda: check_ram(state, now_ts),
                lambda: check_swap(state, now_ts),
                lambda: check_cpu_load(state, now_ts),
                lambda: check_systemd_failed_units(state, now_ts),
                lambda: check_new_listening_ports(state, now_ts),
                lambda: check_new_outbound_remotes(state, now_ts),
                lambda: net_anomaly_check(state, *get_net_rates(prev_net, snapshot_net_bytes(), max(1e-6, now_ts - float(prev_ts))), now_ts),
            ]:
                alert = checker()
                if alert:
                    alerts.append(alert)

            alerts.extend(check_auth_activity(state, now_ts))
            alerts.extend(check_disks(state, now_ts))
            alerts.extend(check_inodes(state, now_ts))
            alerts.extend(scan_suspicious_processes(state, now_ts))
            alerts.extend(check_file_integrity(state, now_ts))
            alerts.extend(check_service_awareness(state, now_ts))
            alerts.extend(check_journal_patterns(state, now_ts))

            curr_net = snapshot_net_bytes()
            state["prev_net_bytes"] = curr_net
            state["prev_net_ts"] = now_ts
            prev_net = curr_net
            prev_ts = now_ts

            maybe_attach_snapshots(host, alerts)
            queue_or_send(host, state, alerts, now_ts)
            check_heartbeat(host, state, now_ts)
            cleanup_old_snapshots()
            update_watchdog_file()
            save_state(CONFIG["state_file"], state)
        except KeyboardInterrupt:
            safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [INFO] remotemon stopped by user")
            break
        except Exception as e:
            safe_write_log(CONFIG["log_file"], f"{now_utc_iso()} [ERROR] loop error: {e}")
            update_watchdog_file()
            save_state(CONFIG["state_file"], state)


if __name__ == "__main__":
    main()
