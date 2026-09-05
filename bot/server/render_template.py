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


async def _ad_preferences():
    defaults = {
        "manual_ads_enabled": bool(Telegram.AD_TITLE and Telegram.AD_URL),
        "manual_ad_title": Telegram.AD_TITLE,
        "manual_ad_url": Telegram.AD_URL,
        "manual_ad_image_url": Telegram.AD_IMAGE_URL,
        "manual_ad_placement": "all",
        "network_ads_enabled": False,
        "ad_provider": "adsterra",
        "ad_code": "",
        "ad_height": 100,
        "network_ad_placement": "all",
    }
    for key in tuple(defaults):
        try:
            value = await db.get_variable(key)
        except Exception:
            value = None
        if value is not None:
            defaults[key] = value
    return defaults


def _apply_admin_settings(html, preferences, downloads_enabled):
    return (html
        .replace("<!-- ManualAdsChecked -->", "checked" if preferences["manual_ads_enabled"] else "")
        .replace("<!-- ManualAdTitle -->", escape(str(preferences["manual_ad_title"] or ""), quote=True))
        .replace("<!-- ManualAdUrl -->", escape(str(preferences["manual_ad_url"] or ""), quote=True))
        .replace("<!-- ManualAdImageUrl -->", escape(str(preferences["manual_ad_image_url"] or ""), quote=True))
        .replace("<!-- NetworkAdsChecked -->", "checked" if preferences["network_ads_enabled"] else "")
        .replace("<!-- AdsterraSelected -->", "selected" if preferences["ad_provider"] == "adsterra" else "")
        .replace("<!-- MonetagSelected -->", "selected" if preferences["ad_provider"] == "monetag" else "")
        .replace("<!-- AdHeight -->", escape(str(preferences["ad_height"]), quote=True))
        .replace("<!-- AdCode -->", escape(str(preferences["ad_code"])))
        .replace("<!-- ManualAllSelected -->", "selected" if preferences["manual_ad_placement"] == "all" else "")
        .replace("<!-- ManualHomeSelected -->", "selected" if preferences["manual_ad_placement"] == "home" else "")
        .replace("<!-- ManualChannelSelected -->", "selected" if preferences["manual_ad_placement"] == "channel" else "")
        .replace("<!-- ManualCollectionSelected -->", "selected" if preferences["manual_ad_placement"] == "collection" else "")
        .replace("<!-- ManualPlayerSelected -->", "selected" if preferences["manual_ad_placement"] == "player" else "")
        .replace("<!-- NetworkAllSelected -->", "selected" if preferences["network_ad_placement"] == "all" else "")
        .replace("<!-- NetworkHomeSelected -->", "selected" if preferences["network_ad_placement"] == "home" else "")
        .replace("<!-- NetworkChannelSelected -->", "selected" if preferences["network_ad_placement"] == "channel" else "")
        .replace("<!-- NetworkCollectionSelected -->", "selected" if preferences["network_ad_placement"] == "collection" else "")
        .replace("<!-- NetworkPlayerSelected -->", "selected" if preferences["network_ad_placement"] == "player" else "")
        .replace("<!-- DownloadsEnabled -->", "checked" if downloads_enabled is not False else "")
    )


async def _ad_slot(is_admin=False, placement="home"):
    preferences = await _ad_preferences()
    title = str(preferences["manual_ad_title"] or "").strip()
    target = _safe_external_url(str(preferences["manual_ad_url"] or "").strip())
    image = _safe_external_url(str(preferences["manual_ad_image_url"] or "").strip())
    slots = []
    if preferences["manual_ads_enabled"] and preferences["manual_ad_placement"] in {"all", placement} and title and target:
        picture = f'<img src="{escape(image, quote=True)}" alt="Advertisement">' if image else ""
        slots.append(
            '<aside class="ad-slot manual-ad"><span class="ad-label">Advertisement</span>'
            f'<a href="{escape(target, quote=True)}" target="_blank" rel="nofollow sponsored noopener">'
            f'{picture}<strong>{escape(title)}</strong></a></aside>'
        )
    if preferences["network_ads_enabled"] and preferences["network_ad_placement"] in {"all", placement} and preferences["ad_code"]:
        provider = escape(str(preferences["ad_provider"]).title())
        try:
            height = max(50, min(600, int(preferences["ad_height"])))
        except (TypeError, ValueError):
            height = 100
        admin_help = (
            '<small class="ad-network-help">Only inline banner/native-banner tags draw inside this slot. '
            'Popunder tags have no visible banner; localhost or browser ad blocking can also suppress publisher ads.</small>'
            if is_admin else ""
        )
        slots.append(
            '<aside class="ad-slot network-ad"><span class="ad-label">Advertisement</span>'
            f'<iframe data-network-ad src="/ads/network" title="{provider} advertisement" style="height:{height}px" sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox" '
            f'loading="lazy" referrerpolicy="strict-origin-when-cross-origin" scrolling="no"></iframe>{admin_help}</aside>'
        )
    return "".join(slots)


async def render_page(id, secure_hash, is_admin=False, html='', playlist='', database='', route='', redirect_url='', msg='', chat_id='', accounts='', downloadable=True, account_role='', display_title=''):
    tpath = ospath.join('bot', 'server', 'template')
    if route == 'login':
        async with aiopen(ospath.join(tpath, 'login_v2.html'), 'r', encoding='utf-8') as f:
            error = f'<div class="alert">{escape(msg)}</div>' if msg else ''
            html = (await f.read()).replace("<!-- ErrorBlock -->", error)
            return _finish_page(html, "midnight", False, "")
    try:
        theme = await db.get_variable('theme')
    except Exception:
        theme = None
    if theme is None or theme == '':
        theme = Telegram.THEME
    theme = theme if theme in Telegram.THEMES else "midnight"
    safe_title = escape(str(msg or ""))
    if route == 'home':
        try:
            auth_channels = await db.get_variable('auth_channel')
        except Exception:
            auth_channels = None
        if not auth_channels:
            auth_channels = ", ".join(Telegram.AUTH_CHANNEL)
        async with aiopen(ospath.join(tpath, 'home.html'), 'r', encoding='utf-8') as f:
            view = display_title if display_title in {"channels", "latest"} else "channels"
            html = ((await f.read())
                .replace("<!-- Print -->", html)
                .replace("<!-- Playlist -->", playlist)
                .replace("<!-- Latest -->", database)
                .replace("<!-- ChannelsActive -->", "active" if view == "channels" else "")
                .replace("<!-- LatestActive -->", "active" if view == "latest" else "")
                .replace("<!-- ChannelsHidden -->", "" if view == "channels" else "hidden")
                .replace("<!-- LatestHidden -->", "" if view == "latest" else "hidden"))
            if not is_admin and Telegram.HIDE_CHANNEL:
                html += hide_channel
    elif route == 'admin':
        try:
            auth_channels = await db.get_variable('auth_channel')
        except Exception:
            auth_channels = None
        if not auth_channels:
            auth_channels = ", ".join(Telegram.AUTH_CHANNEL)
        preferences = await _ad_preferences()
        try:
            downloads_enabled = await db.get_variable("downloads_enabled")
        except Exception:
            downloads_enabled = None
        async with aiopen(ospath.join(tpath, 'admin.html'), 'r', encoding='utf-8') as f:
            html = ((await f.read())
                .replace("<!-- Accounts -->", accounts)
                .replace("<!-- AuthChannels -->", escape(str(auth_channels), quote=True)))
            html = _apply_admin_settings(html, preferences, downloads_enabled)
    elif route == 'playlist':
        async with aiopen(ospath.join(tpath, 'playlist.html'), 'r', encoding='utf-8') as f:
            html = (await f.read()).replace("<!-- Playlist -->", playlist).replace("<!-- Database -->", database).replace("<!-- Title -->", safe_title).replace("<!-- Parent_id -->", escape(str(id or ""), quote=True))
    elif route == 'index':
        async with aiopen(ospath.join(tpath, 'index.html'), 'r', encoding='utf-8') as f:
            html = (await f.read()).replace("<!-- Print -->", html).replace("<!-- Title -->", safe_title).replace("<!-- Chat_id -->", escape(str(chat_id), quote=True))
    elif route == 'profile':
        async with aiopen(ospath.join(tpath, 'profile.html'), 'r', encoding='utf-8') as f:
            html = (await f.read()).replace("<!-- Profile -->", html)
    if route in {'home', 'playlist', 'index', 'profile', 'admin'}:
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
    placement = {"home": "home", "index": "channel", "playlist": "collection"}.get(route, "player")
    return _finish_page(html, theme, is_admin, await _ad_slot(is_admin, placement))


def _finish_page(html, theme, is_admin, ad_slot):
    safe_name = escape(Telegram.SITE_NAME)
    safe_credit = escape(Telegram.SITE_CREDIT)
    return (html
        # Versioned local assets ensure phones do not keep an old responsive
        # stylesheet/script after a Koyeb deployment.
        .replace('href="/static/app.css"', 'href="/static/app.css?v=3.1.1"')
        .replace('src="/static/app.js"', 'src="/static/app.js?v=3.1.1"')
        .replace("<!-- Theme -->", theme)
        .replace("<!-- BrandName -->", safe_name)
        .replace("<!-- SiteCredit -->", safe_credit)
        .replace("<!-- AdSlot -->", ad_slot)
        .replace("<html ", f'<html data-theme="{theme}" ')
        .replace("<body>", f'<body data-theme="{theme}" data-base-theme="{theme}">')
    )
