"""
mailer.py — Send the daily portfolio brief PDF via Gmail SMTP.

Reads GMAIL_USER, GMAIL_APP_PASSWORD, and REPORT_EMAIL_TO from .env / environment.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from datetime import date
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent


def _load_env() -> None:
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ[k.strip()] = v.strip()


def send_daily_brief(pdf_path: Path, date_str: str = "") -> None:
    """
    Email the daily brief PDF to REPORT_EMAIL_TO.
    Raises RuntimeError if env vars are missing or SMTP fails.
    """
    _load_env()

    sender   = os.environ.get("GMAIL_USER", "")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    to_addr  = os.environ.get("REPORT_EMAIL_TO", "")

    if not sender or not password or not to_addr:
        raise RuntimeError(
            "Missing GMAIL_USER, GMAIL_APP_PASSWORD, or REPORT_EMAIL_TO in .env"
        )

    if not pdf_path.exists():
        raise RuntimeError(f"PDF not found: {pdf_path}")

    date_label = date_str or date.today().strftime("%B %d, %Y")

    msg = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = to_addr
    msg["Subject"] = f"Portfolio Brief — {date_label}"

    body = (
        f"Daily portfolio brief attached.\n\n"
        f"Date: {date_label}\n"
        f"File: {pdf_path.name}\n\n"
        f"Advisory only. Not financial advice.\n"
    )
    msg.attach(MIMEText(body, "plain"))

    with open(pdf_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        f"attachment; filename={pdf_path.name}",
    )
    msg.attach(part)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender, password)
        server.sendmail(sender, to_addr, msg.as_string())

    print(f"[Mailer] Brief sent to {to_addr}")
