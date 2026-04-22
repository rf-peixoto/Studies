import threading
import smtplib
import asyncio
import email.utils
import dns.resolver
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from flask import Flask, render_template, request, jsonify

try:
    from aiosmtpd.controller import Controller
    USE_AIOSMTPD = True
except ImportError:
    import smtpd
    import asyncore
    USE_AIOSMTPD = False

app = Flask(__name__)

SMTP_HOST = "127.0.0.1"
SMTP_PORT = 1025

received_emails = []


# ─── MX Relay ────────────────────────────────────────────────────────────────

def relay_message(mail_from, rcpt_tos, raw_data):
    """
    Resolve MX records for each recipient domain and deliver directly.
    Returns { recipient: {"ok": bool, "detail": str} }
    """
    results = {}
    by_domain = {}
    for rcpt in rcpt_tos:
        domain = rcpt.split("@")[-1].lower()
        by_domain.setdefault(domain, []).append(rcpt)

    for domain, recipients in by_domain.items():
        try:
            mx_records = dns.resolver.resolve(domain, "MX")
            mx_hosts = [r.exchange.to_text().rstrip(".") for r in sorted(mx_records, key=lambda r: r.preference)]
        except Exception as dns_err:
            mx_hosts = [domain]
            print(f"[RELAY] DNS MX lookup failed for {domain}: {dns_err} — trying A record")

        delivered = False
        last_error = None

        for mx_host in mx_hosts:
            try:
                print(f"[RELAY] Connecting to {mx_host}:25 for {recipients}")
                with smtplib.SMTP(mx_host, 25, timeout=15) as relay:
                    relay.ehlo_or_helo_if_needed()
                    try:
                        relay.starttls()
                        relay.ehlo()
                    except smtplib.SMTPException:
                        pass
                    refused = relay.sendmail(mail_from, recipients, raw_data)
                    for rcpt in recipients:
                        if rcpt in refused:
                            code, msg = refused[rcpt]
                            results[rcpt] = {"ok": False, "detail": f"{code} {msg.decode()}"}
                        else:
                            results[rcpt] = {"ok": True, "detail": f"delivered via {mx_host}"}
                delivered = True
                break
            except Exception as e:
                last_error = str(e)
                print(f"[RELAY] Failed via {mx_host}: {e}")

        if not delivered:
            for rcpt in recipients:
                if rcpt not in results:
                    results[rcpt] = {"ok": False, "detail": f"all MX failed — {last_error}"}

    return results


# ─── SMTP Server ─────────────────────────────────────────────────────────────

if USE_AIOSMTPD:
    class RelayHandler:
        async def handle_DATA(self, server, session, envelope):
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            raw = envelope.content if isinstance(envelope.content, bytes) else envelope.content.encode()
            loop = asyncio.get_event_loop()
            relay_results = await loop.run_in_executor(
                None, relay_message, envelope.mail_from, envelope.rcpt_tos, raw
            )
            entry = {
                "timestamp": timestamp,
                "mail_from": envelope.mail_from,
                "rcpt_tos":  envelope.rcpt_tos,
                "data":      raw.decode("utf8", errors="replace"),
                "relay":     relay_results,
            }
            received_emails.append(entry)
            all_ok = all(v["ok"] for v in relay_results.values())
            print(f"[SMTP] [{timestamp}] from={envelope.mail_from} relay={'ok' if all_ok else 'FAILED'}")
            return "250 Message accepted for delivery"

    def start_smtp_server():
        import time
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        controller = Controller(RelayHandler(), hostname=SMTP_HOST, port=SMTP_PORT, loop=loop)
        controller.start()
        print(f"[SMTP] aiosmtpd listening on {SMTP_HOST}:{SMTP_PORT} — relay enabled")
        while True:
            time.sleep(60)

else:
    class RelayingSMTPServer(smtpd.SMTPServer):
        def process_message(self, peer, mailfrom, rcpttos, data, **kwargs):
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            raw = data if isinstance(data, bytes) else data.encode()
            relay_results = relay_message(mailfrom, rcpttos, raw)
            received_emails.append({
                "timestamp": timestamp,
                "mail_from": mailfrom,
                "rcpt_tos":  rcpttos,
                "data":      raw.decode("utf8", errors="replace"),
                "relay":     relay_results,
            })

    def start_smtp_server():
        RelayingSMTPServer((SMTP_HOST, SMTP_PORT), None)
        print(f"[SMTP] smtpd listening on {SMTP_HOST}:{SMTP_PORT} — relay enabled")
        asyncore.loop()


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", smtp_host=SMTP_HOST, smtp_port=SMTP_PORT)


@app.route("/send", methods=["POST"])
def send_email():
    try:
        from_name  = request.form.get("from_name", "").strip()
        from_email = request.form.get("from_email", "").strip()
        to         = request.form.get("to", "").strip()
        subject    = request.form.get("subject", "").strip()
        body       = request.form.get("body", "").strip()

        if not from_email or not to or not subject:
            return jsonify({"ok": False, "error": "from_email, to and subject are required"}), 400

        from_addr = email.utils.formataddr((from_name, from_email)) if from_name else from_email
        msg = MIMEMultipart()
        msg["From"]    = from_addr
        msg["To"]      = to
        msg["Subject"] = subject
        msg["Date"]    = email.utils.formatdate(localtime=True)
        msg.attach(MIMEText(body, "plain"))

        for f in request.files.getlist("attachments"):
            if f and f.filename:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{f.filename}"')
                msg.attach(part)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.sendmail(from_email, [to], msg.as_string())

        return jsonify({"ok": True, "message": f"Accepted — relaying to {to}"})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/log")
def get_log():
    return jsonify(received_emails[-50:][::-1])


@app.route("/clear", methods=["POST"])
def clear_log():
    received_emails.clear()
    return jsonify({"ok": True})


# ─── Startup ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    threading.Thread(target=start_smtp_server, daemon=True).start()
    app.run(debug=True, use_reloader=False, port=5000)
