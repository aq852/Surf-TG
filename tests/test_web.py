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

from aiohttp import CookieJar
from aiohttp.test_utils import AioHTTPTestCase, TestClient
from unittest.mock import AsyncMock, patch

from bot.server import web_server
from bot.server.render_template import render_page
from bot.server.stream_routes import _image_type
from bot.helper.security import hash_password


class WebSmokeTests(AioHTTPTestCase):
    async def get_application(self):
        return await web_server()

    async def get_client(self, server):
        # aiohttp 3.14 correctly rejects cookies for a numeric test host unless
        # this explicit test-only jar setting is used. Browser production hosts
        # remain protected by the normal cookie rules.
        return TestClient(server, cookie_jar=CookieJar(unsafe=True))

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

    async def test_admin_can_disable_downloads_globally(self):
        origin = str(self.server.make_url("/")).rstrip("/")
        await self.client.post(
            "/login",
            data={"username": "admin", "password": "admin-safe-password"},
            headers={"Origin": origin},
            allow_redirects=False,
        )
        with patch("bot.server.stream_routes.db.set_config_values", AsyncMock(return_value=True)) as save:
            response = await self.client.post(
                "/admin/download-policy",
                data={},
                headers={"Origin": origin},
                allow_redirects=False,
            )
        self.assertEqual(302, response.status)
        self.assertEqual("/admin#downloads", response.headers["Location"])
        save.assert_awaited_once_with(downloads_enabled=False)

    async def test_viewer_cannot_open_admin_dashboard(self):
        origin = str(self.server.make_url("/")).rstrip("/")
        await self.client.post(
            "/login",
            data={"username": "viewer", "password": "viewer-safe-password"},
            headers={"Origin": origin},
            allow_redirects=False,
        )
        response = await self.client.get("/admin")
        self.assertEqual(403, response.status)

    async def test_free_viewer_cannot_open_premium_collection(self):
        origin = str(self.server.make_url("/")).rstrip("/")
        await self.client.post(
            "/login",
            data={"username": "viewer", "password": "viewer-safe-password"},
            headers={"Origin": origin},
            allow_redirects=False,
        )
        with patch("bot.server.stream_routes.db.collection_requires_premium", AsyncMock(return_value=True)):
            response = await self.client.get("/playlist?db=507f1f77bcf86cd799439011")
        self.assertEqual(403, response.status)

    async def test_home_renders_a_latest_indexed_file(self):
        origin = str(self.server.make_url("/")).rstrip("/")
        await self.client.post(
            "/login",
            data={"username": "viewer", "password": "viewer-safe-password"},
            headers={"Origin": origin},
            allow_redirects=False,
        )
        latest = [{"chat_id": "-100123", "msg_id": "7", "title": "Latest upload", "size": "1 GB", "type": "video/mp4"}]
        with (
            patch("bot.server.stream_routes.get_chats", AsyncMock(return_value=[])),
            patch("bot.server.stream_routes.db.get_Dbfolder", AsyncMock(return_value=[])),
            patch("bot.server.stream_routes.get_authorized_chat_ids", AsyncMock(return_value={-100123})),
            patch("bot.server.stream_routes.db.list_latest_tgfiles", AsyncMock(return_value=latest)),
            patch("bot.server.render_template.db.get_variable", AsyncMock(return_value=None)),
        ):
            response = await self.client.get("/?view=latest")
        self.assertEqual(200, response.status)
        self.assertIn("Latest upload", await response.text())

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

    async def test_sponsor_banner_is_managed_and_rendered_for_free_members(self):
        values = {
            "manual_ads_enabled": True,
            "manual_ad_url": "https://example.com/offer?from=library",
            "manual_ad_desktop_image_url": "https://example.com/banner-desktop.jpg",
            "manual_ad_mobile_image_url": "https://example.com/banner-mobile.jpg",
        }
        with patch(
            "bot.server.render_template.db.get_variable",
            AsyncMock(side_effect=lambda key: values.get(key)),
        ):
            html = await render_page(
                None, None, route="home", html="", playlist="", is_admin=False
            )
        self.assertIn('href="https://example.com/offer?from=library"', html)
        self.assertIn('src="https://example.com/banner-desktop.jpg"', html)
        self.assertIn('srcset="https://example.com/banner-mobile.jpg"', html)
        self.assertIn("sponsor-ad", html)
        self.assertNotIn("<strong>", html)

    async def test_sponsor_banner_is_not_rendered_for_premium_members(self):
        values = {
            "manual_ads_enabled": True,
            "manual_ad_url": "https://example.com/offer",
            "manual_ad_desktop_image_url": "https://example.com/banner.jpg",
        }
        with patch("bot.server.render_template.db.get_variable", AsyncMock(side_effect=lambda key: values.get(key))):
            html = await render_page(None, None, route="home", html="", playlist="", is_premium=True)
        self.assertNotIn("sponsor-ad", html)

    async def test_admin_can_save_manual_ad_settings(self):
        origin = str(self.server.make_url("/")).rstrip("/")
        await self.client.post(
            "/login",
            data={"username": "admin", "password": "admin-safe-password"},
            headers={"Origin": origin},
            allow_redirects=False,
        )
        with (
            patch("bot.server.stream_routes.db.update_config", AsyncMock(return_value=True)) as update,
            patch("bot.server.stream_routes.db.get_variable", AsyncMock(return_value=None)),
        ):
            response = await self.client.post(
                "/config",
                data={
                    "manual_form": "1",
                    "theme": "midnight",
                    "channel": "-100123",
                    "manual_ads_enabled": "yes",
                    "manual_ad_url": "https://example.com/offer",
                    "manual_ad_desktop_image_url": "https://example.com/banner-desktop.jpg",
                    "manual_ad_mobile_image_url": "https://example.com/banner-mobile.jpg",
                    "manual_ad_placement": "all",
                },
                headers={"Origin": origin},
                allow_redirects=False,
            )
        self.assertEqual(302, response.status)
        self.assertEqual("https://example.com/offer", update.await_args.kwargs["manual_ad_url"])
        self.assertEqual("https://example.com/banner-desktop.jpg", update.await_args.kwargs["manual_ad_desktop_image_url"])
        self.assertEqual("all", update.await_args.kwargs["manual_ad_placement"])

    async def test_manual_ad_rejects_non_http_destination(self):
        origin = str(self.server.make_url("/")).rstrip("/")
        await self.client.post(
            "/login",
            data={"username": "admin", "password": "admin-safe-password"},
            headers={"Origin": origin},
            allow_redirects=False,
        )
        with patch("bot.server.stream_routes.db.get_variable", AsyncMock(return_value=None)):
            response = await self.client.post(
                "/config",
                data={
                    "manual_form": "1",
                    "theme": "midnight",
                    "channel": "-100123",
                    "manual_ads_enabled": "yes",
                    "manual_ad_url": "javascript:alert(1)",
                },
                headers={"Origin": origin},
                allow_redirects=False,
            )
        self.assertEqual(400, response.status)

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
                None, None, route="admin", accounts="", is_admin=True
            )
        self.assertIn("Admin dashboard", html)
        self.assertIn("Library settings", html)
        self.assertIn("Viewer & premium accounts", html)
        self.assertIn("Expires on", html)
        self.assertIn("Create collection", html)
        self.assertNotIn("ADMIN_START", html)
        self.assertIn("Administrator", html)
        self.assertIn("Royal Gold", html)
        self.assertIn("Aurora Glass", html)
        self.assertIn("AMOLED Black", html)
        self.assertIn("Graphite Luxe", html)
        self.assertIn("Sponsor banner", html)
        self.assertIn("Desktop poster URL", html)
        self.assertIn("Global downloads", html)

    async def test_saved_premium_theme_is_rendered_before_javascript(self):
        values = {"theme": "royal"}
        with patch(
            "bot.server.render_template.db.get_variable",
            AsyncMock(side_effect=lambda key: values.get(key)),
        ):
            html = await render_page(
                None, None, route="home", html="", playlist="", is_admin=False
            )
        self.assertIn('<html data-theme="royal"', html)
        self.assertIn('<body data-theme="royal" data-base-theme="royal">', html)

    def test_channel_cover_magic_detection(self):
        self.assertEqual("image/png", _image_type(b"\x89PNG\r\n\x1a\nrest"))
        self.assertEqual("image/jpeg", _image_type(b"\xff\xd8\xffrest"))
        self.assertIsNone(_image_type(b"<svg>unsafe</svg>"))
