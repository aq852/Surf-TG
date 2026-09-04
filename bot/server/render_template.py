import re
from html import escape
from aiofiles import open as aiopen
from os import path as ospath

from bot import LOGGER
from bot.config import Telegram
from bot.helper.database import Database
from bot.helper.security import StreamTokenError, verify_stream_token
from bot.helper.file_size import get_readable_file_size
from bot.server.file_properties import get_file_ids
from bot.telegram import StreamBot

db = Database()

hide_channel = """
                    <style>
                        .hide-channel {
                            display: none;
                        }
                    </style>"""


async def render_page(id, secure_hash, is_admin=False, html='', playlist='', database='', route='', redirect_url='', msg='', chat_id=''):
    tpath = ospath.join('bot', 'server', 'template')
    if route == 'login':
        async with aiopen(ospath.join(tpath, 'login_v2.html'), 'r') as f:
            error = f'<div class="alert">{escape(msg)}</div>' if msg else ''
            return (await f.read()).replace("<!-- ErrorBlock -->", error)
    try:
        theme = await db.get_variable('theme')
    except Exception:
        theme = None
    if theme is None or theme == '':
        theme = Telegram.THEME
    if route == 'home':
        async with aiopen(ospath.join(tpath, 'home.html'), 'r') as f:
            html = (await f.read()).replace("<!-- Print -->", html).replace("<!-- Theme -->", theme.lower()).replace("<!-- Playlist -->", playlist)
            if not is_admin and Telegram.HIDE_CHANNEL:
                html += hide_channel
    elif route == 'playlist':
        async with aiopen(ospath.join(tpath, 'playlist.html'), 'r') as f:
            html = (await f.read()).replace("<!-- Theme -->", theme.lower()).replace("<!-- Playlist -->", playlist).replace("<!-- Database -->", database).replace("<!-- Title -->", msg).replace("<!-- Parent_id -->", id)
    elif route == 'index':
        async with aiopen(ospath.join(tpath, 'index.html'), 'r') as f:
            html = (await f.read()).replace("<!-- Print -->", html).replace("<!-- Theme -->", theme.lower()).replace("<!-- Title -->", msg).replace("<!-- Chat_id -->", chat_id)
    if route in {'home', 'playlist', 'index'}:
        if not is_admin:
            html = re.sub(r'<!-- ADMIN_START -->.*?<!-- ADMIN_END -->', '', html, flags=re.DOTALL)
        else:
            html = html.replace('<!-- ADMIN_START -->', '').replace('<!-- ADMIN_END -->', '')
    else:
        claim = verify_stream_token(Telegram.SECRET_KEY, secure_hash)
        if claim.chat_id != int(chat_id) or claim.message_id != int(id):
            raise StreamTokenError("token does not match media")
        file_data = await get_file_ids(StreamBot, chat_id=int(chat_id), message_id=int(id))
        filename, tag, size = file_data.file_name, file_data.mime_type.split(
            '/')[0].strip(), get_readable_file_size(file_data.file_size)
        if filename is None:
            filename = "Proper Filename is Missing"
        filename = escape(re.sub(r'[,|_\',]', ' ', filename))
        if tag == 'video':
            async with aiopen(ospath.join(tpath, 'video.html')) as r:
                poster = f"/api/thumb/{chat_id}?id={id}"
                html = (await r.read()).replace('<!-- Filename -->', filename).replace("<!-- Theme -->", theme.lower()).replace('<!-- Poster -->', poster).replace('<!-- Size -->', size).replace('<!-- Username -->', StreamBot.me.username)
        else:
            async with aiopen(ospath.join(tpath, 'dl.html')) as r:
                html = (await r.read()).replace('<!-- Filename -->', filename).replace("<!-- Theme -->", theme.lower()).replace('<!-- Size -->', size)
    return html
