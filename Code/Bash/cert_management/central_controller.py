import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone, timedelta
import ssl
import socket

DB = "certmgr.sqlite3"

def utcnow():
    return datetime.now(timezone.utc)

def parse_openssl_notafter(s: str) -> datetime:
    # Example: "Jan 30 12:34:56 2026 GMT"
    return datetime.strptime(s.strip(), "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)

def tls_notafter_and_fpr(host: str, port: int = 443):
    ctx = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=10) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ssock:
            cert_bin = ssock.getpeercert(binary_form=True)
            cert = ssl.DER_cert_to_PEM_cert(cert_bin)

    # Extract notAfter and fingerprint using openssl locally
    p = subprocess.run(
        ["openssl", "x509", "-noout", "-enddate", "-fingerprint", "-sha256"],
        input=cert.encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    out = p.stdout.decode()
    not_after = None
    fpr = None
    for line in out.splitlines():
        if line.startswith("notAfter="):
            not_after = line.split("=", 1)[1].strip()
        if line.startswith("sha256 Fingerprint="):
            fpr = line.split("=", 1)[1].strip()
    if not_after is None or fpr is None:
        raise RuntimeError("Unable to parse certificate details from openssl output.")
    return not_after, fpr

def ssh_run(host: str, user: str, port: int, zone: str):
    # Load Cloudflare token on remote side from a root-readable env file.
    # For example, /etc/cert-agent.env contains: CF_Token=...
    # The remote command: source env, run agent, print JSON.
    remote_cmd = f"set -e; sudo -n bash -lc 'source /etc/cert-agent.env; /usr/local/sbin/cert-agent-renew {zone}'"
    cmd = ["ssh", "-p", str(port), f"{user}@{host}", remote_cmd]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    conn.execute("""
      CREATE TABLE IF NOT EXISTS targets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        host TEXT NOT NULL,
        ssh_user TEXT NOT NULL,
        ssh_port INTEGER NOT NULL DEFAULT 22,
        zone TEXT NOT NULL,
        renew_before_days INTEGER NOT NULL DEFAULT 30,
        last_not_after TEXT,
        last_fingerprint_sha256 TEXT,
        last_ok INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        last_run_utc TEXT,
        next_run_utc TEXT
      )
    """)
    conn.commit()

    rows = conn.execute("SELECT * FROM targets").fetchall()
    now = utcnow()

    for r in rows:
        target_id = r["id"]
        host = r["host"]
        user = r["ssh_user"]
        port = int(r["ssh_port"])
        zone = r["zone"]
        renew_before = int(r["renew_before_days"])

        # Decide if due (simple: run if next_run_utc is null or <= now)
        due = True
        if r["next_run_utc"]:
            try:
                due_time = datetime.fromisoformat(r["next_run_utc"])
                due = due_time <= now
            except Exception:
                due = True

        if not due:
            continue

        # Attempt remote renew
        rc, out, err = ssh_run(host, user, port, zone)

        last_run = now.isoformat()
        if rc != 0:
            # Backoff: retry in 2 hours
            next_run = (now + timedelta(hours=2)).isoformat()
            conn.execute(
                "UPDATE targets SET last_ok=0,last_error=?,last_run_utc=?,next_run_utc=? WHERE id=?",
                (f"ssh/agent failed: {err[:500]}", last_run, next_run, target_id)
            )
            conn.commit()
            print(f"[{host}] FAIL (agent): {err}", file=sys.stderr)
            continue

        try:
            payload = json.loads(out.splitlines()[-1])
            if not payload.get("ok"):
                raise RuntimeError("Agent returned ok=false")
            agent_not_after = payload["not_after"]
            agent_fpr = payload["fingerprint_sha256"]
        except Exception as e:
            next_run = (now + timedelta(hours=2)).isoformat()
            conn.execute(
                "UPDATE targets SET last_ok=0,last_error=?,last_run_utc=?,next_run_utc=? WHERE id=?",
                (f"bad agent output: {str(e)} | out={out[:500]} | err={err[:500]}", last_run, next_run, target_id)
            )
            conn.commit()
            print(f"[{host}] FAIL (parse): {e}", file=sys.stderr)
            continue

        # Verify over TLS on host:443
        try:
            tls_not_after, tls_fpr = tls_notafter_and_fpr(host, 443)
        except Exception as e:
            next_run = (now + timedelta(hours=2)).isoformat()
            conn.execute(
                "UPDATE targets SET last_ok=0,last_error=?,last_run_utc=?,next_run_utc=? WHERE id=?",
                (f"tls verify failed: {str(e)}", last_run, next_run, target_id)
            )
            conn.commit()
            print(f"[{host}] FAIL (verify): {e}", file=sys.stderr)
            continue

        # Compute next run: check daily, but renew decision happens on host side.
        next_run = (now + timedelta(days=1)).isoformat()

        conn.execute(
            """UPDATE targets
               SET last_ok=1,
                   last_error=NULL,
                   last_not_after=?,
                   last_fingerprint_sha256=?,
                   last_run_utc=?,
                   next_run_utc=?
               WHERE id=?""",
            (tls_not_after, tls_fpr, last_run, next_run, target_id)
        )
        conn.commit()

        # Optional: warn if expiry is close
        try:
            exp = parse_openssl_notafter(tls_not_after)
            days = (exp - now).days
            status = "OK" if days > renew_before else "NEAR_EXPIRY"
        except Exception:
            status = "OK"

        print(f"[{host}] {status} notAfter={tls_not_after} fpr={tls_fpr}")

if __name__ == "__main__":
    main()
