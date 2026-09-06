import os
import unittest

os.environ.update({
    "API_ID": "1", "API_HASH": "test", "BOT_TOKEN": "1:test",
    "DATABASE_URL": "mongodb://127.0.0.1:27017", "SECRET_KEY": "0123456789abcdef0123456789abcdef",
})

from bot.helper.channel_urls import channel_path, channel_slug, resolve_channel_slug


class ChannelUrlTests(unittest.TestCase):
    def test_slug_is_readable_and_does_not_expose_telegram_id(self):
        slug = channel_slug(-1003910587051, "Testing DB")
        self.assertTrue(slug.startswith("testing-db-"))
        self.assertNotIn("3910587051", slug)
        self.assertEqual(f"/c/{slug}", channel_path(-1003910587051, "Testing DB"))

    def test_slug_resolves_only_the_matching_authorized_channel(self):
        channels = [
            {"chat-id": -1003910587051, "title": "Testing DB"},
            {"chat-id": -1002001671856, "title": "Testing DB"},
        ]
        resolved = resolve_channel_slug(channel_slug(-1002001671856, "Testing DB"), channels)
        self.assertEqual(-1002001671856, resolved["chat-id"])
        self.assertIsNone(resolve_channel_slug("testing-db-not-a-real-slug", channels))
