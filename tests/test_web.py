import os

os.environ.setdefault("API_ID", "1")
os.environ.setdefault("API_HASH", "test")
os.environ.setdefault("BOT_TOKEN", "1:test")
os.environ.setdefault("DATABASE_URL", "mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=20")
os.environ.setdefault("SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("VIEWER_PASSWORD", "viewer-safe-password")
os.environ.setdefault("ADMIN_PASSWORD", "admin-safe-password")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("VIEWER_USERNAME", "viewer")
os.environ.setdefault("ADMIN_USERNAME", "admin")

from aiohttp.test_utils import AioHTTPTestCase

from bot.server import web_server


class WebSmokeTests(AioHTTPTestCase):
    async def get_application(self):
        return await web_server()

    async def test_login_page_and_security_headers(self):
        response = await self.client.get("/login")
        self.assertEqual(response.status, 200)
        text = await response.text()
        self.assertIn("Welcome back", text)
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
