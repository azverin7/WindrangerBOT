import logging
from typing import Optional, Dict, Any, TypeVar, Generic
from collections import OrderedDict

from motor.motor_asyncio import AsyncIOMotorClient
from motor.core import AgnosticDatabase, AgnosticCollection
from pymongo import IndexModel, ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import OperationFailure

from core.config import MONGO_URL, MONGO_DB_NAME

logger = logging.getLogger('windranger.database')

K = TypeVar('K')
V = TypeVar('V')

class LRUCache(Generic[K, V]):
    def __init__(self, capacity: int):
        self.cache: OrderedDict[K, V] = OrderedDict()
        self.capacity = capacity

    def get(self, key: K) -> Optional[V]:
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key: K, value: V) -> None:
        self.cache[key] = value
        self.cache.move_to_end(key)
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

    def pop(self, key: K) -> None:
        self.cache.pop(key, None)

    def clear(self) -> None:
        self.cache.clear()

class Database:
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AgnosticDatabase] = None
        
        self.users: Optional[AgnosticCollection] = None
        self.active_lobbies: Optional[AgnosticCollection] = None
        self.match_history: Optional[AgnosticCollection] = None
        self.settings: Optional[AgnosticCollection] = None
        
        self._guild_cache: LRUCache[str, dict] = LRUCache(1000)
        self._user_locale_cache: LRUCache[str, str] = LRUCache(10000)

    async def connect_and_init(self) -> bool:
        try:
            self.client = AsyncIOMotorClient(
                MONGO_URL, 
                serverSelectionTimeoutMS=5000, 
                connectTimeoutMS=5000
            )
            await self.client.admin.command("ping")
            
            self.db = self.client[MONGO_DB_NAME]
            self.users = self.db["users"]
            self.active_lobbies = self.db["active_lobbies"]
            self.match_history = self.db["match_history"]
            self.settings = self.db["settings"]
            
            await self._setup_indexes()
            return True
            
        except Exception as e:
            logger.critical(f"DATABASE CONNECTION FAILED: {e}", exc_info=True)
            return False

    async def _setup_indexes(self) -> None:
        if self.users is None or self.match_history is None or self.active_lobbies is None:
            return

        try:
            await self.users.create_indexes([
                IndexModel([("guild_id", ASCENDING), ("season", DESCENDING), ("matches", DESCENDING), ("mmr", DESCENDING)]),
                IndexModel([("guild_id", ASCENDING), ("season", DESCENDING), ("mmr", DESCENDING)]),
                IndexModel([("guild_id", ASCENDING), ("ban_expires", ASCENDING)])
            ])
            
            await self.match_history.create_indexes([
                IndexModel([("lobby_id", ASCENDING)], unique=True),
                IndexModel([("guild_id", ASCENDING), ("season", DESCENDING)]),
                IndexModel([("guild_id", ASCENDING), ("timestamp", DESCENDING)])
            ])
            
            await self.active_lobbies.create_indexes([
                IndexModel([("guild_id", ASCENDING), ("shuffled", ASCENDING)]),
                IndexModel([("message_id", ASCENDING)])
            ])
            
        except OperationFailure as e:
            logger.warning(f"Index creation error: {e}")

    async def get_guild_config(self, guild_id: int | str) -> dict:
        gid = str(guild_id)
        cached = self._guild_cache.get(gid)
        if cached is not None:
            return cached

        if self.settings is None:
            return {}

        data = await self.settings.find_one({"_id": gid})
        result = data or {}
        self._guild_cache.put(gid, result)
        return result

    def clear_guild_cache(self, guild_id: int | str) -> None:
        self._guild_cache.pop(str(guild_id))

    async def set_guild_locale(self, guild_id: int | str, locale: str) -> None:
        gid = str(guild_id)
        if self.settings is None:
            return

        await self.settings.update_one(
            {"_id": gid},
            {"$set": {"locale": locale}},
            upsert=True
        )
        
        cached = self._guild_cache.get(gid)
        if cached is not None:
            cached["locale"] = locale
            self._guild_cache.put(gid, cached)
        else:
            self._guild_cache.pop(gid)

    async def get_user_locale(self, user_id: int | str) -> Optional[str]:
        uid = str(user_id)
        cached = self._user_locale_cache.get(uid)
        if cached is not None:
            return cached

        if self.users is None:
            return None

        data = await self.users.find_one({"_id": uid}, {"locale": 1})
        if data and "locale" in data:
            locale = data["locale"]
            self._user_locale_cache.put(uid, locale)
            return locale
            
        return None

    async def set_user_locale(self, user_id: int | str, locale: str) -> None:
        uid = str(user_id)
        if self.users is None:
            return

        await self.users.update_one(
            {"_id": uid},
            {"$set": {"locale": locale}},
            upsert=True
        )
        self._user_locale_cache.put(uid, locale)

    async def get_next_lobby_id(self, guild_id: int | str) -> int:
        gid = str(guild_id)
        if self.settings is None:
            return 1
            
        res = await self.settings.find_one_and_update(
            {"_id": f"counters_{gid}"},
            {"$inc": {"lobby_sequence": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        return res.get("lobby_sequence", 1)

    async def get_next_match_id(self, guild_id: int | str) -> int:
        gid = str(guild_id)
        if self.settings is None:
            return 1
            
        res = await self.settings.find_one_and_update(
            {"_id": f"counters_{gid}"},
            {"$inc": {"match_sequence": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        return res.get("match_sequence", 1)