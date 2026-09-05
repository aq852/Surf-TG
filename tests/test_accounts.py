import os
from datetime import datetime, timedelta, timezone
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

os.environ.update({
    "API_ID": "1",
    "API_HASH": "test",
    "BOT_TOKEN": "1:test",
    "DATABASE_URL": "mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=20",
    "SECRET_KEY": "0123456789abcdef0123456789abcdef",
    "VIEWER_USERNAME": "viewer",
    "VIEWER_PASSWORD": "viewer-safe-password",
    "PASSWORD_HASH": "",
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD": "admin-safe-password",
    "ADMIN_PASSWORD_HASH": "",
})

from bot.helper import accounts
from bot.helper.security import hash_password


class AccountExpiryTests(IsolatedAsyncioTestCase):
    async def test_expired_database_account_cannot_login(self):
        user = {
            "username": "expired-member",
            "password_hash": hash_password("strong-password"),
            "tier": "premium",
            "active": True,
            "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
        with patch.object(accounts.db, "get_user", AsyncMock(return_value=user)):
            result = await accounts.authenticate("expired-member", "strong-password")
        self.assertIsNone(result)

    async def test_active_unexpired_database_account_can_login(self):
        user = {
            "username": "current-member",
            "password_hash": hash_password("strong-password"),
            "tier": "premium",
            "active": True,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
        }
        with patch.object(accounts.db, "get_user", AsyncMock(return_value=user)):
            result = await accounts.authenticate("current-member", "strong-password")
        self.assertEqual("premium", result["tier"])

    async def test_disabled_database_account_cannot_login(self):
        user = {
            "username": "disabled-member",
            "password_hash": hash_password("strong-password"),
            "tier": "free",
            "active": False,
        }
        with patch.object(accounts.db, "get_user", AsyncMock(return_value=user)):
            result = await accounts.authenticate("disabled-member", "strong-password")
        self.assertIsNone(result)
