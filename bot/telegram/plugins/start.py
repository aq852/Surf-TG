from asyncio import sleep, create_task
from os.path import splitext
import re

from pyrogram import Client, filters
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from bot import LOGGER
from bot.config import Telegram
from bot.helper.database import Database
from bot.helper.file_size import get_readable_file_size
from bot.helper.filename import clean_filename
from bot.helper.index import get_messages
from bot.helper.media import is_media
from bot.telegram import StreamBot


db = Database()
TELEGRAM_DELIVERY_DELETE_SECONDS = 120 * 60


async def _delete_temporary_delivery(bot: Client, chat_id: int, message_id: int):
    """Best-effort cleanup of a bot-delivered file after the access window."""
    await sleep(TELEGRAM_DELIVERY_DELETE_SECONDS)
    try:
        await bot.delete_messages(chat_id, message_id)
    except Exception as exc:
        LOGGER.warning("Could not delete temporary Telegram delivery %s: %s", message_id, exc)


async def authorized_channels() -> set[str]:
    try:
        configured = await db.get_variable("auth_channel")
    except Exception as exc:
        LOGGER.warning("Could not read AUTH_CHANNEL override from MongoDB: %s", exc)
        configured = None
    if isinstance(configured, str) and configured.strip():
        values = configured.split(",")
    elif configured is not None and not isinstance(configured, str):
        values = configured if isinstance(configured, (list, tuple, set)) else [configured]
    else:
        values = Telegram.AUTH_CHANNEL
    return {str(value).strip() for value in values if str(value).strip()}


def parse_file_shortcut(message: Message) -> tuple[int, int] | None:
    """Parse both normal and deep-link `/start file_<id>-100<chat>` payloads."""
    parts = getattr(message, "command", None) or []
    payload = str(parts[1] if len(parts) > 1 else (message.text or "").partition(" ")[2]).strip()
    match = re.fullmatch(r"file_(\d+)-(-?\d+)", payload)
    if not match:
        return None
    message_id = int(match.group(1))
    encoded_chat = match.group(2)
    if encoded_chat.startswith("-100"):
        chat_id = int(encoded_chat)
    elif encoded_chat.startswith("100"):
        chat_id = -int(encoded_chat)
    else:
        return None
    return message_id, chat_id


@StreamBot.on_message(filters.command("start") & filters.private)
async def start_command(bot: Client, message: Message):
    shortcut = parse_file_shortcut(message)
    if shortcut is None:
        await message.reply(f"{Telegram.SITE_NAME} is online. Open your private web library to browse files.")
        return
    try:
        try:
            delivery_enabled = await db.get_variable("telegram_delivery_enabled")
            delivery_protected = await db.get_variable("telegram_delivery_protected")
        except Exception as exc:
            LOGGER.warning("Could not read Telegram delivery policy: %s", exc)
            delivery_enabled = delivery_protected = None
        if delivery_enabled is False:
            await message.reply("Temporary Telegram delivery is currently disabled by the owner.")
            return
        message_id, chat_id = shortcut
        if str(chat_id) not in await authorized_channels():
            await message.reply("That channel is not authorized.")
            return
        source = await bot.get_messages(chat_id, message_id)
        media = is_media(source)
        if not media:
            await message.reply("File not found.")
            return
        # PyroFork's reply_cached_media does not accept protect_content, while
        # send_cached_media does. Use the latter so the admin protection toggle
        # works instead of raising a TypeError on every protected delivery.
        delivered = await bot.send_cached_media(
            chat_id=message.chat.id,
            file_id=media.file_id,
            caption=f"**{media.file_name or 'Telegram file'}**\n\nTemporary access: this message is deleted after about 120 minutes.",
            protect_content=delivery_protected is not False,
            reply_to_message_id=message.id,
        )
        if delivered:
            create_task(_delete_temporary_delivery(bot, delivered.chat.id, delivered.id))
    except Exception:
        LOGGER.exception("Temporary Telegram delivery failed for shortcut %s", shortcut)
        await message.reply("The file could not be sent right now. Please try again shortly.")


@StreamBot.on_message(filters.command("index"))
async def index_command(bot: Client, message: Message):
    try:
        channels = await authorized_channels()
        LOGGER.info("/index received in channel %s; authorized=%s", message.chat.id, str(message.chat.id) in channels)
        if str(message.chat.id) not in channels:
            await message.reply(
                f"This channel is not authorized. Its ID is `{message.chat.id}`. "
                "Add it to AUTH_CHANNEL and restart the bot.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        wait_message = await message.reply(
            "Indexing this channel now. Avoid uploading new files until it completes."
        )
        indexed = 0

        async def save_batch(batch):
            nonlocal indexed
            indexed += await db.add_btgfiles(batch)

        files = await get_messages(message.chat.id, 1, message.id, on_batch=save_batch)
        await wait_message.delete()
        await bot.send_message(
            message.chat.id,
            f"Indexing complete. {indexed} new file(s) added; {len(files) - indexed} already existed. "
            "New uploads are added automatically.",
        )
    except FloodWait as exc:
        LOGGER.info("Indexing paused for %ss due to Telegram flood control", exc.value)
        await sleep(exc.value)
        await message.reply(
            f"Telegram requested a {exc.value}-second pause. Run /index again afterward.",
            disable_web_page_preview=True,
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        LOGGER.exception("Channel indexing failed for channel %s", message.chat.id)
        try:
            await message.reply(f"Indexing failed. Check the {Telegram.SITE_NAME} terminal for the detailed error.")
        except Exception:
            pass


@StreamBot.on_message(filters.channel & (filters.document | filters.video))
async def file_receive_handler(bot: Client, message: Message):
    try:
        if str(message.chat.id) not in await authorized_channels():
            LOGGER.info("Ignored file from unauthorized channel %s", message.chat.id)
            return
        file = message.video or message.document
        title = file.file_name or message.caption or file.file_id
        title, _ = splitext(title)
        title = clean_filename(title)
        added = await db.add_tgfiles(
            str(message.chat.id), str(message.id), str(file.file_unique_id),
            title, get_readable_file_size(file.file_size), str(file.mime_type),
        )
        LOGGER.info(
            "%s file from channel %s, message %s",
            "Indexed" if added else "Skipped existing",
            message.chat.id,
            message.id,
        )
    except FloodWait as exc:
        LOGGER.info("Receiver paused for %ss due to Telegram flood control", exc.value)
        await sleep(exc.value)
    except Exception:
        LOGGER.exception("Automatic file indexing failed for channel %s, message %s", message.chat.id, message.id)
