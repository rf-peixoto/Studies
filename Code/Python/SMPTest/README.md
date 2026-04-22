# SMTP Dev Mailer

A minimalistic local SMTP test tool. Terminal-styled UI to compose and send emails through a local SMTP server — no external mail service required.

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open: http://localhost:5000

## How it works

- On startup, a local SMTP server is started on **127.0.0.1:1025** (no auth, no TLS).
- The web UI lets you compose and send emails to that server.
- Every message the server receives is captured in memory and visible in the **RECEIVED LOG** tab.
- Attachments are supported and forwarded as MIME parts.

## Notes

- Emails never leave your machine — perfect for development and testing.
- The log resets when the process restarts (in-memory only).
- Port 1025 is used instead of 25 to avoid requiring root privileges.

## Dependencies

| Package     | Purpose                        |
|-------------|--------------------------------|
| flask       | Web framework                  |
| aiosmtpd    | Async SMTP server (preferred)  |

If `aiosmtpd` is unavailable, the app falls back to Python's built-in `smtpd` module.
