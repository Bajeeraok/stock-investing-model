"""
Send story-change alerts via email (SMTP) or Telegram.
Configure in config.yaml under 'alerts'. If not configured, no alerts are sent.
Only sends when there is at least one story change (no empty digests).
"""
from __future__ import annotations

import smtplib
import urllib.error
import urllib.parse
import urllib.request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_alert_digest(story_changes: list[dict], config: dict, full_report: str | None = None) -> bool:
    """
    Send digest when story changes occur. Returns True if sent, False otherwise.
    story_changes: list of {ticker, story_change, ...}
    config: full config dict; uses config.get("alerts", {})
    full_report: optional full text to include (e.g. portfolio summary)
    """
    if not story_changes:
        return False

    alerts_cfg = config.get("alerts", {}) or {}
    if not alerts_cfg:
        return False

    lines = ["STORY CHANGE ALERTS", "=" * 40]
    for r in story_changes:
        lines.append(f"  {r.get('ticker', '?'):6}  {r.get('story_change', '')}")
    if full_report:
        lines.append("")
        lines.append(full_report)
    body = "\n".join(lines)

    # Try Telegram first, then email
    telegram_ok = _send_telegram(alerts_cfg, body)
    if telegram_ok:
        return True
    email_ok = _send_email(alerts_cfg, body)
    return email_ok


def _send_telegram(cfg: dict, body: str) -> bool:
    """Send via Telegram Bot API. Needs bot_token and chat_id."""
    token = cfg.get("telegram", {}).get("bot_token") or cfg.get("telegram_bot_token")
    chat_id = cfg.get("telegram", {}).get("chat_id") or cfg.get("telegram_chat_id")
    if not token or not chat_id:
        return False
    try:
        # Telegram escape for parse_mode=HTML (keep plain for now - HTML can break long text)
        text = body[:4000]  # Telegram limit
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def _send_email(cfg: dict, body: str) -> bool:
    """Send via SMTP. Needs smtp_host, from_addr, to_addrs, and optionally user/password."""
    email_cfg = cfg.get("email", {}) or {}
    host = email_cfg.get("smtp_host") or cfg.get("smtp_host")
    port = email_cfg.get("smtp_port") or cfg.get("smtp_port") or 587
    user = email_cfg.get("user") or cfg.get("smtp_user")
    password = email_cfg.get("password") or cfg.get("smtp_password")
    from_addr = email_cfg.get("from_addr") or cfg.get("email_from")
    to_addrs = email_cfg.get("to_addrs") or cfg.get("email_to")
    if isinstance(to_addrs, str):
        to_addrs = [to_addrs]
    if not host or not from_addr or not to_addrs:
        return False
    try:
        msg = MIMEMultipart()
        msg["Subject"] = "Stock Model: Story Change Alerts"
        msg["From"] = from_addr
        msg["To"] = ", ".join(to_addrs)
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP(host, port) as smtp:
            smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.sendmail(from_addr, to_addrs, msg.as_string())
        return True
    except Exception:
        return False
