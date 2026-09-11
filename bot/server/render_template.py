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
        "manual_ads_enabled": bool(Telegram.AD_URL and Telegram.AD_IMAGE_URL),
        "manual_ad_url": Telegram.AD_URL,
        "manual_ad_desktop_image_url": Telegram.AD_IMAGE_URL,
        "manual_ad_mobile_image_url": Telegram.AD_MOBILE_IMAGE_URL,
        "manual_ad_placement": "all",
    }
    for key in tuple(defaults):
        try:
            value = await db.get_variable(key)
        except Exception:
            value = None
        if value is not None:
            defaults[key] = value
    # One-time compatibility with banners saved by AkMovieVerse 3.1.
    if not defaults["manual_ad_desktop_image_url"]:
        try:
            defaults["manual_ad_desktop_image_url"] = await db.get_variable("manual_ad_image_url") or ""
        except Exception:
            pass
    return defaults


def _apply_admin_settings(html, preferences, downloads_enabled, hide_native_download, secure_link_copy_enabled, telegram_delivery_enabled, telegram_delivery_protected):
    return (html
        .replace("<!-- ManualAdsChecked -->", "checked" if preferences["manual_ads_enabled"] else "")
        .replace("<!-- ManualAdUrl -->", escape(str(preferences["manual_ad_url"] or ""), quote=True))
        .replace("<!-- ManualDesktopImageUrl -->", escape(str(preferences["manual_ad_desktop_image_url"] or ""), quote=True))
        .replace("<!-- ManualMobileImageUrl -->", escape(str(preferences["manual_ad_mobile_image_url"] or ""), quote=True))
        .replace("<!-- ManualAllSelected -->", "selected" if preferences["manual_ad_placement"] == "all" else "")
        .replace("<!-- ManualHomeSelected -->", "selected" if preferences["manual_ad_placement"] == "home" else "")
        .replace("<!-- ManualChannelSelected -->", "selected" if preferences["manual_ad_placement"] == "channel" else "")
        .replace("<!-- ManualCollectionSelected -->", "selected" if preferences["manual_ad_placement"] == "collection" else "")
        .replace("<!-- ManualPlayerSelected -->", "selected" if preferences["manual_ad_placement"] == "player" else "")
        .replace("<!-- DownloadsEnabled -->", "checked" if downloads_enabled is not False else "")
        .replace("<!-- HideNativeDownloadChecked -->", "checked" if hide_native_download else "")
        .replace("<!-- SecureLinkCopyChecked -->", "checked" if secure_link_copy_enabled is not False else "")
        .replace("<!-- TelegramDeliveryChecked -->", "checked" if telegram_delivery_enabled is not False else "")
        .replace("<!-- TelegramProtectionChecked -->", "checked" if telegram_delivery_protected is not False else "")
    )


async def _ad_slot(is_premium=False, placement="home"):
    if is_premium:
        return ""
    preferences = await _ad_preferences()
    target = _safe_external_url(str(preferences["manual_ad_url"] or "").strip())
    desktop_image = _safe_external_url(str(preferences["manual_ad_desktop_image_url"] or "").strip())
    mobile_image = _safe_external_url(str(preferences["manual_ad_mobile_image_url"] or "").strip())
    if preferences["manual_ads_enabled"] and preferences["manual_ad_placement"] in {"all", placement} and target and desktop_image:
        mobile_source = (
            f'<source media="(max-width: 720px)" srcset="{escape(mobile_image, quote=True)}">'
            if mobile_image else ""
        )
        return (
            '<aside class="ad-slot sponsor-ad" data-sponsor-ad><span class="ad-label">Sponsored</span>'
            f'<a href="{escape(target, quote=True)}" target="_blank" rel="nofollow sponsored noopener">'
            f'<picture>{mobile_source}<img src="{escape(desktop_image, quote=True)}" alt="Sponsored" referrerpolicy="no-referrer" data-sponsor-image></picture>'
            '</a></aside>'
        )
    return ""


async def render_page(id, secure_hash, is_admin=False, html='', playlist='', database='', route='', redirect_url='', msg='', chat_id='', channel_path='', cover_version='', accounts='', analytics='', media='', media_channels='', media_query='', tmdb_query='', downloadable=True, account_role='', display_title='', is_premium=False, hide_native_download=False, telegram_delivery_enabled=True, channel_access='free', show_in_latest=True, premium_prompt=False, share_path='', share_enabled=True, latest_query='', poster=''):
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
            view = display_title if display_title in {"channels", "latest"} else "latest"
            html = ((await f.read())
                .replace("<!-- Print -->", html)
                .replace("<!-- Playlist -->", playlist)
                .replace("<!-- Latest -->", database)
                .replace("<!-- LatestQuery -->", escape(str(latest_query), quote=True))
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
        try:
            hide_native_download = bool(await db.get_variable("hide_native_download"))
        except Exception:
            hide_native_download = False
        try:
            secure_link_copy_enabled = await db.get_variable("secure_link_copy_enabled")
        except Exception:
            secure_link_copy_enabled = None
        try:
            telegram_delivery_enabled = await db.get_variable("telegram_delivery_enabled")
        except Exception:
            telegram_delivery_enabled = None
        try:
            telegram_delivery_protected = await db.get_variable("telegram_delivery_protected")
        except Exception:
            telegram_delivery_protected = None
        async with aiopen(ospath.join(tpath, 'admin.html'), 'r', encoding='utf-8') as f:
            html = ((await f.read())
                .replace("<!-- Accounts -->", accounts)
                .replace("<!-- Analytics -->", analytics)
                .replace("<!-- MediaEditor -->", media)
                .replace("<!-- MediaChannels -->", media_channels)
                .replace("<!-- MediaQuery -->", escape(str(media_query or ""), quote=True))
                .replace("<!-- TmdbQuery -->", escape(str(tmdb_query or ""), quote=True))
                .replace("<!-- AuthChannels -->", escape(str(auth_channels), quote=True)))
        html = _apply_admin_settings(html, preferences, downloads_enabled, hide_native_download, secure_link_copy_enabled, telegram_delivery_enabled, telegram_delivery_protected)
    elif route == 'playlist':
        async with aiopen(ospath.join(tpath, 'playlist.html'), 'r', encoding='utf-8') as f:
            html = (await f.read()).replace("<!-- Playlist -->", playlist).replace("<!-- Database -->", database).replace("<!-- Title -->", safe_title).replace("<!-- Parent_id -->", escape(str(id or ""), quote=True))
    elif route == 'index':
        async with aiopen(ospath.join(tpath, 'index.html'), 'r', encoding='utf-8') as f:
            html = ((await f.read()).replace("<!-- Print -->", html).replace("<!-- Title -->", safe_title)
                .replace("<!-- Chat_id -->", escape(str(chat_id), quote=True)).replace("<!-- ChannelPath -->", escape(str(channel_path), quote=True))
                .replace("<!-- CoverVersion -->", escape(str(cover_version), quote=True))
                .replace("<!-- ChannelPremiumSelected -->", " selected" if channel_access == "premium" else "")
                .replace("<!-- ShowInLatestChecked -->", " checked" if show_in_latest else ""))
    elif route == 'profile':
        async with aiopen(ospath.join(tpath, 'profile.html'), 'r', encoding='utf-8') as f:
            html = (await f.read()).replace("<!-- Profile -->", html)
    elif route == 'requests':
        async with aiopen(ospath.join(tpath, 'requests.html'), 'r', encoding='utf-8') as f:
            html = (await f.read()).replace("<!-- Requests -->", html)
    if route in {'home', 'playlist', 'index', 'profile', 'admin', 'requests'}:
        if not is_admin:
            html = re.sub(r'<!-- ADMIN_START -->.*?<!-- ADMIN_END -->', '', html, flags=re.DOTALL)
        else:
            html = html.replace('<!-- ADMIN_START -->', '').replace('<!-- ADMIN_END -->', '')
        html = html.replace('<!-- AccountRole -->', account_role or ('Administrator' if is_admin else 'Viewer'))
        if route != 'requests':
            html = html.replace(
                '<a class="btn btn-sm" href="/profile">Profile</a>',
                '<a class="btn btn-sm" href="/requests">Requests</a><a class="btn btn-sm" href="/profile">Profile</a>',
            )
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
                player_poster = _safe_external_url(str(poster or "")) or f"/api/thumb/{chat_id}?id={id}"
                html = (await r.read()).replace('<!-- Filename -->', filename).replace('<!-- Poster -->', player_poster).replace('<!-- Size -->', size).replace('<!-- Username -->', StreamBot.me.username).replace('<!-- NativeDownloadControl -->', 'controlsList="nodownload noremoteplayback"' if hide_native_download else '')
        else:
            async with aiopen(ospath.join(tpath, 'dl.html'), encoding='utf-8') as r:
                html = (await r.read()).replace('<!-- Filename -->', filename).replace('<!-- Size -->', size).replace('<!-- Username -->', StreamBot.me.username)
        download_token = create_stream_token(
            Telegram.SECRET_KEY, int(chat_id), int(id), ttl=Telegram.STREAM_TOKEN_TTL, scope="download"
        ) if downloadable else ""
        # Desktop VLC cannot carry this site's browser session cookie. Give the
        # generated M3U a separate, signed, short-lived stream-only token.
        vlc_token = create_stream_token(
            Telegram.SECRET_KEY, int(chat_id), int(id), ttl=Telegram.STREAM_TOKEN_TTL, scope="vlc"
        )
        html = html.replace("<!-- DownloadToken -->", download_token)
        html = html.replace("<!-- VlcToken -->", vlc_token)
        html = html.replace("<!-- SharePath -->", escape(share_path, quote=True))
        if not share_enabled:
            html = re.sub(r'<!-- COPY_START -->.*?<!-- COPY_END -->', '', html, flags=re.DOTALL)
        else:
            html = html.replace('<!-- COPY_START -->', '').replace('<!-- COPY_END -->', '')
        html = html.replace("<!-- FilenameJS -->", json.dumps(raw_filename))
        if not downloadable:
            html = re.sub(r'<!-- DOWNLOAD_START -->.*?<!-- DOWNLOAD_END -->', '', html, flags=re.DOTALL)
        else:
            html = html.replace('<!-- DOWNLOAD_START -->', '').replace('<!-- DOWNLOAD_END -->', '')
        if not telegram_delivery_enabled:
            html = re.sub(r'<!-- TELEGRAM_START -->.*?<!-- TELEGRAM_END -->', '', html, flags=re.DOTALL)
        else:
            html = html.replace('<!-- TELEGRAM_START -->', '').replace('<!-- TELEGRAM_END -->', '')
    placement = {"home": "home", "index": "channel", "playlist": "collection"}.get(route, "player")
    return _finish_page(html, theme, is_admin, await _ad_slot(is_premium or is_admin, placement), is_premium=is_premium, premium_prompt=premium_prompt, idle_timeout=route != 'login')


def _finish_page(html, theme, is_admin, ad_slot, *, is_premium=False, premium_prompt=False, idle_timeout=False):
    safe_name = escape(Telegram.SITE_NAME)
    safe_credit = escape(Telegram.SITE_CREDIT)
    body_options = " data-idle-timeout=\"1800\"" if idle_timeout else ""
    if premium_prompt:
        body_options += " data-show-premium-prompt=\"1\""
    premium_modal = ""
    if not is_admin and not is_premium:
        premium_modal = (
            '<div class="premium-modal" data-premium-modal hidden role="dialog" aria-modal="true" aria-labelledby="premiumTitle">'
            '<div class="premium-modal-card"><button class="modal-close" type="button" data-premium-close aria-label="Close">×</button>'
            '<div class="eyebrow">Premium content</div><h2 id="premiumTitle">Unlock this content</h2>'
            '<p class="muted">This channel or video is available for Premium members only. Contact the owner to buy Premium access.</p>'
            f'<div class="actions"><a class="btn btn-primary" href="https://t.me/{escape(Telegram.SUPPORT_USERNAME, quote=True)}" target="_blank" rel="noopener">Contact @{escape(Telegram.SUPPORT_USERNAME)}</a>'
            '<button class="btn" type="button" data-premium-close>Not now</button></div></div></div>'
        )
    return (html
        # Versioned local assets ensure phones do not keep an old responsive
        # stylesheet/script after a Koyeb deployment.
        .replace('href="/static/app.css"', 'href="/static/app.css?v=3.2.5"')
        .replace('src="/static/app.js"', 'src="/static/app.js?v=3.2.5"')
        .replace("<!-- Theme -->", theme)
        .replace("<!-- BrandName -->", safe_name)
        .replace("<!-- SiteCredit -->", safe_credit)
        .replace("<!-- AdSlot -->", ad_slot)
        .replace('</body>', premium_modal + '</body>')
        .replace("<html ", f'<html data-theme="{theme}" ')
        .replace("<body>", f'<body data-theme="{theme}" data-base-theme="{theme}"{body_options}>')
    )
