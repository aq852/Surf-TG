"""Public, stable URLs for authorized Telegram channels.

Telegram chat IDs stay server-side.  The short suffix prevents two channels
with the same title from receiving the same public path.
"""

import hashlib
import hmac
import re
import unicodedata

from bot.config import Telegram


def channel_slug(chat_id: int, title: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(title or "channel"))
    ascii_title = normalized.encode("ascii", "ignore").decode("ascii").lower()
    base = re.sub(r"[^a-z0-9]+", "-", ascii_title).strip("-")[:48] or "channel"
    digest = hmac.new(
        Telegram.SECRET_KEY.encode("utf-8"), str(int(chat_id)).encode("ascii"), hashlib.sha256
    ).hexdigest()[:10]
    return f"{base}-{digest}"


def channel_path(chat_id: int, title: str) -> str:
    return f"/c/{channel_slug(chat_id, title)}"


def resolve_channel_slug(slug: str, channels: list[dict]) -> dict | None:
    for channel in channels:
        if hmac.compare_digest(channel_slug(int(channel["chat-id"]), channel["title"]), str(slug)):
            return channel
    return None
