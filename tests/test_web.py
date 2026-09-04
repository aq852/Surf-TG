import os

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
