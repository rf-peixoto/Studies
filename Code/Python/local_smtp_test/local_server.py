#!/usr/bin/env python3
"""
pip install aiosmtpd==1.6.0 dkimpy pyspf

"""

import asyncio
import os
from aiosmtpd.controller import Controller
from aiosmtpd.handlers import AsyncMessage
from email.parser import BytesParser
from email.policy import default
from datetime import datetime

MAILBOX_DIR = "mailbox"

class SavingHandler(AsyncMessage):
    async def handle_message(self, message):
        # message is an email.message.EmailMessage
        envelope_from = self._envelope.mail_from if hasattr(self, "_envelope") else "(unknown)"
        envelope_rcpt = ", ".join(self._envelope.rcpt_tos) if hasattr(self, "_envelope") else "(unknown)"
        now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        os.makedirs(MAILBOX_DIR, exist_ok=True)
        filename = os.path.join(MAILBOX_DIR, f"msg-{now}-{hash(message)}.eml")
        raw_bytes = message.as_bytes()
        with open(filename, "wb") as f:
            f.write(raw_bytes)
        print("="*80)
        print(f"Saved message to: {filename}")
        print(f"Envelope From (MAIL FROM): {envelope_from}")
        print(f"Envelope Recipients: {envelope_rcpt}")
        print("---- Parsed headers ----")
        for h, v in message.items():
            print(f"{h}: {v}")
        print("---- First 500 bytes of body (decoded) ----")
        payload = message.get_body(preferencelist=('plain', 'html'))
        if payload is not None:
            text = payload.get_content()
            print(text[:500])
        else:
            # fallback to raw bytes preview
            print(raw_bytes[:500])
        print("="*80)

async def run():
    handler = SavingHandler()
    controller = Controller(handler, hostname="127.0.0.1", port=1025)
    controller.start()
    print("Local SMTP server running at 127.0.0.1:1025 — mailbox directory:", MAILBOX_DIR)
    print("Press Ctrl-C to stop.")
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        controller.stop()

if __name__ == "__main__":
    asyncio.run(run())
