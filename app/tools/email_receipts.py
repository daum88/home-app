"""Auto-import Coop e-receipts sent to an email inbox (IMAP).

Flow: you email/share the receipt PDF to your own inbox → the Pi polls IMAP for
unseen emails with PDF attachments → imports each one into the inventory (+ hOn).
Works with Gmail (needs an App Password if you have 2FA).
"""
from __future__ import annotations

import asyncio
import email
import imaplib
from email.header import decode_header
from typing import Any

from .. import config
from .base import ToolError
from . import receipts as receipts_mod


def _configured() -> bool:
    return bool(config.EMAIL_HOST and config.EMAIL_USER and config.EMAIL_PASS)


def _decode(value: str | None) -> str:
    if not value:
        return ""
    out = ""
    for data, enc in decode_header(value) or []:
        if isinstance(data, bytes):
            out += data.decode(enc or "utf-8", errors="replace")
        else:
            out += data
    return out


def _fetch_pdfs() -> list[tuple[str, bytes]]:
    """Download unseen PDF attachments, marking those emails as seen. Blocking."""
    mail = imaplib.IMAP4_SSL(config.EMAIL_HOST, config.EMAIL_PORT)
    mail.login(config.EMAIL_USER, config.EMAIL_PASS)
    mail.select(config.EMAIL_FOLDER)

    typ, data = mail.search(None, "UNSEEN")
    if typ != "OK" or not data[0]:
        mail.logout()
        return []

    results: list[tuple[str, bytes]] = []
    for num in data[0].split():
        try:
            typ, msg_data = mail.fetch(num, "(RFC822)")
            if typ != "OK":
                continue
            message = email.message_from_bytes(msg_data[0][1])
            for part in message.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                filename = _decode(part.get_filename())
                if filename.lower().endswith(".pdf"):
                    payload = part.get_payload(decode=True)
                    if payload:
                        results.append((filename, payload))
                        mail.store(num, "+FLAGS", "\\Seen")
                        break
        except Exception:  # noqa: BLE001 — skip bad emails, keep polling
            continue

    mail.logout()
    return results


async def check_email_receipts() -> dict[str, Any]:
    """Poll the inbox for new receipt PDFs and import them."""
    if not _configured():
        return {"configured": False, "imported": []}

    pdfs = await asyncio.to_thread(_fetch_pdfs)
    imported: list[dict[str, Any]] = []
    for filename, pdf in pdfs:
        try:
            result = await receipts_mod.import_receipt(pdf)
            imported.append({"file": filename, **result})
        except ToolError as err:
            imported.append({"file": filename, "error": err.message})
        except Exception as err:  # noqa: BLE001
            imported.append({"file": filename, "error": str(err)})

    return {"configured": True, "imported": imported}
