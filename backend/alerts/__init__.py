"""Alerts package (options + macro alert feed)."""

# Alerts: email and Telegram notifications for story changes

from .notifier import send_alert_digest

__all__ = ["send_alert_digest"]
