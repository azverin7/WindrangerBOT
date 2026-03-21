import logging
from typing import Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient
from motor.core import AgnosticDatabase, AgnosticCollection
from pymongo import IndexModel, ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import OperationFailure
from core.config import MONGO_URL, MONGO_DB_NAME

logger = logging.getLogger('windranger.database')

class Database:
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AgnosticDatabase] = None
        
        self.users: Optional[AgnosticCollection] = None
        self.active_lobbies: Optional[AgnosticCollection] = None
        self.match_history: Optional[AgnosticCollection] = None
        self.settings: Optional[AgnosticCollection] = None
        
        self._cache: Dict[str, dict] = {}

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
                IndexModel([("guild_id", ASCENDING), ("season", DESCENDING), ("mmr", DESCENDING)])
            ])
            
            await self.match_history.create_indexes([
                IndexModel([("lobby_id", ASCENDING)], unique=True),
                IndexModel([("guild_id", ASCENDING), ("season", DESCENDING)]),
                IndexModel([("guild_id", ASCENDING), ("timestamp", DESCENDING)])
            ])
            
            await self.active_lobbies.create_indexes([
                IndexModel([("guild_id", ASCENDING), ("shuffled", ASCENDING)])
            ])
            
        except OperationFailure as e:
            logger.warning(f"Index creation error: {e}")

    async def get_guild_config(self, guild_id: int | str) -> dict:
        gid = str(guild_id)
        if gid not in self._cache:
            if self.settings is None:
                return {}
            data = await self.settings.find_one({"_id": gid})
            self._cache[gid] = data or {}
        return self._cache[gid]

    def clear_cache(self, guild_id: int | str) -> None:
        self._cache.pop(str(guild_id), None)

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