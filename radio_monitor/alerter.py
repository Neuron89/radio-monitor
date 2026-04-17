"""Alert system — sends notifications when keywords are detected."""
import logging
import subprocess
import urllib.request
import urllib.parse
import json
from datetime import datetime

log = logging.getLogger(__name__)


class Alerter:
    """Sends alerts via ntfy, webhook, and/or local sound."""

    def __init__(self, config: dict):
        self.alerts = config["alerts"]
        self._last_alert = None
        self._cooldown = 10  # seconds between repeated alerts

    def send(self, text: str, matches: list[dict]):
        """Send alert for matched keywords in transcribed text."""
        now = datetime.now()
        if self._last_alert and (now - self._last_alert).total_seconds() < self._cooldown:
            log.debug("Alert cooldown active, skipping.")
            return

        self._last_alert = now
        keywords = ", ".join(m["keyword"] for m in matches)
        title = f"Radio: {keywords}"
        body = f'"{text}"'

        log.info(f"ALERT: {title} — {body}")

        if self.alerts["ntfy"]["enabled"]:
            self._send_ntfy(title, body)
        if self.alerts.get("sound", {}).get("enabled"):
            self._play_sound()
        if self.alerts.get("webhook", {}).get("enabled"):
            self._send_webhook(title, body, text, matches)

    def _send_ntfy(self, title: str, body: str):
        """Send push notification via ntfy."""
        cfg = self.alerts["ntfy"]
        url = f"{cfg['server']}/{cfg['topic']}"

        headers = {
            "Title": title,
            "Priority": cfg.get("priority", "high"),
            "Tags": cfg.get("tags", "loudspeaker"),
        }

        try:
            req = urllib.request.Request(
                url,
                data=body.encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                log.debug(f"ntfy response: {resp.status}")
        except Exception as e:
            log.error(f"ntfy send failed: {e}")

    def _play_sound(self):
        """Play an alert sound locally."""
        sound_file = self.alerts["sound"].get("file", "")
        if sound_file:
            try:
                subprocess.Popen(
                    ["aplay", "-q", sound_file],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                try:
                    subprocess.Popen(
                        ["paplay", sound_file],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except FileNotFoundError:
                    log.warning("No audio player found (aplay/paplay)")

    def _send_webhook(self, title: str, body: str, text: str, matches: list[dict]):
        """Send alert via webhook POST."""
        url = self.alerts["webhook"]["url"]
        if not url:
            return

        payload = json.dumps({
            "title": title,
            "body": body,
            "transcript": text,
            "matches": matches,
            "timestamp": datetime.now().isoformat(),
        }).encode("utf-8")

        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception as e:
            log.error(f"Webhook send failed: {e}")
