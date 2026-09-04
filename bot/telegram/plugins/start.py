import re
from asyncio import sleep
from os.path import splitext

from pyrogram import Client, filters
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from bot import LOGGER
from bot.config import Telegram
from bot.helper.database import Database
from bot.helper.file_size import get_readable_file_size
from bot.helper.index import get_messages
from bot.helper.media import is_media
from bot.telegram import StreamBot


db = Database()


async def authorized_channels() -> set[str]:
    configured = await db.get_variable("auth_channel")
    values = configured.split(",") if configured and configured.strip() else Telegram.AUTH_CHANNEL
    return {str(value).strip() for value in values if str(value).strip()}


@StreamBot.on_message(filters.command("start") & filters.private)
async def start_command(bot: Client, message: Message):
    if "file_" not in (message.text or ""):
        await message.reply("Surf-TG is online. Open your private web library to browse files.")
        return
    if not message.from_user or message.from_user.id not in Telegram.ALLOWED_TELEGRAM_USERS:
        await message.reply("This private file shortcut is not enabled for your Telegram account.")
        return
    try:
        command = message.text.rsplit("_", 1)[-1]
        message_id, encoded_chat = command.split("-", 1)
        chat_id = -int(encoded_chat)
        if str(chat_id) not in await authorized_channels():
            await message.reply("That channel is not authorized.")
            return
        source = await bot.get_messages(chat_id, int(message_id))
        media = is_media(source)
        if not media:
            await message.reply("File not found.")
            return
        await message.reply_cached_media(file_id=media.file_id, caption=f"**{media.file_name or 'Telegram file'}**")
    except (TypeError, ValueError):
        await message.reply("Invalid file shortcut.")


@StreamBot.on_message(filters.command("index"))
async def index_command(bot: Client, message: Message):
    if str(message.chat.id) not in await authorized_channels():
        await message.reply("This channel is not in AUTH_CHANNEL.")
        return
    try:
        wait_message = await message.reply(
            "Indexing this channel now. Avoid uploading new files until it completes."
        )
        files = await get_messages(message.chat.id, 1, message.id)
        if files:
            await db.add_btgfiles(files)
        await wait_message.delete()
        await bot.send_message(message.chat.id, "Indexing complete. New uploads are added automatically.")
    except FloodWait as exc:
        LOGGER.info("Indexing paused for %ss due to Telegram flood control", exc.value)
        await sleep(exc.value)
        await message.reply(
            f"Telegram requested a {exc.value}-second pause. Run /index again afterward.",
            disable_web_page_preview=True,
            parse_mode=ParseMode.MARKDOWN,
        )


@StreamBot.on_message(filters.channel & (filters.document | filters.video))
async def file_receive_handler(bot: Client, message: Message):
    if str(message.chat.id) not in await authorized_channels():
        return
    try:
        file = message.video or message.document
        title = file.file_name or message.caption or file.file_id
        title, _ = splitext(title)
        title = re.sub(r"[.,|_']", " ", title)
        await db.add_tgfiles(
            str(message.chat.id), str(message.id), str(file.file_unique_id),
            title, get_readable_file_size(file.file_size), str(file.mime_type),
        )
    except FloodWait as exc:
        LOGGER.info("Receiver paused for %ss due to Telegram flood control", exc.value)
        await sleep(exc.value)
