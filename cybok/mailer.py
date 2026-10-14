"""Minimal SMTP mailer. Without SMTP settings, messages are printed to the server console instead."""
import smtplib
import threading
from email.message import EmailMessage

from flask import current_app


def mail_configured():
    return bool(current_app.config.get("MAIL_SERVER"))


def _send(cfg, msg):
    try:
        with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=20) as s:
            if cfg["MAIL_USE_TLS"]:
                s.starttls()
            if cfg["MAIL_USERNAME"]:
                s.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            s.send_message(msg)
    except Exception as exc:  # pragma: no cover - network
        print(f"[Cybok mail] Failed to send e-mail to {msg['To']}: {exc}")


def send_mail(to, subject, body):
    cfg = current_app.config
    if not mail_configured():
        print("\n" + "=" * 70 + f"\n[Cybok mail - SMTP not configured]\nTo: {to}\nSubject: {subject}\n\n{body}\n" + "=" * 70 + "\n",
              flush=True)
        return False
    msg = EmailMessage()
    msg["From"] = cfg["MAIL_FROM"] or cfg["MAIL_USERNAME"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    threading.Thread(target=_send, args=(dict(cfg), msg), daemon=True).start()
    return True
