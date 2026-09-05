import re
import json
from html import escape
from urllib.parse import urlparse
from aiofiles import open as aiopen
from os import path as ospath

from bot import LOGGER
from bot.config import Telegram
from bot.helper.database import Database
from bot.helper.security import StreamTokenError, create_stream_token, verify_stream_token
from bot.helper.file_size import get_readable_file_size
from bot.helper.filename import clean_filename
from bot.server.file_properties import get_file_ids
from bot.telegram import StreamBot

db = Database()

hide_channel = """
                    <style>
                        .hide-channel {
                            display: none;
                        }
                    </style>"""


def _safe_external_url(value):
    parsed = urlparse(value or "")
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _ad_slot():
    target = _safe_external_url(Telegram.AD_URL)
    image = _safe_external_url(Telegram.AD_IMAGE_URL)
    if not Telegram.AD_TITLE or not target:
        return ""
    picture = f'<img src="{escape(image, quote=True)}" alt="Advertisement">' if image else ""
    return (
        '<aside class="ad-slot"><span class="ad-label">Advertisement</span>'
        f'<a href="{escape(target, quote=True)}" target="_blank" rel="nofollow sponsored noopener">'
        f'{picture}<strong>{escape(Telegram.AD_TITLE)}</strong></a></aside>'
    )


async def render_page(id, secure_hash, is_admin=False, html='', playlist='', database='', route='', redirect_url='', msg='', chat_id='', accounts='', downloadable=True, account_role='', display_title=''):
    tpath = ospath.join('bot', 'server', 'template')
    if route == 'login':
        async with aiopen(ospath.join(tpath, 'login_v2.html'), 'r', encoding='utf-8') as f:
            error = f'<div class="alert">{escape(msg)}</div>' if msg else ''
            html = (await f.read()).replace("<!-- ErrorBlock -->", error)
            return _finish_page(html, "midnight", False)
    try:
        theme = await db.get_variable('theme')
    except Exception:
        theme = None
    if theme is None or theme == '':
        theme = Telegram.THEME
    theme = theme if theme in {"midnight", "cinema", "ocean", "light"} else "midnight"
    safe_title = escape(str(msg or ""))
    if route == 'home':
        try:
            auth_channels = await db.get_variable('auth_channel')
        except Exception:
            auth_channels = None
        if not auth_channels:
            auth_channels = ", ".join(Telegram.AUTH_CHANNEL)
        async with aiopen(ospath.join(tpath, 'home.html'), 'r', encoding='utf-8') as f:
            html = (await f.read()).replace("<!-- Print -->", html).replace("<!-- Playlist -->", playlist).replace("<!-- Accounts -->", accounts).replace("<!-- AuthChannels -->", escape(str(auth_channels), quote=True))
            if not is_admin and Telegram.HIDE_CHANNEL:
                html += hide_channel
    elif route == 'playlist':
        async with aiopen(ospath.join(tpath, 'playlist.html'), 'r', encoding='utf-8') as f:
            html = (await f.read()).replace("<!-- Playlist -->", playlist).replace("<!-- Database -->", database).replace("<!-- Title -->", safe_title).replace("<!-- Parent_id -->", escape(str(id or ""), quote=True))
    elif route == 'index':
        async with aiopen(ospath.join(tpath, 'index.html'), 'r', encoding='utf-8') as f:
            html = (await f.read()).replace("<!-- Print -->", html).replace("<!-- Title -->", safe_title).replace("<!-- Chat_id -->", escape(str(chat_id), quote=True))
    if route in {'home', 'playlist', 'index'}:
        if not is_admin:
            html = re.sub(r'<!-- ADMIN_START -->.*?<!-- ADMIN_END -->', '', html, flags=re.DOTALL)
        else:
            html = html.replace('<!-- ADMIN_START -->', '').replace('<!-- ADMIN_END -->', '')
        html = html.replace('<!-- AccountRole -->', account_role or ('Administrator' if is_admin else 'Viewer'))
    else:
        claim = verify_stream_token(Telegram.SECRET_KEY, secure_hash)
        if claim.chat_id != int(chat_id) or claim.message_id != int(id):
            raise StreamTokenError("token does not match media")
        file_data = await get_file_ids(StreamBot, chat_id=int(chat_id), message_id=int(id))
        filename, tag, size = file_data.file_name, file_data.mime_type.split(
            '/')[0].strip(), get_readable_file_size(file_data.file_size)
        if filename is None:
            filename = "Proper Filename is Missing"
        raw_filename = clean_filename(display_title or filename)
        filename = escape(raw_filename)
        if tag == 'video':
            async with aiopen(ospath.join(tpath, 'video.html'), encoding='utf-8') as r:
                poster = f"/api/thumb/{chat_id}?id={id}"
                html = (await r.read()).replace('<!-- Filename -->', filename).replace('<!-- Poster -->', poster).replace('<!-- Size -->', size).replace('<!-- Username -->', StreamBot.me.username)
        else:
            async with aiopen(ospath.join(tpath, 'dl.html'), encoding='utf-8') as r:
                html = (await r.read()).replace('<!-- Filename -->', filename).replace('<!-- Size -->', size).replace('<!-- Username -->', StreamBot.me.username)
        download_token = create_stream_token(
            Telegram.SECRET_KEY, int(chat_id), int(id), ttl=Telegram.STREAM_TOKEN_TTL, scope="download"
        ) if downloadable else ""
        html = html.replace("<!-- DownloadToken -->", download_token)
        html = html.replace("<!-- FilenameJS -->", json.dumps(raw_filename))
        if not downloadable:
            html = re.sub(r'<!-- DOWNLOAD_START -->.*?<!-- DOWNLOAD_END -->', '', html, flags=re.DOTALL)
        else:
            html = html.replace('<!-- DOWNLOAD_START -->', '').replace('<!-- DOWNLOAD_END -->', '')
    return _finish_page(html, theme, is_admin)


def _finish_page(html, theme, is_admin):
    safe_name = escape(Telegram.SITE_NAME)
    safe_credit = escape(Telegram.SITE_CREDIT)
    return (html
        .replace("<!-- Theme -->", theme)
        .replace("<!-- BrandName -->", safe_name)
        .replace("<!-- SiteCredit -->", safe_credit)
        .replace("<!-- AdSlot -->", _ad_slot())
        .replace("<body>", f'<body data-theme="{theme}" data-base-theme="{theme}">')
    )
