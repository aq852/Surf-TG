import asyncio
import tempfile
from time import monotonic
from pathlib import Path

from pyrogram import raw
from pyrogram.file_id import FileId

from bot import LOGGER
from bot.server.custom_dl import ByteStreamer
from bot.telegram import StreamBot

image_cache = {}
STATIC_DIR = Path('bot/server/static')
DEFAULT_THUMBNAIL = STATIC_DIR / 'thumbnail.svg'
# Keep generated previews out of the public static directory. They are served
# only through the authenticated /api/thumb route.
THUMBNAIL_CACHE_DIR = Path(tempfile.gettempdir()) / 'akmovieverse-thumbnails'
_thumbnail_locks: dict[str, asyncio.Lock] = {}
_failed_thumbnails: dict[str, float] = {}
_download_semaphore = asyncio.Semaphore(3)
FAILURE_RETRY_SECONDS = 120


def _thumbnail_lock(cache_key: str) -> asyncio.Lock:
    """Serialize only duplicate requests for the same thumbnail.

    A single global lock made a cold Latest page download every Telegram
    poster one at a time. Separate keys can safely download in parallel.
    """
    lock = _thumbnail_locks.get(cache_key)
    if lock is None:
        lock = asyncio.Lock()
        _thumbnail_locks[cache_key] = lock
    return lock


def _cached_file(cache_key: str) -> Path:
    """Return a distinct on-disk target for every Telegram thumbnail."""
    safe_key = cache_key.replace('-', '_')
    return THUMBNAIL_CACHE_DIR / f"{safe_key}.jpg"


async def _download_thumbnail(file_id: str, cache_key: str) -> Path:
    """Download a thumbnail with limited concurrency and one retry."""
    THUMBNAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = _cached_file(cache_key)
    last_error = None
    for attempt in range(2):
        try:
            async with _download_semaphore:
                # Prefer the same cross-DC session path used by the streamer.
                # Pyrogram's generic download_media can fail on a new container
                # with AUTH_BYTES_INVALID before it retries authorization.
                file = FileId.decode(file_id)
                session = await ByteStreamer.generate_media_session(StreamBot, file)
                location = await ByteStreamer.get_location(file)
                response = await session.send(raw.functions.upload.GetFile(
                    location=location, offset=0, limit=1024 * 1024,
                ))
                content = getattr(response, "bytes", b"")
                if content:
                    target.write_bytes(content)
                    downloaded = str(target)
                else:
                    downloaded = await StreamBot.download_media(file_id, file_name=str(target))
            result = Path(downloaded) if downloaded else target
            if not result.is_file() or result.stat().st_size == 0:
                raise RuntimeError("Telegram did not return a usable thumbnail file")
            return result
        except Exception as exc:
            last_error = exc
            if target.exists():
                target.unlink(missing_ok=True)
            if attempt == 0:
                await asyncio.sleep(0.6)
    raise RuntimeError("Telegram thumbnail download failed after retry") from last_error


def is_default_thumbnail(image_path) -> bool:
    return Path(image_path) == DEFAULT_THUMBNAIL


def refresh_image(chat_id, message_id=None):
    """Forget cached success/failure data so the next request retries Telegram."""
    cache_key = f"{chat_id}-{message_id}" if message_id else f"{chat_id}"
    image_cache.pop(cache_key, None)
    _failed_thumbnails.pop(cache_key, None)
    _cached_file(cache_key).unlink(missing_ok=True)

async def get_image(chat_id, message_id):
    global image_cache
    cache_key = f"{chat_id}-{message_id}" if message_id else f"{chat_id}"
    async with _thumbnail_lock(cache_key):
        cached = image_cache.get(cache_key)
        if cached and Path(cached).is_file():
            return cached
        if _failed_thumbnails.get(cache_key, 0) > monotonic():
            return str(DEFAULT_THUMBNAIL)
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
            _failed_thumbnails.pop(cache_key, None)
            return str(img)
        except Exception as e:
            LOGGER.warning("Thumbnail fallback for %s: %s", cache_key, e)
            # Do not cache a failure as success. It is retried shortly, or
            # immediately when an administrator uses Poster Studio refresh.
            _failed_thumbnails[cache_key] = monotonic() + FAILURE_RETRY_SECONDS
            return str(DEFAULT_THUMBNAIL)
