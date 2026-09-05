import os
import time
from datetime import datetime, timedelta, timezone

# Explicit values keep the smoke tests isolated from a developer's config.env.
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

from aiohttp.test_utils import AioHTTPTestCase
from unittest.mock import AsyncMock, patch

from bot.server import web_server
from bot.server.render_template import render_page
from bot.server.stream_routes import _image_type
from bot.helper.security import hash_password


class WebSmokeTests(AioHTTPTestCase):
    async def get_application(self):
        return await web_server()

    async def test_login_page_and_security_headers(self):
        response = await self.client.get("/login")
        self.assertEqual(response.status, 200)
        text = await response.text()
        self.assertIn("Welcome back", text)
        self.assertIn("AkMovieVerse", text)
        self.assertNotIn("Â", text)
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])

    async def test_cross_site_post_is_rejected(self):
        response = await self.client.post(
            "/login",
            data={"username": "viewer", "password": "viewer-safe-password"},
            headers={"Origin": "https://attacker.example"},
        )
        self.assertEqual(response.status, 403)

    async def test_valid_login_redirects_and_sets_cookie(self):
        origin = str(self.server.make_url("/")).rstrip("/")
        response = await self.client.post(
            "/login",
            data={"username": "viewer", "password": "viewer-safe-password"},
            headers={"Origin": origin},
            allow_redirects=False,
        )
        self.assertEqual(
            response.status,
            302,
            msg=f"history={response.history!r} body={await response.text()!r}",
        )
        self.assertIn("surftg_session", response.cookies)

    async def test_relogin_does_not_silently_keep_old_account(self):
        origin = str(self.server.make_url("/")).rstrip("/")
        first = await self.client.post(
            "/login",
            data={"username": "admin", "password": "admin-safe-password"},
            headers={"Origin": origin},
            allow_redirects=False,
        )
        self.assertEqual(first.status, 302)
        second = await self.client.post(
            "/login",
            data={"username": "viewer", "password": "wrong"},
            headers={"Origin": origin},
            allow_redirects=False,
        )
        self.assertEqual(second.status, 200)
        self.assertIn("Invalid username or password", await second.text())

    async def test_database_backed_account_can_login(self):
        origin = str(self.server.make_url("/")).rstrip("/")
        account = {"username": "member1", "role": "viewer", "tier": "premium"}
        with patch("bot.server.stream_routes.authenticate", AsyncMock(return_value=account)):
            response = await self.client.post(
                "/login",
                data={"username": "member1", "password": "member-password"},
                headers={"Origin": origin},
                allow_redirects=False,
            )
        self.assertEqual(302, response.status)

    async def test_expired_login_session_is_rejected(self):
        origin = str(self.server.make_url("/")).rstrip("/")
        account = {
            "username": "member1",
            "role": "viewer",
            "tier": "premium",
            "expires_at": time.time() - 1,
        }
        with patch("bot.server.stream_routes.authenticate", AsyncMock(return_value=account)):
            response = await self.client.post(
                "/login",
                data={"username": "member1", "password": "member-password"},
                headers={"Origin": origin},
                allow_redirects=False,
            )
        self.assertEqual(302, response.status)
        response = await self.client.get("/", allow_redirects=False)
        self.assertEqual(302, response.status)
        self.assertEqual("/login", response.headers["Location"])

    async def test_admin_can_delete_an_index_row(self):
        origin = str(self.server.make_url("/")).rstrip("/")
        await self.client.post(
            "/login",
            data={"username": "admin", "password": "admin-safe-password"},
            headers={"Origin": origin},
            allow_redirects=False,
        )
        with (
            patch("bot.server.stream_routes.get_authorized_chat_ids", AsyncMock(return_value={-100123})),
            patch("bot.server.stream_routes.db.delete_tgfile", AsyncMock(return_value=1)) as delete,
        ):
            response = await self.client.post(
                "/indexed/delete",
                data={"chat_id": "123", "message_id": "7"},
                headers={"Origin": origin},
                allow_redirects=False,
            )
        self.assertEqual(302, response.status)
        delete.assert_awaited_once_with(-100123, 7)

    async def test_admin_can_delete_all_channel_index_rows(self):
        origin = str(self.server.make_url("/")).rstrip("/")
        await self.client.post(
            "/login",
            data={"username": "admin", "password": "admin-safe-password"},
            headers={"Origin": origin},
            allow_redirects=False,
        )
        with (
            patch("bot.server.stream_routes.get_authorized_chat_ids", AsyncMock(return_value={-100123})),
            patch("bot.server.stream_routes.db.delete_channel_tgfiles", AsyncMock(return_value=8)) as delete_all,
        ):
            response = await self.client.post(
                "/indexed/delete-all",
                data={"chat_id": "123"},
                headers={"Origin": origin},
                allow_redirects=False,
            )
        self.assertEqual(302, response.status)
        delete_all.assert_awaited_once_with(-100123)

    async def test_admin_can_rename_display_title(self):
        origin = str(self.server.make_url("/")).rstrip("/")
        await self.client.post(
            "/login",
            data={"username": "admin", "password": "admin-safe-password"},
            headers={"Origin": origin},
            allow_redirects=False,
        )
        with (
            patch("bot.server.stream_routes.get_authorized_chat_ids", AsyncMock(return_value={-100123})),
            patch("bot.server.stream_routes.db.update_tgfile_title", AsyncMock(return_value=1)) as rename,
        ):
            response = await self.client.post(
                "/indexed/rename",
                data={"chat_id": "123", "message_id": "7", "title": "  Better   Movie Name  "},
                headers={"Origin": origin},
                allow_redirects=False,
            )
        self.assertEqual(302, response.status)
        rename.assert_awaited_once_with(-100123, 7, "Better Movie Name")

    async def test_viewer_cannot_bulk_delete_index(self):
        origin = str(self.server.make_url("/")).rstrip("/")
        await self.client.post(
            "/login",
            data={"username": "viewer", "password": "viewer-safe-password"},
            headers={"Origin": origin},
            allow_redirects=False,
        )
        response = await self.client.post(
            "/indexed/delete-all",
            data={"chat_id": "123"},
            headers={"Origin": origin},
            allow_redirects=False,
        )
        self.assertEqual(403, response.status)

    async def test_member_profile_shows_expiry_and_support(self):
        origin = str(self.server.make_url("/")).rstrip("/")
        account = {"username": "member1", "role": "viewer", "tier": "premium"}
        with patch("bot.server.stream_routes.authenticate", AsyncMock(return_value=account)):
            await self.client.post(
                "/login",
                data={"username": "member1", "password": "member-password"},
                headers={"Origin": origin},
                allow_redirects=False,
            )
        user = {
            "username": "member1",
            "tier": "premium",
            "expires_at": datetime.now(timezone.utc) + timedelta(days=5),
        }
        with (
            patch("bot.server.stream_routes.db.get_user", AsyncMock(return_value=user)),
            patch("bot.server.render_template.db.get_variable", AsyncMock(return_value=None)),
        ):
            response = await self.client.get("/profile")
        html = await response.text()
        self.assertEqual(200, response.status)
        self.assertIn("member1", html)
        self.assertIn("days remaining", html)
        self.assertIn("https://t.me/AK_ownerbot", html)
        self.assertIn("Change password", html)

    async def test_member_can_change_own_password(self):
        origin = str(self.server.make_url("/")).rstrip("/")
        account = {"username": "member1", "role": "viewer", "tier": "free"}
        with patch("bot.server.stream_routes.authenticate", AsyncMock(return_value=account)):
            await self.client.post(
                "/login",
                data={"username": "member1", "password": "current-password"},
                headers={"Origin": origin},
                allow_redirects=False,
            )
        user = {"username": "member1", "password_hash": hash_password("current-password"), "active": True}
        with (
            patch("bot.server.stream_routes.db.get_user", AsyncMock(return_value=user)),
            patch("bot.server.stream_routes.db.change_user_password", AsyncMock(return_value=1)) as change,
        ):
            response = await self.client.post(
                "/profile/password",
                data={"current_password": "current-password", "new_password": "new-safe-password"},
                headers={"Origin": origin},
                allow_redirects=False,
            )
        self.assertEqual(302, response.status)
        self.assertEqual("/profile?changed=1", response.headers["Location"])
        change.assert_awaited_once()
        self.assertEqual("member1", change.await_args.args[0])

    async def test_network_ad_document_is_isolated(self):
        origin = str(self.server.make_url("/")).rstrip("/")
        await self.client.post(
            "/login",
            data={"username": "admin", "password": "admin-safe-password"},
            headers={"Origin": origin},
            allow_redirects=False,
        )
        values = {
            "network_ads_enabled": True,
            "ad_code": '<script src="https://ads.example/tag.js"></script>',
            "ad_provider": "adsterra",
        }
        with patch("bot.server.stream_routes.db.get_variable", AsyncMock(side_effect=lambda key: values.get(key))):
            response = await self.client.get("/ads/network")
        html = await response.text()
        self.assertEqual(200, response.status)
        self.assertIn("https://ads.example/tag.js", html)
        self.assertEqual("SAMEORIGIN", response.headers["X-Frame-Options"])
        self.assertIn("frame-ancestors 'self'", response.headers["Content-Security-Policy"])

    async def test_viewer_html_contains_no_admin_controls(self):
        with patch("bot.server.render_template.db.get_variable", AsyncMock(return_value=None)):
            html = await render_page(
                None, None, route="home", html="", playlist="", is_admin=False
            )
        self.assertNotIn("Library settings", html)
        self.assertNotIn("Create a collection", html)
        self.assertNotIn("ADMIN_START", html)
        self.assertIn("Viewer", html)

    async def test_admin_html_contains_admin_controls(self):
        with patch("bot.server.render_template.db.get_variable", AsyncMock(return_value=None)):
            html = await render_page(
                None, None, route="home", html="", playlist="", is_admin=True
            )
        self.assertIn("Library and advertising settings", html)
        self.assertIn("Viewer and premium accounts", html)
        self.assertIn("Expires on", html)
        self.assertIn("Library and advertising settings", html)
        self.assertIn("Adsterra", html)
        self.assertIn("Monetag", html)
        self.assertIn("Create a collection", html)
        self.assertNotIn("ADMIN_START", html)
        self.assertIn("Administrator", html)

    def test_channel_cover_magic_detection(self):
        self.assertEqual("image/png", _image_type(b"\x89PNG\r\n\x1a\nrest"))
        self.assertEqual("image/jpeg", _image_type(b"\xff\xd8\xffrest"))
        self.assertIsNone(_image_type(b"<svg>unsafe</svg>"))
