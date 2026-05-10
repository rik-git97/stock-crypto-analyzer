"""Render the weekly brief as HTML and (optionally) email it via SMTP.

SMTP env vars (all optional — if any missing, email step is skipped):
- SCA_SMTP_HOST, SCA_SMTP_PORT, SCA_SMTP_USER, SCA_SMTP_PASS, SCA_EMAIL_TO, SCA_EMAIL_FROM
"""
from __future__ import annotations
import os, smtplib, ssl
from email.message import EmailMessage
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES = Path(__file__).resolve().parents[1] / "reporting" / "templates"


def render_brief(context: dict) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)),
                      autoescape=select_autoescape(["html"]))
    return env.get_template("live_brief.html.j2").render(b=context)


def send_email(html: str, subject: str, to: str | None = None) -> bool:
    host = os.environ.get("SCA_SMTP_HOST")
    port = os.environ.get("SCA_SMTP_PORT")
    user = os.environ.get("SCA_SMTP_USER")
    pwd = os.environ.get("SCA_SMTP_PASS")
    sender = os.environ.get("SCA_EMAIL_FROM", user)
    receiver = to or os.environ.get("SCA_EMAIL_TO")
    if not all([host, port, user, pwd, receiver, sender]):
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = receiver
    msg.set_content("HTML brief attached. View in an HTML-capable mail client.")
    msg.add_alternative(html, subtype="html")
    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, int(port)) as s:
        s.starttls(context=ctx)
        s.login(user, pwd)
        s.send_message(msg)
    return True
