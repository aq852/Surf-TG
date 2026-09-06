from aiohttp import web
from aiohttp.web import Application
import base64
import hashlib
import time
from cryptography.fernet import Fernet
from aiohttp_session import get_session, setup
from aiohttp_session.cookie_storage import EncryptedCookieStorage

from bot.server.stream_routes import routes
from bot.config import Telegram
from bot.helper.database import Database
from bot.helper.accounts import premium_session_is_active
from pathlib import Path


IDLE_TIMEOUT_SECONDS = 30 * 60


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


@web.middleware
async def account_expiry(request, handler):
    session = await get_session(request)
    session_id = session.get("premium_session_id")
    # A member must always be able to clear a stale browser session, even if
    # MongoDB is briefly unavailable.
    if session.get("user") and session_id and request.path != "/logout":
        try:
            active = await premium_session_is_active(str(session["user"]), str(session_id))
        except Exception:
            # Do not let a database outage silently bypass premium access control.
            raise web.HTTPServiceUnavailable(text="Premium session validation is temporarily unavailable")
        if not active:
            session.clear()
            if request.method == "GET" and request.path != "/login":
                raise web.HTTPFound("/login")
            raise web.HTTPUnauthorized(text="This premium account was signed in on another device")
    if session.get("user") and request.path != "/logout":
        now = time.time()
        last_activity = float(session.get("last_activity", now))
        if now - last_activity >= IDLE_TIMEOUT_SECONDS:
            session.clear()
            if request.method == "GET" and request.path != "/login":
                raise web.HTTPFound("/login")
            raise web.HTTPUnauthorized(text="Signed out after 30 minutes of inactivity")
        session["last_activity"] = now
    expires_at = session.get("expires_at")
    if session.get("user") and expires_at is not None and float(expires_at) <= time.time():
        session.clear()
        if request.method == "GET" and request.path != "/login":
            raise web.HTTPFound("/login")
        raise web.HTTPUnauthorized(text="Account expired")
    return await handler(request)

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
    web_app.middlewares.append(account_expiry)
    web_app.router.add_static('/static/', path=Path('bot/server/static'), name='static')
    web_app.add_routes(routes)
    web_app.on_cleanup.append(lambda app: _close_database())
    return web_app


async def _close_database():
    Database.close_all()
