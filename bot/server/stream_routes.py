import json
import logging
import mimetypes
import secrets
import time
from urllib.parse import quote
from aiohttp import web
from bot.helper.chats import get_chats, get_authorized_chat_ids, post_playlist, posts_chat, posts_db_file
from bot.helper.database import Database
from bot.helper.search import search
from bot.helper.thumbnail import get_image
from bot.telegram import work_loads, multi_clients
from aiohttp_session import get_session
from bot.config import Telegram
from bot.helper.exceptions import FIleNotFound
from bot.helper.index import get_files, posts_file
from bot.server.custom_dl import ByteStreamer
from bot.server.render_template import render_page
from bot.helper.ranges import RangeNotSatisfiable, parse_range, plan_chunks
from bot.helper.security import StreamTokenError, verify_password, verify_stream_token
from bot.helper.cache import rm_cache

from bot.telegram import StreamBot

client_cache = {}
login_attempts = {}

routes = web.RouteTableDef()
db = Database()


def public_chat_id(value: str) -> int:
    if not value.isdigit():
        raise web.HTTPNotFound()
    return int(f"-100{value}")


async def require_authorized_chat(chat_id: int):
    if chat_id not in await get_authorized_chat_ids():
        raise web.HTTPForbidden(text="Channel is not authorized")


@routes.get('/login')
async def login_form(request):
    session = await get_session(request)
    redirect_url = session.get('redirect_url', '/')
    return web.Response(text=await render_page(None, None, route='login', redirect_url=redirect_url), content_type='text/html')


@routes.post('/login')
async def login_route(request):
    session = await get_session(request)
    if 'user' in session:
        raise web.HTTPFound('/')
    data = await request.post()
    username = data.get('username')
    password = data.get('password')
    error_message = None
    remote = request.remote or "unknown"
    now = time.monotonic()
    attempts = [stamp for stamp in login_attempts.get(remote, []) if now - stamp < 15 * 60]
    if len(attempts) >= 10:
        raise web.HTTPTooManyRequests(text="Too many login attempts. Try again later.")

    def credential_matches(candidate_user, expected_user, password_hash, legacy_password):
        if not secrets.compare_digest(candidate_user or "", expected_user or ""):
            return False
        if password_hash:
            return verify_password(password or "", password_hash)
        return secrets.compare_digest(password or "", legacy_password or "")

    valid = credential_matches(username, Telegram.USERNAME, Telegram.PASSWORD_HASH, Telegram.PASSWORD)
    valid = valid or credential_matches(
        username, Telegram.ADMIN_USERNAME, Telegram.ADMIN_PASSWORD_HASH, Telegram.ADMIN_PASSWORD
    )
    if valid:
        login_attempts.pop(remote, None)
        session['user'] = username
        if 'redirect_url' not in session:
            session['redirect_url'] = '/'
        redirect_url = session['redirect_url']
        del session['redirect_url']
        raise web.HTTPFound(redirect_url)
    else:
        attempts.append(now)
        login_attempts[remote] = attempts
        error_message = "Invalid username or password"
    return web.Response(text=await render_page(None, None, route='login', msg=error_message), content_type='text/html')


@routes.post('/logout')
async def logout_route(request):
    session = await get_session(request)
    session.pop('user', None)
    raise web.HTTPFound('/login')


@routes.post('/create')
async def create_route(request):
    session = await get_session(request)
    if (username := session.get('user')) != Telegram.ADMIN_USERNAME:
        return web.json_response({'msg': 'Who the hell you are'})
    data = await request.post()
    folderName = data.get('folderName')
    thumbnail = data.get('thumbnail')
    parent_dir = data.get('parent_dir', 'root')
    parent_dir = parent_dir.split('db=')[-1] if 'db=' in parent_dir else 'root'
    if not folderName or len(folderName) > 120 or len(thumbnail or "") > 2048:
        raise web.HTTPBadRequest(text="Invalid folder data")
    await db.create_folder(parent_dir, folderName, thumbnail)
    if parent_dir == 'root':
        raise web.HTTPFound('/')
    else:
        raise web.HTTPFound(f'/playlist?db={parent_dir}')


@routes.post('/delete')
async def delete_route(request):
    session = await get_session(request)
    if (username := session.get('user')) != Telegram.ADMIN_USERNAME:
        return web.json_response({'msg': 'Who the hell you are'})
    data = await request.json()
    id = data.get('delete_id')
    parent = data.get('parent')
    if not (success := await db.delete(id)):
        raise web.HTTPInternalServerError()
    if parent == 'root':
        raise web.HTTPFound('/')
    else:
        raise web.HTTPFound(f'/playlist?db={parent}')


@routes.post('/edit')
async def editFolder_route(request):
    session = await get_session(request)
    if (username := session.get('user')) != Telegram.ADMIN_USERNAME:
        return web.json_response({'msg': 'Who the hell you are'})
    data = await request.post()
    folderName = data.get('folderName')
    thumbnail = data.get('thumbnail')
    id = data.get('folder_id')
    parent = data.get('parent')
    success = await db.edit(id, folderName, thumbnail)
    if not success:
        raise web.HTTPInternalServerError()
    if parent == 'root':
        raise web.HTTPFound('/')
    else:
        raise web.HTTPFound(f'/playlist?db={parent}')


@routes.post('/edit_post')
async def editPost_route(request):
    session = await get_session(request)
    if (username := session.get('user')) != Telegram.ADMIN_USERNAME:
        return web.json_response({'msg': 'Who the hell you are'})
    data = await request.post()
    fileName = data.get('fileName')
    thumbnail = data.get('filethumbnail')
    id = data.get('file_id')
    parent = data.get('file_folder_id')
    success = await db.edit(id, fileName, thumbnail)
    if not success:
        raise web.HTTPInternalServerError()
    if parent == 'root':
        raise web.HTTPFound('/')
    else:
        raise web.HTTPFound(f'/playlist?db={parent}')


@routes.get('/searchDbFol')
async def searchDbFolder_route(request):
    session = await get_session(request)
    if (username := session.get('user')) != Telegram.ADMIN_USERNAME:
        return web.json_response({'msg': 'Who the hell you are'})
    query = request.query.get('query', '')
    folder_names = await db.search_DbFolder(query)
    return web.json_response(folder_names)


@routes.post('/send')
async def send_route(request):
    session = await get_session(request)
    if session.get('user') != Telegram.ADMIN_USERNAME:
        raise web.HTTPForbidden(text="Administrator access required")
    data = await request.post()
    raw_chat_id = data.get('chatId', '')
    chat_id = public_chat_id(raw_chat_id)
    await require_authorized_chat(chat_id)
    folder_id = data.get('folderId')
    selected_ids = data.get('selectedIds')
    if not all([folder_id, selected_ids]):
        raise web.HTTPBadRequest(text="Missing required data")

    formatted_entries = []
    entries = selected_ids.split(',')
    if len(entries) > 100:
        raise web.HTTPBadRequest(text="Select no more than 100 files")
    for entry in entries:
        try:
            file_id, token, filename, size, file_type, thumbnail = entry.split('|', 5)
            claim = verify_stream_token(Telegram.SECRET_KEY, token)
            if claim.chat_id != chat_id or claim.message_id != int(file_id):
                raise StreamTokenError("media mismatch")
        except (ValueError, StreamTokenError) as exc:
            raise web.HTTPBadRequest(text="Invalid selected file") from exc
        formatted_entries.append({
            'chat_id': chat_id,
            'parent_folder': folder_id,
            'file_id': file_id,
            'hash': token,
            'name': filename[:500],
            'size': size,
            'file_type': file_type,
            'thumbnail': thumbnail,
            'type': 'file'
        })

    json_data = json.dumps(formatted_entries)
    data = json.loads(json_data)
    await db.add_json(data)
    if folder_id == 'root':
        raise web.HTTPFound('/')
    else:
        raise web.HTTPFound(f'/playlist?db={folder_id}')


@routes.get('/reload')
async def reload_route(request):
    session = await get_session(request)
    if (username := session.get('user')) != Telegram.ADMIN_USERNAME:
        return web.json_response({'msg': 'Who the hell you are'})

    chat_id = request.query.get('chatId', '')
    if chat_id == 'home':
        rm_cache()
        raise web.HTTPFound('/')
    else:
        rm_cache(f"-100{chat_id}")
        raise web.HTTPFound(f'/channel/{chat_id}')


@routes.post('/config')
async def editConfig_route(request):
    session = await get_session(request)
    if (username := session.get('user')) != Telegram.ADMIN_USERNAME:
        raise web.HTTPForbidden(text='Administrator access required')
    data = await request.post()
    channel = data.get('channel')
    theme = data.get('theme')
    success = await db.update_config(theme=theme, auth_channel=channel)
    if not success:
        raise web.HTTPInternalServerError()
    raise web.HTTPFound('/')



@routes.get('/')
async def home_route(request):
    session = await get_session(request)
    if username := session.get('user'):
        try:
            channels = await get_chats()
            playlists = await db.get_Dbfolder()
            is_admin = username == Telegram.ADMIN_USERNAME
            phtml = await posts_chat(channels)
            dhtml = await post_playlist(playlists, is_admin=is_admin)
            return web.Response(text=await render_page(None, None, route='home', html=phtml, playlist=dhtml, is_admin=is_admin), content_type='text/html')
        except Exception as e:
            logging.critical(e.with_traceback(None))
            raise web.HTTPInternalServerError(text=str(e)) from e
    else:
        session['redirect_url'] = request.path_qs
        raise web.HTTPFound('/login')


@routes.get('/playlist')
async def playlist_route(request):
    session = await get_session(request)
    if username := session.get('user'):
        try:
            parent_id = request.query.get('db')
            page = request.query.get('page', '1')
            playlists = await db.get_Dbfolder(parent_id, page=page)
            files = await db.get_dbFiles(parent_id, page=page)
            text = await db.get_info(parent_id)
            is_admin = username == Telegram.ADMIN_USERNAME
            dhtml = await post_playlist(playlists, is_admin=is_admin)
            dphtml = await posts_db_file(files, is_admin=is_admin)
            return web.Response(text=await render_page(parent_id, None, route='playlist', playlist=dhtml, database=dphtml, msg=text, is_admin=is_admin), content_type='text/html')
        except Exception as e:
            logging.critical(e.with_traceback(None))
            raise web.HTTPInternalServerError(text=str(e)) from e
    else:
        session['redirect_url'] = request.path_qs
        raise web.HTTPFound('/login')


@routes.get('/search/db/{parent}')
async def dbsearch_route(request):
    session = await get_session(request)
    if username := session.get('user'):
        parent = request.match_info['parent']
        page = request.query.get('page', '1')
        query = request.query.get('q', '')
        is_admin = username == Telegram.ADMIN_USERNAME
        try:
            files = await db.search_dbfiles(id=parent, page=page, query=query)
            dphtml = await posts_db_file(files, is_admin=is_admin)
            name = await db.get_info(parent)
            text = f"{name} - {query}"
            return web.Response(text=await render_page(parent, None, route='playlist', database=dphtml, msg=text, is_admin=is_admin), content_type='text/html')
        except Exception as e:
            logging.critical(e.with_traceback(None))
            raise web.HTTPInternalServerError(text=str(e)) from e
    else:
        session['redirect_url'] = request.path_qs
        raise web.HTTPFound('/login')


@routes.get('/channel/{chat_id}')
async def channel_route(request):
    session = await get_session(request)
    if username := session.get('user'):
        chat_id = public_chat_id(request.match_info['chat_id'])
        await require_authorized_chat(chat_id)
        page = request.query.get('page', '1')
        is_admin = username == Telegram.ADMIN_USERNAME
        try:
            posts = await get_files(chat_id, page=page)
            phtml = await posts_file(posts, chat_id, is_admin=is_admin)
            chat = await StreamBot.get_chat(int(chat_id))
            return web.Response(text=await render_page(None, None, route='index', html=phtml, msg=chat.title, chat_id=str(chat_id).removeprefix("-100"), is_admin=is_admin), content_type='text/html')
        except Exception as e:
            logging.critical(e.with_traceback(None))
            raise web.HTTPInternalServerError(text=str(e)) from e
    else:
        session['redirect_url'] = request.path_qs
        raise web.HTTPFound('/login')


@routes.get('/search/{chat_id}')
async def search_route(request):
    session = await get_session(request)
    if username := session.get('user'):
        chat_id = public_chat_id(request.match_info['chat_id'])
        await require_authorized_chat(chat_id)
        page = request.query.get('page', '1')
        query = request.query.get('q', '')
        is_admin = username == Telegram.ADMIN_USERNAME
        try:
            posts = await search(chat_id, page=page, query=query)
            phtml = await posts_file(posts, chat_id, is_admin=is_admin)
            chat = await StreamBot.get_chat(int(chat_id))
            text = f"{chat.title} - {query}"
            return web.Response(text=await render_page(None, None, route='index', html=phtml, msg=text, chat_id=str(chat_id).removeprefix("-100"), is_admin=is_admin), content_type='text/html')
        except Exception as e:
            logging.critical(e.with_traceback(None))
            raise web.HTTPInternalServerError(text=str(e)) from e
    else:
        session['redirect_url'] = request.path_qs
        raise web.HTTPFound('/login')


@routes.get('/api/thumb/{chat_id}', allow_head=True)
async def get_thumbnail(request):
    session = await get_session(request)
    if not session.get('user'):
        raise web.HTTPUnauthorized(text="Login required")
    raw_chat_id = request.match_info['chat_id']
    chat_id = int(raw_chat_id) if raw_chat_id.startswith("-100") and raw_chat_id[4:].isdigit() else public_chat_id(raw_chat_id)
    await require_authorized_chat(chat_id)
    if message_id := request.query.get('id'):
        img = await get_image(str(chat_id), message_id)
    else:
        img = await get_image(str(chat_id), None)
    response = web.FileResponse(img)
    response.content_type = "image/jpeg"
    return response


@routes.get('/watch/{chat_id}', allow_head=True)
async def stream_handler_watch(request: web.Request):
    session = await get_session(request)
    if username := session.get('user'):
        try:
            chat_id = public_chat_id(request.match_info['chat_id'])
            await require_authorized_chat(chat_id)
            message_id = request.query.get('id')
            stream_token = request.query.get('token', '')
            claim = verify_stream_token(Telegram.SECRET_KEY, stream_token)
            if claim.chat_id != int(chat_id) or claim.message_id != int(message_id):
                raise StreamTokenError("token does not match media")
            return web.Response(text=await render_page(message_id, stream_token, chat_id=chat_id), content_type='text/html')
        except StreamTokenError as e:
            raise web.HTTPForbidden(text=str(e)) from e
        except FIleNotFound as e:
            raise web.HTTPNotFound(text=e.message) from e
        except Exception as e:
            logging.critical(e.with_traceback(None))
            raise web.HTTPInternalServerError(text=str(e)) from e
    else:
        session['redirect_url'] = request.path_qs
        raise web.HTTPFound('/login')


@routes.get('/{chat_id}/{encoded_name}', allow_head=True)
async def stream_handler(request: web.Request):
    try:
        chat_id = public_chat_id(request.match_info['chat_id'])
        message_id = request.query.get('id')
        #name = request.match_info['encoded_name']
        stream_token = request.query.get('token', '')
        return await media_streamer(request, int(chat_id), int(message_id), stream_token)
    except StreamTokenError as e:
        raise web.HTTPForbidden(text=str(e)) from e
    except FIleNotFound as e:
        raise web.HTTPNotFound(text=e.message) from e
    except Exception as e:
        logging.critical(e.with_traceback(None))
        raise web.HTTPInternalServerError(text=str(e))


class_cache = {}


async def media_streamer(request: web.Request, chat_id: int, id: int, stream_token: str):
    claim = verify_stream_token(Telegram.SECRET_KEY, stream_token)
    if claim.chat_id != chat_id or claim.message_id != id:
        raise StreamTokenError("token does not match media")
    range_header = request.headers.get("Range")

    index = min(work_loads, key=work_loads.get)
    faster_client = multi_clients[index]

    if Telegram.MULTI_CLIENT:
        logging.info(f"Client {index} is now serving {request.remote}")

    if faster_client in class_cache:
        tg_connect = class_cache[faster_client]
        logging.debug(f"Using cached ByteStreamer object for client {index}")
    else:
        logging.debug(f"Creating new ByteStreamer object for client {index}")
        tg_connect = ByteStreamer(faster_client)
        class_cache[faster_client] = tg_connect
    logging.debug("before calling get_file_properties")
    file_id = await tg_connect.get_file_properties(chat_id=chat_id, message_id=id)
    logging.debug("after calling get_file_properties")

    file_size = file_id.file_size
    try:
        byte_range, partial = parse_range(range_header, file_size)
    except RangeNotSatisfiable:
        return web.Response(
            status=416,
            text="416: Range not satisfiable",
            headers={"Content-Range": f"bytes */{file_size}"},
        )
    chunk_size = 1024 * 1024
    plan = plan_chunks(byte_range, chunk_size)
    body = tg_connect.yield_file(
        file_id, index, plan.offset, plan.first_cut, plan.last_cut, plan.count, chunk_size
    )

    mime_type = file_id.mime_type
    file_name = file_id.file_name
    disposition = "attachment"

    if mime_type:
        if not file_name:
            try:
                file_name = f"{secrets.token_hex(2)}.{mime_type.split('/')[1]}"
            except (IndexError, AttributeError):
                file_name = f"{secrets.token_hex(2)}.unknown"
    else:
        if file_name:
            mime_type = mimetypes.guess_type(file_id.file_name)[0] or "application/octet-stream"
        else:
            mime_type = "application/octet-stream"
            file_name = f"{secrets.token_hex(2)}.unknown"

    return web.Response(
        status=206 if partial else 200,
        body=body,
        headers={
            "Content-Type": f"{mime_type}",
            "Content-Range": f"bytes {byte_range.start}-{byte_range.end}/{file_size}",
            "Content-Length": str(byte_range.length),
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(file_name)}",
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
