from os.path import splitext
import re
from html import escape
from bot.config import Telegram
from bot.helper.database import Database
from bot.telegram import StreamBot, UserBot
from bot.helper.file_size import get_readable_file_size
from bot.helper.cache import get_cache, save_cache
from bot import LOGGER
from bot.helper.security import create_stream_token

db = Database()


async def get_messages(chat_id, first_message_id, last_message_id, batch_size=200):
    messages = []
    current_message_id = first_message_id
    while current_message_id <= last_message_id:
        batch_message_ids = list(range(current_message_id, min(current_message_id + batch_size, last_message_id + 1)))
        batch_messages = await StreamBot.get_messages(chat_id, batch_message_ids, replies=0)
        for message in batch_messages:
            if message:
                if file := message.video or message.document:
                    title = file.file_name or message.caption or file.file_id
                    title, _ = splitext(title)
                    title = re.sub(r'[.,|_\',]', ' ', title)
                    messages.append({"msg_id": str(message.id), "title": title,
                                     "hash": file.file_unique_id[:6], "size": get_readable_file_size(file.file_size),
                                     "type": file.mime_type, "chat_id": str(chat_id)})
        LOGGER.info(
            "Index scan progress for channel %s: %s/%s messages checked, %s files found",
            chat_id,
            min(batch_message_ids[-1], last_message_id),
            last_message_id,
            len(messages),
        )
        current_message_id += batch_size
    return messages


async def get_files(chat_id, page=1):
    if Telegram.SESSION_STRING == '':
        return await db.list_tgfiles(id=chat_id, page=page)
    if cache := get_cache(chat_id, int(page)):
        return cache
    posts = []
    async for post in UserBot.get_chat_history(chat_id=int(chat_id), limit=50, offset=(int(page) - 1) * 50):
        file = post.video or post.document
        if not file:
            continue
        title = file.file_name or post.caption or file.file_id
        title, _ = splitext(title)
        title = re.sub(r'[.,|_\',]', ' ', title)
        posts.append({"msg_id": post.id, "title": title,
                    "hash": file.file_unique_id[:6], "size": get_readable_file_size(file.file_size), "type": file.mime_type})
    save_cache(chat_id, {"posts": posts}, page)
    return posts

async def posts_file(posts, chat_id, is_admin=False):
    phtml = """
            <div class="col">
                
                    <div class="card text-white bg-primary mb-3">
        {admin_checkbox}
                        <img src="/static/placeholder.svg" class="lzy_img card-img-top rounded-top"
                            data-src="{img}" alt="{title}">
                        <a href="/watch/{chat_id}?id={id}&hash={hash}">
                        <div class="card-body p-1">
                            <h6 class="card-title">{title}</h6>
                            <span class="badge bg-warning">{type}</span>
                            <span class="badge bg-info">{size}</span>
                        </div>
                        </a>
                    </div>
                
            </div>
"""
    cards = []
    for post in posts:
        token = create_stream_token(
            Telegram.SECRET_KEY, int(chat_id), int(post["msg_id"]), ttl=Telegram.STREAM_TOKEN_TTL
        )
        cards.append(phtml.format(
            chat_id=str(chat_id).replace("-100", ""), id=int(post["msg_id"]),
            img=f"/api/thumb/{chat_id}?id={int(post['msg_id'])}",
            title=escape(str(post["title"])), hash=token,
            size=escape(str(post['size'])), type=escape(str(post['type'])),
            admin_checkbox=(
                '<input type="checkbox" class="form-check-input position-absolute top-0 end-0 m-2" '
                'onchange="checkSendButton()" id="selectCheckbox" '
                f'data-id="{int(post["msg_id"])}|{token}|{escape(str(post["title"]), quote=True)}|'
                f'{escape(str(post["size"]), quote=True)}|{escape(str(post["type"]), quote=True)}|'
                f'/api/thumb/{chat_id}?id={int(post["msg_id"])}">'
                if is_admin else ''
            )
        ).replace("&hash=", "&token="))
    return ''.join(cards)
