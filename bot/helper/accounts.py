"""Authentication helpers for built-in and database-backed accounts."""

import secrets
import asyncio
from datetime import datetime, timedelta, timezone

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


def premium_session_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=12)


async def issue_premium_session(account: dict) -> tuple[str, float]:
    """Create a server-side session for a managed premium account only."""
    session_id = secrets.token_urlsafe(32)
    expires_at = premium_session_expiry()
    await db.create_premium_session(
        account["username"], session_id, account.get("session_limit", 1), expires_at,
    )
    return session_id, expires_at.timestamp()


async def premium_session_is_active(username: str, session_id: str) -> bool:
    return bool(session_id) and await db.premium_session_is_active(username, session_id)


async def revoke_premium_session(session_id: str | None):
    await db.revoke_premium_session(session_id)


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
    if not user or not user.get("active", True):
        return None
    expires_at = user.get("expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            return None
    if not await asyncio.to_thread(verify_password, password or "", user.get("password_hash", "")):
        return None
    return {
        "username": user["username"],
        "role": "viewer",
        "tier": user.get("tier", "free"),
        "expires_at": expires_at.timestamp() if expires_at else None,
        "managed": True,
        "session_limit": max(1, min(int(user.get("session_limit", 1)), 5)),
    }
