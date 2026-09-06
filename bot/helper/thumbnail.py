import asyncio
import tempfile
from pathlib import Path

from bot import LOGGER
from bot.telegram import StreamBot

image_cache = {}
STATIC_DIR = Path('bot/server/static')
DEFAULT_THUMBNAIL = STATIC_DIR / 'thumbnail.jpg'
# Keep generated previews out of the public static directory. They are served
# only through the authenticated /api/thumb route.
THUMBNAIL_CACHE_DIR = Path(tempfile.gettempdir()) / 'akmovieverse-thumbnails'
_thumbnail_lock = asyncio.Lock()


def _cached_file(cache_key: str) -> Path:
    """Return a distinct on-disk target for every Telegram thumbnail."""
    safe_key = cache_key.replace('-', '_')
    return THUMBNAIL_CACHE_DIR / f"{safe_key}.jpg"


async def _download_thumbnail(file_id: str, cache_key: str) -> Path:
    """Download a thumbnail to its own stable path and validate the result."""
    THUMBNAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = _cached_file(cache_key)
    downloaded = await StreamBot.download_media(file_id, file_name=str(target))
    result = Path(downloaded) if downloaded else target
    if not result.is_file() or result.stat().st_size == 0:
        raise RuntimeError("Telegram did not return a usable thumbnail file")
    return result

async def get_image(chat_id, message_id):
    global image_cache
    cache_key = f"{chat_id}-{message_id}" if message_id else f"{chat_id}"
    async with _thumbnail_lock:
        cached = image_cache.get(cache_key)
        if cached and Path(cached).is_file():
            return cached
        try:
            if message_id is None:
                chat = await StreamBot.get_chat(int(chat_id))
                if not chat.photo:
                    raise RuntimeError("Telegram chat has no profile photo")
                img = await _download_thumbnail(str(chat.photo.big_file_id), cache_key)
            else:
                msg = await StreamBot.get_messages(int(chat_id), int(message_id))
                media = msg.video or msg.document
                thumbs = getattr(media, "thumbs", None) if media else None
                if not thumbs:
                    raise RuntimeError("Telegram media has no thumbnail")
                img = await _download_thumbnail(str(thumbs[0].file_id), cache_key)

            image_cache[cache_key] = str(img)
            return str(img)
        except Exception as e:
            LOGGER.warning("Thumbnail fallback for %s: %s", cache_key, e)
            # A valid local image is always returned, so the frontend never
            # renders a broken <img> element for documents without previews.
            image_cache[cache_key] = str(DEFAULT_THUMBNAIL)
            return str(DEFAULT_THUMBNAIL)
