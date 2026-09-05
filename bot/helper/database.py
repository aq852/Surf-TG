from pymongo import DESCENDING, MongoClient, UpdateOne
from bson import ObjectId
from datetime import datetime, timezone
from bot.config import Telegram
import re
import asyncio


class Database:
    _clients = {}

    def __init__(self):
        self.mongodb_uri = Telegram.DATABASE_URL

    @property
    def mongo_client(self):
        if self.mongodb_uri not in self._clients:
            self._clients[self.mongodb_uri] = MongoClient(self.mongodb_uri)
        return self._clients[self.mongodb_uri]

    @property
    def db(self):
        return self.mongo_client["surftg"]

    @property
    def collection(self):
        return self.db["playlist"]

    @property
    def config(self):
        return self.db["config"]

    @property
    def files(self):
        return self.db["files"]

    @property
    def channel_settings(self):
        return self.db["channel_settings"]

    @property
    def users(self):
        return self.db["users"]

    @classmethod
    def close_all(cls):
        for client in cls._clients.values():
            client.close()
        cls._clients.clear()

    async def create_folder(self, parent_id, folder_name, thumbnail, access="free"):
        folder = {"parent_folder": parent_id, "name": folder_name,
                  "thumbnail": thumbnail, "type": "folder", "access": access}
        await asyncio.to_thread(self.collection.insert_one, folder)

    async def delete(self, document_id):
        return await asyncio.to_thread(self._delete_sync, document_id)

    def _delete_sync(self, document_id):
        try:
            has_child_documents = self.collection.count_documents(
                {'parent_folder': document_id}) > 0
            if has_child_documents:
                result = self.collection.delete_many(
                    {'parent_folder': document_id})
            result = self.collection.delete_one({'_id': ObjectId(document_id)})
            return result.deleted_count > 0
        except Exception as e:
            print(f'An error occurred: {e}')
            return False

    async def edit(self, id, name, thumbnail, access=None):
        changes = {"name": name, "thumbnail": thumbnail}
        if access in {"free", "premium"}:
            changes["access"] = access
        result = await asyncio.to_thread(self.collection.update_one, {"_id": ObjectId(id)}, {
            "$set": changes})
        return result.modified_count > 0

    async def get_folder(self, folder_id):
        if not folder_id or folder_id == "root":
            return None
        try:
            return await asyncio.to_thread(self.collection.find_one, {"_id": ObjectId(folder_id), "type": "folder"})
        except Exception:
            return None

    async def collection_requires_premium(self, folder_id):
        """Honor access on a collection and each of its parent collections."""
        current = str(folder_id or "root")
        visited = set()
        while current != "root" and current not in visited:
            visited.add(current)
            folder = await self.get_folder(current)
            if not folder:
                return False
            if folder.get("access", "free") == "premium":
                return True
            current = str(folder.get("parent_folder", "root"))
        return False

    async def search_DbFolder(self, query):
        words = re.findall(r'\w+', query.lower())
        regex_pattern = '.*'.join(f'(?=.*{re.escape(word)})' for word in words)
        regex_query = {'$regex': f'.*{regex_pattern}.*', '$options': 'i'}
        myquery = {'type': 'folder', 'name': regex_query}
        mydoc = await asyncio.to_thread(lambda: list(self.collection.find(myquery).sort('_id', DESCENDING)))
        return [{'_id': str(x['_id']), 'name': x['name']} for x in mydoc]

    async def add_json(self, data):
        await asyncio.to_thread(self.collection.insert_many, data)

    async def get_Dbfolder(self, parent_id="root", page=1, per_page=50):
        query = {"parent_folder": parent_id, "type": "folder"} if parent_id != 'root' else {
            "parent_folder": 'root', "type": "folder"}
        if parent_id != 'root':
            offset = (int(page) - 1) * per_page
            return await asyncio.to_thread(lambda: list(self.collection.find(query).skip(offset).limit(per_page)))
        else:
            return await asyncio.to_thread(lambda: list(self.collection.find(query)))

    async def get_dbFiles(self, parent_id=None, page=1, per_page=50):
        query = {"parent_folder": parent_id, "type": "file"}
        offset = (int(page) - 1) * per_page
        return await asyncio.to_thread(lambda: list(self.collection.find(query).sort(
            'file_id', DESCENDING).skip(offset).limit(per_page)))

    async def list_latest_tgfiles(self, chat_ids, page=1, per_page=48):
        ids = []
        for chat_id in chat_ids:
            ids.extend([str(chat_id), int(chat_id)])
        offset = (int(page) - 1) * per_page
        return await asyncio.to_thread(
            lambda: list(self.files.find({"chat_id": {"$in": ids}}).sort("_id", DESCENDING).skip(offset).limit(per_page))
        )

    async def get_info(self, id):
        query = {'_id': ObjectId(id)}
        if document := await asyncio.to_thread(self.collection.find_one, query):
            return document.get('name', None)
        else:
            return None

    async def search_dbfiles(self, id, query, page=1, per_page=50):
        words = re.findall(r'\w+', query.lower())
        regex_pattern = '.*'.join(f'(?=.*{re.escape(word)})' for word in words)
        regex_query = {'$regex': f'.*{regex_pattern}.*', '$options': 'i'}
        query = {'type': 'file', 'parent_folder': id, 'name': regex_query}
        offset = (int(page) - 1) * per_page
        return await asyncio.to_thread(lambda: list(self.collection.find(query).sort(
            'file_id', DESCENDING).skip(offset).limit(per_page)))

    async def update_config(self, theme, auth_channel, **settings):
        bot_id = Telegram.BOT_TOKEN.split(":", 1)[0]
        values = {"theme": theme, "auth_channel": auth_channel, **settings}
        config = await asyncio.to_thread(self.config.find_one, {"_id": bot_id})
        if config is None:
            result = await asyncio.to_thread(self.config.insert_one,
                {"_id": bot_id, **values})
            return result.inserted_id is not None
        else:
            result = await asyncio.to_thread(self.config.update_one, {"_id": bot_id}, {
                "$set": values})
            return result.acknowledged

    async def set_config_values(self, **settings):
        bot_id = Telegram.BOT_TOKEN.split(":", 1)[0]
        result = await asyncio.to_thread(
            self.config.update_one,
            {"_id": bot_id},
            {"$set": settings},
            upsert=True,
        )
        return result.acknowledged

    async def get_variable(self, key):
        bot_id = Telegram.BOT_TOKEN.split(":", 1)[0]
        config = await asyncio.to_thread(self.config.find_one, {"_id": bot_id})
        return config.get(key) if config is not None else None

    async def list_tgfiles(self, id, page=1, per_page=50):
        # Indexers persist Telegram identifiers as strings. Accept legacy integer
        # rows too so upgrades do not make an existing library disappear.
        query = {'chat_id': {'$in': [str(id), int(id)]}}
        offset = (int(page) - 1) * per_page
        return await asyncio.to_thread(lambda: list(self.files.find(query).sort(
            'msg_id', DESCENDING).skip(offset).limit(per_page)))

    async def get_tgfile(self, chat_id, message_id):
        return await asyncio.to_thread(
            self.files.find_one,
            {
                "chat_id": {"$in": [str(chat_id), int(chat_id)]},
                "msg_id": {"$in": [str(message_id), int(message_id)]},
            },
        )

    async def delete_tgfile(self, chat_id, message_id):
        result = await asyncio.to_thread(
            self.files.delete_many,
            {
                "chat_id": {"$in": [str(chat_id), int(chat_id)]},
                "msg_id": {"$in": [str(message_id), int(message_id)]},
            },
        )
        return result.deleted_count

    async def delete_channel_tgfiles(self, chat_id):
        result = await asyncio.to_thread(
            self.files.delete_many,
            {"chat_id": {"$in": [str(chat_id), int(chat_id)]}},
        )
        return result.deleted_count

    async def update_tgfile_title(self, chat_id, message_id, title):
        result = await asyncio.to_thread(
            self.files.update_many,
            {
                "chat_id": {"$in": [str(chat_id), int(chat_id)]},
                "msg_id": {"$in": [str(message_id), int(message_id)]},
            },
            {"$set": {"display_title": title}},
        )
        await asyncio.to_thread(
            self.collection.update_many,
            {
                "chat_id": {"$in": [str(chat_id), int(chat_id)]},
                "file_id": {"$in": [str(message_id), int(message_id)]},
                "type": "file",
            },
            {"$set": {"name": title}},
        )
        return result.matched_count

    async def update_tgfile_settings(self, chat_id, message_id, access, downloadable):
        result = await asyncio.to_thread(
            self.files.update_many,
            {
                "chat_id": {"$in": [str(chat_id), int(chat_id)]},
                "msg_id": {"$in": [str(message_id), int(message_id)]},
            },
            {"$set": {"access": access, "downloadable": bool(downloadable)}},
        )
        await asyncio.to_thread(
            self.collection.update_many,
            {
                "chat_id": {"$in": [str(chat_id), int(chat_id)]},
                "file_id": {"$in": [str(message_id), int(message_id)]},
                "type": "file",
            },
            {"$set": {"access": access, "downloadable": bool(downloadable)}},
        )
        return result.matched_count

    async def add_tgfiles(self, chat_id, file_id, hash, name, size, file_type):
        numeric_file_id = int(file_id)
        file = {"chat_id": str(chat_id), "msg_id": numeric_file_id,
                "hash": hash, "title": name, "size": size, "type": file_type}
        result = await asyncio.to_thread(
            self.files.update_one,
            {
                "chat_id": {"$in": [str(chat_id), int(chat_id)]},
                "msg_id": {"$in": [str(file_id), numeric_file_id]},
            },
            {
                "$set": file,
                "$setOnInsert": {"access": "free", "downloadable": True},
            },
            upsert=True,
        )
        return result.upserted_id is not None


    async def search_tgfiles(self, id, query, page=1, per_page=50):
        words = re.findall(r'\w+', query.lower())
        regex_pattern = '.*'.join(f'(?=.*{re.escape(word)})' for word in words)
        regex_query = {'$regex': f'.*{regex_pattern}.*', '$options': 'i'}
        query = {
            'chat_id': {'$in': [str(id), int(id)]},
            '$or': [{'title': regex_query}, {'display_title': regex_query}],
        }
        offset = (int(page) - 1) * per_page
        return await asyncio.to_thread(lambda: list(self.files.find(query).sort(
            'msg_id', DESCENDING).skip(offset).limit(per_page)))
    
    async def add_btgfiles(self, data):
        operations = [
            UpdateOne(
                {
                    "chat_id": {"$in": [str(file["chat_id"]), int(file["chat_id"])]},
                    "msg_id": {"$in": [str(file["msg_id"]), int(file["msg_id"])]},
                },
                {
                    "$set": {
                        **file,
                        "chat_id": str(file["chat_id"]),
                        "msg_id": int(file["msg_id"]),
                    },
                    "$setOnInsert": {"access": "free", "downloadable": True},
                },
                upsert=True,
            )
            for file in data
        ]
        if not operations:
            return 0
        result = await asyncio.to_thread(self.files.bulk_write, operations, ordered=False)
        return result.upserted_count

    async def save_channel_cover(self, chat_id, content, content_type):
        await asyncio.to_thread(
            self.channel_settings.update_one,
            {"_id": str(chat_id)},
            {"$set": {
                "cover": content,
                "cover_type": content_type,
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )

    async def get_channel_cover(self, chat_id):
        return await asyncio.to_thread(
            self.channel_settings.find_one,
            {"_id": str(chat_id)},
            {"cover": 1, "cover_type": 1},
        )

    async def create_user(self, username, password_hash, tier="free", expires_at=None):
        await asyncio.to_thread(
            self.users.update_one,
            {"_id": username.lower()},
            {"$set": {
                "username": username,
                "password_hash": password_hash,
                "tier": tier,
                "active": True,
                "expires_at": expires_at,
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )

    async def update_user(self, username, tier, active, expires_at=None, password_hash=None):
        changes = {
            "tier": tier,
            "active": bool(active),
            "expires_at": expires_at,
            "updated_at": datetime.now(timezone.utc),
        }
        if password_hash:
            changes["password_hash"] = password_hash
        result = await asyncio.to_thread(
            self.users.update_one,
            {"_id": username.lower()},
            {"$set": changes},
        )
        return result.matched_count

    async def change_user_password(self, username, password_hash):
        result = await asyncio.to_thread(
            self.users.update_one,
            {"_id": username.lower(), "active": {"$ne": False}},
            {"$set": {
                "password_hash": password_hash,
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        return result.matched_count

    async def get_user(self, username):
        if not username:
            return None
        return await asyncio.to_thread(self.users.find_one, {"_id": username.lower()})

    async def list_users(self):
        return await asyncio.to_thread(lambda: list(self.users.find({}, {"password_hash": 0}).sort("username", 1)))

    async def delete_user(self, username):
        result = await asyncio.to_thread(self.users.delete_one, {"_id": username.lower()})
        return result.deleted_count
