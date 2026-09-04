import os
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

# Keep module-level Telegram configuration identical to the web smoke tests,
# regardless of unittest's file discovery order.
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
    "COOKIE_SECURE": "false",
})

from bot.helper import index


class IndexingTests(IsolatedAsyncioTestCase):
    async def test_channel_history_is_fetched_in_batches(self):
        async def get_batch(chat_id, message_ids, replies=1):
            self.assertEqual(-100123, chat_id)
            self.assertEqual(0, replies)
            return [
                SimpleNamespace(
                    id=message_id,
                    video=SimpleNamespace(
                        file_name=f"video_{message_id}.mp4",
                        file_id=f"file-{message_id}",
                        file_unique_id=f"unique-{message_id}",
                        file_size=1024,
                        mime_type="video/mp4",
                    ),
                    document=None,
                    caption=None,
                )
                for message_id in message_ids
            ]

        mocked = AsyncMock(side_effect=get_batch)
        with patch.object(index.StreamBot, "get_messages", mocked):
            files = await index.get_messages(-100123, 1, 401)

        self.assertEqual(401, len(files))
        self.assertEqual(3, mocked.await_count)
        self.assertEqual("1", files[0]["msg_id"])
        self.assertEqual("-100123", files[0]["chat_id"])
