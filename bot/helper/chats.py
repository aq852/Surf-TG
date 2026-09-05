from asyncio import gather, create_task
from bot.helper.database import Database
from bot.telegram import StreamBot
from bot.config import Telegram
from html import escape
from bot.helper.security import create_stream_token

db = Database()

async def get_chats():
    AUTH_CHANNEL = await get_authorized_chat_ids()
    return [{"chat-id": chat.id, "title": chat.title or chat.first_name, "type": chat.type.name} for chat in await gather(*[create_task(StreamBot.get_chat(channel_id)) for channel_id in AUTH_CHANNEL])]


async def get_authorized_chat_ids():
    try:
        AUTH_CHANNEL = await db.get_variable('auth_channel')
    except Exception:
        AUTH_CHANNEL = None
    if AUTH_CHANNEL is None or AUTH_CHANNEL.strip() == '':
        AUTH_CHANNEL = Telegram.AUTH_CHANNEL
    else:
        AUTH_CHANNEL = [channel.strip() for channel in AUTH_CHANNEL.split(",")]
    
    return {int(channel_id) for channel_id in AUTH_CHANNEL}


async def posts_chat(channels):
    phtml = """
            <div class="col channel-card">
                <a href="/channel/{cid}">
                    <div class="card profile-card text-white bg-primary mb-2">
                    
                        <div class="img-container text-center"
                            style="width: 145px; height: 145px; display: inline-block; overflow: hidden; position: relative; border-radius: 50%; margin: auto;">
                            <img src="/static/placeholder.svg" class="card-img-top lzy_img"
                                data-src="{img}" alt="{title}"
                                style="object-fit: cover; width: 100%; height: 100%; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);">
                        </div>
            
                        <div class="card-body p-1 text-center">
                            <div>
                                <h6 class="card-title">{title}</h6>
                                <span class="badge bg-warning">{ctype}</span>
                            </div>
                        </div>
                    </div>
                </a>
            </div>
"""
    return ''.join(phtml.format(
        cid=str(channel["chat-id"]).removeprefix("-100"),
        img=f"/api/channel-cover/{channel['chat-id']}",
        title=escape(str(channel["title"])),
        ctype=escape(str(channel['type'])),
    ) for channel in channels)


async def post_playlist(playlists, is_admin=False):
    dhtml = """
    <div class="col">
        <div class="card profile-card text-white bg-primary mb-2">
            <a href="/playlist?db={cid}"><div class="img-container"><img class="lzy_img" data-src="{img}" alt="{title}"></div><div class="card-body"><h6 class="card-title">{title}</h6><span class="badge">Collection</span></div></a>
            {admin_controls}
        </div>
    </div>
    """

    cards = []
    for playlist in playlists:
        cid = str(playlist["_id"])
        img = escape(str(playlist.get("thumbnail", "")), quote=True)
        title = escape(str(playlist["name"]), quote=True)
        parent = escape(str(playlist['parent_folder']), quote=True)
        controls = ''
        if is_admin:
            controls = f'<details style="padding:0 15px 15px"><summary>Edit</summary><form action="/edit" method="post"><input type="hidden" name="folder_id" value="{cid}"><input type="hidden" name="parent" value="{parent}"><label>Name</label><input class="form-control" name="folderName" value="{title}" required><label>Cover URL</label><input class="form-control" name="thumbnail" value="{img}"><div class="actions" style="margin-top:10px"><button class="btn btn-primary btn-sm">Save</button><button type="button" class="btn btn-danger btn-sm" onclick="deleteRecord(\'{cid}\',\'{parent}\')">Delete</button></div></form></details>'
        cards.append(dhtml.format(cid=cid, img=img, title=title, ctype=parent, admin_controls=controls))
    return ''.join(cards)


async def posts_db_file(posts, is_admin=False, user_tier="free"):
    phtml = """
    <div class="col">
        <div class="card text-white bg-primary mb-2">
            {open_tag}<img data-src="{img}" class="card-img-top lzy_img" alt="{title}"><div class="card-body"><h6 class="card-title">{title}</h6><span class="badge">{type}</span>{access_badge}<span class="badge">{size}</span></div>{close_tag}
            {admin_controls}
        </div>
    </div>
"""
    cards = []
    for post in posts:
        chat_id = int(post["chat_id"])
        message_id = int(post["file_id"])
        access = post.get("access", "free")
        entitled = is_admin or user_tier == "premium" or access != "premium"
        token = create_stream_token(Telegram.SECRET_KEY, chat_id, message_id, ttl=Telegram.STREAM_TOKEN_TTL) if entitled else ""
        public_chat_id = str(chat_id).removeprefix("-100")
        cards.append(phtml.format(
            cid=post["_id"], chat_id=public_chat_id, id=message_id,
            img=escape(str(post.get("thumbnail", "")), quote=True), title=escape(str(post["name"])),
            hash=token, size=escape(str(post['size'])), type=escape(str(post['file_type'])),
            ctype=escape(str(post["parent_folder"])),
            open_tag=(f'<a href="/watch/{public_chat_id}?id={message_id}&token={token}">' if entitled else '<div class="locked-file">'),
            close_tag='</a>' if entitled else '</div>',
            access_badge=(
                '<span class="badge premium-badge">Premium</span>' if access == "premium" else ''
            ) + ('<span class="badge">Locked</span>' if not entitled else ''),
            admin_controls=(
                f'<details style="padding:0 15px 15px"><summary>Edit</summary><form action="/edit_post" method="post"><input type="hidden" name="file_id" value="{post["_id"]}"><input type="hidden" name="file_folder_id" value="{escape(str(post["parent_folder"]), quote=True)}"><label>Name</label><input class="form-control" name="fileName" value="{escape(str(post["name"]), quote=True)}" required><label>Cover URL</label><input class="form-control" name="filethumbnail" value="{escape(str(post.get("thumbnail", "")), quote=True)}"><div class="actions" style="margin-top:10px"><button class="btn btn-primary btn-sm">Save</button><button type="button" class="btn btn-danger btn-sm" onclick="deleteRecord(\'{post["_id"]}\',\'{escape(str(post["parent_folder"]), quote=True)}\')">Delete</button></div></form></details>'
                if is_admin else ''
            )
        ))
    return ''.join(cards)
