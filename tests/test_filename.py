import unittest
import os

os.environ.update({
    "API_ID": "1", "API_HASH": "test", "BOT_TOKEN": "1:test",
    "DATABASE_URL": "mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=20",
    "SECRET_KEY": "0123456789abcdef0123456789abcdef",
    "VIEWER_USERNAME": "viewer", "VIEWER_PASSWORD": "viewer-safe-password",
    "PASSWORD_HASH": "", "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD": "admin-safe-password", "ADMIN_PASSWORD_HASH": "",
    "COOKIE_SECURE": "false",
})

from bot.helper.filename import clean_filename


class FilenameCleanupTests(unittest.TestCase):
    def test_removes_links_handles_and_promo_brackets(self):
        value = "Movie.2026.1080p [Join @SpamChannel] https://t.me/spam"
        cleaned = clean_filename(value)
        self.assertEqual("Movie 2026 1080p", cleaned)

    def test_preserves_useful_media_metadata(self):
        self.assertEqual("Show S02E04 2160p HDR", clean_filename("Show.S02E04.2160p.HDR"))

    def test_empty_result_has_safe_fallback(self):
        self.assertEqual("Untitled", clean_filename("https://t.me/spam"))


if __name__ == "__main__":
    unittest.main()
