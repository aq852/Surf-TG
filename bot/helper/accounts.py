"""Authentication helpers for built-in and database-backed accounts."""

import secrets
import asyncio

from bot import LOGGER
from bot.config import Telegram
from bot.helper.database import Database
from bot.helper.security import verify_password


db = Database()


def is_admin(session) -> bool:
    return bool(session.get("user")) and (
        session.get("role") == "admin" or session.get("user") == Telegram.ADMIN_USERNAME
    )


def account_tier(session) -> str:
    return "premium" if is_admin(session) else session.get("tier", "free")


async def authenticate(username: str, password: str):
    if secrets.compare_digest(username or "", Telegram.ADMIN_USERNAME or ""):
        valid = await asyncio.to_thread(verify_password, password, Telegram.ADMIN_PASSWORD_HASH) if Telegram.ADMIN_PASSWORD_HASH else secrets.compare_digest(password or "", Telegram.ADMIN_PASSWORD or "")
        return {"username": username, "role": "admin", "tier": "premium"} if valid else None

    if secrets.compare_digest(username or "", Telegram.USERNAME or ""):
        valid = await asyncio.to_thread(verify_password, password, Telegram.PASSWORD_HASH) if Telegram.PASSWORD_HASH else secrets.compare_digest(password or "", Telegram.PASSWORD or "")
        return {"username": username, "role": "viewer", "tier": "free"} if valid else None

    try:
        user = await db.get_user(username)
    except Exception as exc:
        LOGGER.warning("Database account lookup failed: %s", exc)
        return None
    if not user or not user.get("active", True) or not await asyncio.to_thread(verify_password, password or "", user.get("password_hash", "")):
        return None
    return {"username": user["username"], "role": "viewer", "tier": user.get("tier", "free")}
