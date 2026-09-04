from aiohttp import web
from aiohttp.web import Application
import base64
import hashlib
from cryptography.fernet import Fernet
from aiohttp_session import setup
from aiohttp_session.cookie_storage import EncryptedCookieStorage

from bot.server.stream_routes import routes
from bot.config import Telegram
from bot.helper.database import Database
from pathlib import Path


@web.middleware
async def browser_security(request, handler):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("Origin")
        expected = f"{request.scheme}://{request.host}"
        configured = Telegram.BASE_URL
        if origin and origin not in {expected, configured}:
            raise web.HTTPForbidden(text="Cross-site request rejected")
    response = await handler(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: https:; media-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
    )
    return response

async def web_server():
    web_app = Application(client_max_size=30000000, middlewares=[browser_security])
    key = base64.urlsafe_b64encode(hashlib.sha256(Telegram.SECRET_KEY.encode()).digest())
    setup(web_app, EncryptedCookieStorage(
        Fernet(key),
        cookie_name="surftg_session",
        max_age=12 * 60 * 60,
        secure=Telegram.COOKIE_SECURE,
        httponly=True,
        samesite="Strict",
    ))
    web_app.router.add_static('/static/', path=Path('bot/server/static'), name='static')
    web_app.add_routes(routes)
    web_app.on_cleanup.append(lambda app: _close_database())
    return web_app


async def _close_database():
    Database.close_all()
