"""
Telegram notification — sends cost + savings info after each wave.

Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("brain_loader.telegram")


class TelegramNotifier:
    """Send notifications via Telegram Bot API."""

    def __init__(self) -> None:
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.token and self.chat_id)

    async def send(self, message: str) -> bool:
        """Send a message to the configured chat."""
        if not self.enabled:
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "parse_mode": "Markdown",
                    },
                )
                response.raise_for_status()
                logger.debug("Telegram notification sent")
                return True
        except Exception as e:
            logger.warning("Failed to send Telegram notification: %s", e)
            return False

    async def send_wave_complete(
        self,
        goal: str,
        cost: float,
        tokens: int,
        yagni_saved: int = 0,
    ) -> bool:
        """Send a formatted wave completion notification."""
        message = (
            f"🧠 *Brain Loader v5*\n"
            f"Goal: {goal[:50]}{'...' if len(goal) > 50 else ''}\n"
            f"Cost: ${cost:.4f}\n"
            f"Tokens: {tokens:,}\n"
        )
        if yagni_saved:
            message += f"💰 YAGNI saved: {yagni_saved:,} tokens\n"
        
        return await self.send(message)
