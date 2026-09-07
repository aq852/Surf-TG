from os.path import splitext
from html import escape
import re
from bot.config import Telegram
from bot.helper.database import Database
from bot.telegram import StreamBot, UserBot
from bot.helper.file_size import get_readable_file_size
from bot.helper.filename import clean_filename
from bot.helper.cache import get_cache, save_cache
from bot import LOGGER
from bot.helper.security import create_stream_token


QUALITY_PATTERN = re.compile(r"\b(?:2160|1440|1080|720|480|360)p\b|\b4k\b", re.I)
GROUP_NOISE_PATTERN = re.compile(
    r"\b(?:2160|1440|1080|720|480|360)p|\b4k\b|\b(?:web[ .-]?dl|web[ .-]?rip|blu[ .-]?ray|brrip|hdrip|dvdrip|remux)\b|"
    r"\b(?:x26[45]|hevc|avc|h\.?26[45]|10bit|8bit|amzn|nf|dsnp|ddp(?:\s*\d(?:\.\d)?)?|aac|atmos)\b|"
    r"\b(?:hindi|english|tamil|telugu|malayalam|kannada|bengali|dual[ -]?audio|multi[ -]?audio|esub|sub(?:title)?s?)\b",
    re.I,
)


def media_group_key(post):
    """Return a conservative automatic group key or a manual override key."""
    manual = re.sub(r"\s+", " ", str(post.get("group_title") or "").strip())
    if manual:
        return f"manual:{manual.casefold()}", manual
    title = str(post.get("display_title") or post.get("title") or "")
    if not QUALITY_PATTERN.search(title):
        return None, title
    clean = GROUP_NOISE_PATTERN.sub(" ", title)
    clean = re.sub(r"[._\-\[\]()]+", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip(" -")
    return (f"auto:{clean.casefold()}", clean) if len(clean) >= 3 else (None, title)


def media_variant_label(post):
    title = str(post.get("display_title") or post.get("title") or "")
    quality = QUALITY_PATTERN.search(title)
    return quality.group(0).upper() if quality else "Play"

db = Database()


async def get_messages(chat_id, first_message_id, last_message_id, batch_size=200, on_batch=None):
    messages = []
    current_message_id = first_message_id
    while current_message_id <= last_message_id:
        batch_message_ids = list(range(current_message_id, min(current_message_id + batch_size, last_message_id + 1)))
        batch_messages = await StreamBot.get_messages(chat_id, batch_message_ids, replies=0)
        batch_files = []
        for message in batch_messages:
            if message:
                if file := message.video or message.document:
                    title = file.file_name or message.caption or file.file_id
                    title, _ = splitext(title)
                    title = clean_filename(title)
                    batch_files.append({"msg_id": str(message.id), "title": title,
                                        "hash": file.file_unique_id[:6], "size": get_readable_file_size(file.file_size),
                                        "type": file.mime_type, "chat_id": str(chat_id)})
        messages.extend(batch_files)
        if on_batch is not None and batch_files:
            await on_batch(batch_files)
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
        title = clean_filename(title)
        posts.append({"msg_id": post.id, "title": title,
                    "hash": file.file_unique_id[:6], "size": get_readable_file_size(file.file_size), "type": file.mime_type})
    save_cache(chat_id, {"posts": posts}, page)
    return posts

async def posts_file(posts, chat_id, is_admin=False, user_tier="free"):
    phtml = """
            <div class="col">
                
                    <div class="card text-white bg-primary mb-3">
        {admin_checkbox}
                        {open_tag}
                        <img src="/static/placeholder.svg" class="lzy_img card-img-top rounded-top"
                            data-src="{img}" alt="{title}">
                        <div class="card-body p-1">
                            <h6 class="card-title">{title}</h6>
                            <span class="badge bg-warning">{type}</span>
                            <span class="badge bg-info">{size}</span>
                        </div>
                        {close_tag}
                        {admin_controls}
                    </div>
                
            </div>
"""
    cards = []
    for post in posts:
        display_title = str(post.get("display_title") or post["title"])
        access = post.get("access", "free")
        entitled = is_admin or user_tier == "premium" or access != "premium"
        token = create_stream_token(Telegram.SECRET_KEY, int(chat_id), int(post["msg_id"]), ttl=Telegram.STREAM_TOKEN_TTL) if entitled else ""
        public_chat_id = str(chat_id).removeprefix("-100")
        admin_controls = ""
        if is_admin:
            checked = " checked" if post.get("downloadable", True) else ""
            selected = " selected" if access == "premium" else ""
            admin_controls = (
                '<details class="card-admin"><summary>Manage</summary>'
                '<form action="/indexed/settings" method="post">'
                f'<input type="hidden" name="chat_id" value="{public_chat_id}">'
                f'<input type="hidden" name="message_id" value="{int(post["msg_id"])}">'
                '<label>Access</label><select class="form-select" name="access">'
                f'<option value="free">Free</option><option value="premium"{selected}>Premium</option></select>'
                f'<label class="check-label"><input type="checkbox" name="downloadable" value="yes"{checked}> Allow download button</label>'
                '<button class="btn btn-primary btn-sm">Save</button></form>'
            '<form action="/indexed/rename" method="post">'
                f'<input type="hidden" name="chat_id" value="{public_chat_id}">'
                f'<input type="hidden" name="message_id" value="{int(post["msg_id"])}">'
                '<label>Display name</label>'
            f'<input class="form-control" name="title" maxlength="500" value="{escape(display_title, quote=True)}" required>'
            '<button class="btn btn-primary btn-sm">Rename display name</button></form>'
            '<form action="/indexed/group" method="post">'
            f'<input type="hidden" name="chat_id" value="{public_chat_id}">'
            f'<input type="hidden" name="message_id" value="{int(post["msg_id"])}">'
            '<label>Group title (optional)</label>'
            f'<input class="form-control" name="group_title" maxlength="180" value="{escape(str(post.get("group_title") or ""), quote=True)}" placeholder="Automatic grouping">'
            '<button class="btn btn-primary btn-sm">Save grouping</button></form>'
            '<form action="/indexed/delete" method="post" onsubmit="return confirm(\'Remove this indexed file?\')">'
                f'<input type="hidden" name="chat_id" value="{public_chat_id}"><input type="hidden" name="message_id" value="{int(post["msg_id"])}">'
                '<button class="btn btn-danger btn-sm">Delete index</button></form></details>'
            )
        cards.append(phtml.format(
            chat_id=public_chat_id, id=int(post["msg_id"]),
            img=f"/api/thumb/{chat_id}?id={int(post['msg_id'])}",
            title=escape(display_title), hash=token,
            size=escape(str(post['size'])), type=escape(str(post['type'])),
            open_tag=(f'<a href="/watch/{public_chat_id}?id={int(post["msg_id"])}&token={token}">' if entitled else '<button type="button" class="locked-file" data-premium-required>'),
            close_tag='</a>' if entitled else '</button>',
            admin_controls=admin_controls,
            admin_checkbox=(
                '<input type="checkbox" class="form-check-input position-absolute top-0 end-0 m-2" '
                'onchange="checkSendButton()" id="selectCheckbox" '
                f'data-id="{int(post["msg_id"])}|{token}|{escape(display_title, quote=True)}|'
                f'{escape(str(post["size"]), quote=True)}|{escape(str(post["type"]), quote=True)}|'
                f'/api/thumb/{chat_id}?id={int(post["msg_id"])}">'
                if is_admin else ''
            )
        ).replace(
            f'<span class="badge bg-warning">{escape(str(post["type"]))}</span>',
            f'<span class="badge bg-warning">{escape(str(post["type"]))}</span>'
            + ('<span class="badge premium-badge">Premium</span>' if access == "premium" else '')
            + ('<span class="badge">Locked</span>' if not entitled else '')
        ))
    return ''.join(cards)


async def posts_grouped_files(posts, chat_id, is_admin=False, user_tier="free"):
    """Render one card per automatic/manual group, with version choices inside."""
    buckets = {}
    singles = []
    for post in posts:
        key, title = media_group_key(post)
        if key is None:
            singles.append(post)
            continue
        # Never merge matching movie names from two separate Telegram channels.
        key = f'{post.get("chat_id", chat_id)}:{key}'
        bucket = buckets.setdefault(key, {"title": title, "posts": []})
        bucket["posts"].append(post)

    cards = [
        await posts_file([post], int(post.get("chat_id", chat_id)), is_admin=is_admin, user_tier=user_tier)
        for post in singles
    ]
    for bucket in buckets.values():
        variants = bucket["posts"]
        if len(variants) == 1:
            cards.append(await posts_file(variants, chat_id, is_admin=is_admin, user_tier=user_tier))
            continue
        lead = variants[0]
        lead_title = escape(str(bucket["title"]))
        rows = []
        for post in variants:
            post_chat_id = int(post.get("chat_id", chat_id))
            public_chat_id = str(post_chat_id).removeprefix("-100")
            message_id = int(post["msg_id"])
            access = post.get("access", "free")
            entitled = is_admin or user_tier == "premium" or access != "premium"
            token = create_stream_token(Telegram.SECRET_KEY, int(chat_id), message_id, ttl=Telegram.STREAM_TOKEN_TTL) if entitled else ""
            display = escape(str(post.get("display_title") or post["title"]))
            variant = escape(media_variant_label(post))
            open_tag = f'<a href="/watch/{public_chat_id}?id={message_id}&token={token}">' if entitled else '<button type="button" class="locked-file" data-premium-required>'
            close_tag = '</a>' if entitled else '</button>'
            admin_form = (
                '<form class="group-admin" action="/indexed/group" method="post">'
                f'<input type="hidden" name="chat_id" value="{public_chat_id}"><input type="hidden" name="message_id" value="{message_id}">'
                f'<input class="form-control" name="group_title" maxlength="180" value="{escape(str(post.get("group_title") or ""), quote=True)}" placeholder="Group title override">'
                '<button class="btn btn-sm">Save</button></form>' if is_admin else ""
            )
            rows.append(
                f'<div class="group-option">{open_tag}<span><strong>{variant}</strong><small>{display}</small></span>'
                f'<span class="badge">{escape(str(post.get("size", "")))}</span>{close_tag}{admin_form}</div>'
            )
        cards.append(
            '<div class="col"><details class="card media-group"><summary>'
            f'<img src="/api/thumb/{int(lead.get("chat_id", chat_id))}?id={int(lead["msg_id"])}" class="card-img-top" alt="{lead_title}">'
            f'<div class="card-body"><h6 class="card-title">{lead_title}</h6><span class="badge">{len(variants)} versions</span></div>'
            '</summary><div class="group-options">' + ''.join(rows) + '</div></details></div>'
        )
    return ''.join(cards)
