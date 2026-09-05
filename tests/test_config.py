import unittest
from unittest.mock import patch

from bot.config import Telegram


class ConfigValidationTests(unittest.TestCase):
    def _values(self, **overrides):
        values = {
            "API_ID": 1,
            "API_HASH": "test",
            "BOT_TOKEN": "1:test",
            "DATABASE_URL": "mongodb://localhost/test",
            "SECRET_KEY": "s" * 32,
            "PASSWORD_HASH": "",
            "PASSWORD": "viewer-safe-password",
            "ADMIN_PASSWORD_HASH": "",
            "ADMIN_PASSWORD": "admin-safe-password",
            "FILENAME_CLEANUP_REGEX": "",
            "SUPPORT_USERNAME": "AK_ownerbot",
            "THEME": "midnight",
        }
        values.update(overrides)
        return values

    def test_valid_support_username_and_filename_regex(self):
        with patch.multiple(Telegram, **self._values(FILENAME_CLEANUP_REGEX=r"promo|join")):
            Telegram.validate()

    def test_invalid_support_username_is_rejected(self):
        with patch.multiple(Telegram, **self._values(SUPPORT_USERNAME="bad link")):
            with self.assertRaisesRegex(RuntimeError, "SUPPORT_USERNAME"):
                Telegram.validate()

    def test_premium_theme_is_valid(self):
        with patch.multiple(Telegram, **self._values(THEME="royal")):
            Telegram.validate()

    def test_unknown_theme_is_rejected(self):
        with patch.multiple(Telegram, **self._values(THEME="neon")):
            with self.assertRaisesRegex(RuntimeError, "THEME"):
                Telegram.validate()


if __name__ == "__main__":
    unittest.main()
