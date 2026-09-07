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
from bot.helper.chats import post_playlist


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

    async def test_index_batches_can_be_persisted_incrementally(self):
        message = SimpleNamespace(
            id=1,
            video=SimpleNamespace(
                file_name="video.mp4",
                file_id="file-1",
                file_unique_id="unique-1",
                file_size=1024,
                mime_type="video/mp4",
            ),
            document=None,
            caption=None,
        )
        save_batch = AsyncMock()
        with patch.object(index.StreamBot, "get_messages", AsyncMock(return_value=[message])):
            await index.get_messages(-100123, 1, 1, on_batch=save_batch)

        save_batch.assert_awaited_once()
        self.assertEqual("1", save_batch.await_args.args[0][0]["msg_id"])

    async def test_free_viewer_sees_premium_file_as_locked(self):
        post = {"msg_id": "7", "title": "Premium movie", "size": "1GB", "type": "video/mp4", "access": "premium"}
        html = await index.posts_file([post], -100123, user_tier="free")
        self.assertIn("Locked", html)
        self.assertNotIn('/watch/123?id=7', html)

    async def test_admin_gets_index_management_controls(self):
        post = {"msg_id": "7", "title": "Telegram original", "display_title": "Movie", "size": "1GB", "type": "video/mp4"}
        html = await index.posts_file([post], -100123, is_admin=True, user_tier="premium")
        self.assertIn("Delete index", html)
        self.assertIn("Allow download button", html)
        self.assertIn("Rename display name", html)
        self.assertIn('value="Movie"', html)
        self.assertNotIn("Telegram original", html)

    async def test_quality_variants_are_grouped_and_manual_group_is_supported(self):
        posts = [
            {"msg_id": "7", "chat_id": "-100123", "title": "Example Movie 2025 720p Hindi WEB-DL", "size": "1GB", "type": "video/mp4"},
            {"msg_id": "8", "chat_id": "-100123", "title": "Example Movie 2025 1080p English WEB-DL", "size": "2GB", "type": "video/mp4"},
        ]
        html = await index.posts_grouped_files(posts, -100123, is_admin=True, user_tier="premium")
        self.assertIn("2 versions", html)
        self.assertIn("1080P", html)
        self.assertIn("Group title", html)

        manual = {"msg_id": "9", "chat_id": "-100123", "title": "Random uploader title", "group_title": "Example Movie 2025", "size": "2GB", "type": "video/mp4"}
        key, label = index.media_group_key(manual)
        self.assertEqual("manual:example movie 2025", key)
        self.assertEqual("Example Movie 2025", label)

    async def test_free_viewer_sees_premium_collection_as_locked(self):
        html = await post_playlist(
            [{"_id": "507f1f77bcf86cd799439011", "name": "Premium", "thumbnail": "", "parent_folder": "root", "access": "premium"}],
            user_tier="free",
        )
        self.assertIn("Premium", html)
        self.assertIn("Locked", html)
        self.assertNotIn('href="/playlist?db=507f1f77bcf86cd799439011"', html)
