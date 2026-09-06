from os import getenv
import secrets
import re
from dotenv import load_dotenv
from pathlib import Path

if Path("config.env").exists():
    load_dotenv("config.env")

class Telegram:
    THEMES = frozenset({
        "midnight", "cinema", "ocean", "royal", "aurora", "amoled",
        "graphite", "light",
    })
    API_ID = int(getenv("API_ID", "0"))
    API_HASH = getenv("API_HASH", "")
    BOT_TOKEN = getenv("BOT_TOKEN", "")
    PORT = int(getenv("PORT", 8080))
    SESSION_STRING = getenv("SESSION_STRING", "")
    BASE_URL = getenv("BASE_URL", "").rstrip('/')
    DATABASE_URL = getenv("DATABASE_URL", "")
    AUTH_CHANNEL = [channel.strip() for channel in getenv("AUTH_CHANNEL", "").split(",") if channel.strip()]
    ALLOWED_TELEGRAM_USERS = {int(user) for user in getenv("ALLOWED_TELEGRAM_USERS", "").split(",") if user.strip()}
    THEME = getenv("THEME", "midnight").lower()
    USERNAME = getenv("VIEWER_USERNAME", "viewer")
    PASSWORD = getenv("VIEWER_PASSWORD", "")
    ADMIN_USERNAME = getenv("ADMIN_USERNAME", "surfTG")
    ADMIN_PASSWORD = getenv("ADMIN_PASSWORD", "surfTG")
    PASSWORD_HASH = getenv("PASSWORD_HASH", "")
    ADMIN_PASSWORD_HASH = getenv("ADMIN_PASSWORD_HASH", "")
    SECRET_KEY = getenv("SECRET_KEY", "")
    STREAM_TOKEN_TTL = int(getenv("STREAM_TOKEN_TTL", "21600"))
    COOKIE_SECURE = getenv("COOKIE_SECURE", "true").lower() in {"1", "true", "yes", "on"}
    SLEEP_THRESHOLD = int(getenv('SLEEP_THRESHOLD', '60'))
    WORKERS = int(getenv('WORKERS', '10'))
    MULTI_CLIENT = getenv('MULTI_CLIENT', 'False').lower() in {"1", "true", "yes", "on"}
    HIDE_CHANNEL = getenv('HIDE_CHANNEL', 'False').lower() in {"1", "true", "yes", "on"}
    SITE_NAME = getenv("SITE_NAME", "AkMovieVerse").strip() or "AkMovieVerse"
    SITE_CREDIT = getenv("SITE_CREDIT", "By AkMovieVerse").strip()
    AD_URL = getenv("AD_URL", "").strip()
    AD_IMAGE_URL = getenv("AD_IMAGE_URL", "").strip()
    AD_MOBILE_IMAGE_URL = getenv("AD_MOBILE_IMAGE_URL", "").strip()
    SUPPORT_USERNAME = getenv("SUPPORT_USERNAME", "AK_ownerbot").strip().lstrip("@")
    FILENAME_CLEANUP_REGEX = getenv("FILENAME_CLEANUP_REGEX", "").strip()

    @classmethod
    def validate(cls):
        missing = [name for name in ("API_ID", "API_HASH", "BOT_TOKEN", "DATABASE_URL") if not getattr(cls, name)]
        if missing:
            raise RuntimeError(f"Missing required configuration: {', '.join(missing)}")
        if len(cls.SECRET_KEY) < 32:
            raise RuntimeError("SECRET_KEY must be at least 32 random characters")
        if cls.THEME not in cls.THEMES:
            raise RuntimeError(f"THEME must be one of: {', '.join(sorted(cls.THEMES))}")
        if not cls.PASSWORD_HASH and not cls.PASSWORD:
            raise RuntimeError("Set PASSWORD_HASH (recommended) or VIEWER_PASSWORD")
        if not cls.ADMIN_PASSWORD_HASH and cls.ADMIN_PASSWORD in {"", "surfTG"}:
            raise RuntimeError("Set ADMIN_PASSWORD_HASH (recommended) or a non-default ADMIN_PASSWORD")
        for variable, value in (
            ("PASSWORD_HASH", cls.PASSWORD_HASH),
            ("ADMIN_PASSWORD_HASH", cls.ADMIN_PASSWORD_HASH),
        ):
            if value and not value.startswith("pbkdf2_sha256$"):
                raise RuntimeError(
                    f"{variable} contains a plain password. Leave it empty to use the "
                    "plain-password fallback, or generate a real hash with: "
                    "python -m bot.helper.security"
                )
        if cls.FILENAME_CLEANUP_REGEX:
            try:
                re.compile(cls.FILENAME_CLEANUP_REGEX)
            except re.error as exc:
                raise RuntimeError(f"Invalid FILENAME_CLEANUP_REGEX: {exc}") from exc
        if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", cls.SUPPORT_USERNAME):
            raise RuntimeError("SUPPORT_USERNAME must be a valid Telegram username")
