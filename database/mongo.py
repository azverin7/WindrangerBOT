import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import IndexModel, ASCENDING, DESCENDING, ReturnDocument
from core.config import MONGO_URL, MONGO_DB_NAME

logger = logging.getLogger('windranger.database')

class Database:
    def __init__(self):
        self.client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
        self.db = None
        self.players = None
        self.archived_players = None
        self.lobbies = None
        self.settings = None
        self.history = None
        self._cache = {}

    async def connect_and_init(self) -> bool:
        try:
            await self.client.admin.command("ping")
            self.db = self.client[MONGO_DB_NAME]
            self.players = self.db["player_stats"]
            self.archived_players = self.db["archived_players"]
            self.lobbies = self.db["active_lobbies"]
            self.settings = self.db["settings"]
            self.history = self.db["match_history"]
            
            await self._setup_indexes()
            return True
        except Exception as e:
            logger.critical(f"DATABASE CONNECTION FAILED: {e}")
            return False

    async def _setup_indexes(self) -> None:
        await self.players.create_indexes([
            IndexModel([("guild_id", ASCENDING), ("pts", DESCENDING)]),
            IndexModel([("guild_id", ASCENDING), ("matches", DESCENDING)]),
            IndexModel([("user_id", ASCENDING), ("guild_id", ASCENDING)], unique=True)
        ])
        await self.history.create_indexes([
            IndexModel([("guild_id", ASCENDING), ("match_id", DESCENDING)]),
            IndexModel([("guild_id", ASCENDING), ("season", DESCENDING)]),
            IndexModel([("guild_id", ASCENDING), ("ended_at", DESCENDING)])
        ])
        await self.archived_players.create_index([("guild_id", ASCENDING), ("season", DESCENDING), ("pts", DESCENDING)])
        await self.lobbies.create_index([("guild_id", ASCENDING), ("active", ASCENDING)])
        await self.lobbies.create_index([("all_players", ASCENDING), ("active", ASCENDING)])

    async def get_guild_config(self, guild_id: int) -> dict:
        gid = str(guild_id)
        if gid not in self._cache:
            self._cache[gid] = await self.settings.find_one({"_id": gid}) or {}
        return self._cache[gid]

    def clear_cache(self, guild_id: int):
        self._cache.pop(str(guild_id), None)

    async def get_next_lobby_id(self, guild_id: int) -> int:
        res = await self.settings.find_one_and_update(
            {"_id": f"counters_{guild_id}"},
            {"$inc": {"lobby_sequence": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        return res["lobby_sequence"]

    async def get_next_match_id(self, guild_id: int) -> int:
        res = await self.settings.find_one_and_update(
            {"_id": f"counters_{guild_id}"},
            {"$inc": {"match_sequence": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        return res["match_sequence"]

    async def process_match_result(self, user_id: int, is_winner: bool, role_key: str, guild_id: int) -> None:
        query = {"user_id": user_id, "guild_id": guild_id}
        p = await self.players.find_one(query) or {"streak": 0}
        st = p.get("streak", 0)
        
        new_streak = (st + 1 if st >= 0 else 1) if is_winner else (st - 1 if st <= 0 else -1)
        
        await self.players.update_one(
            query,
            {
                "$set": {"streak": new_streak},
                "$inc": {
                    "pts": 25 if is_winner else -25,
                    "wins": 1 if is_winner else 0, 
                    "losses": 0 if is_winner else 1, 
                    "matches": 1, 
                    f"roles.{role_key}.wins": 1 if is_winner else 0, 
                    f"roles.{role_key}.matches": 1
                },
                "$setOnInsert": {"bans": {}}
            },
            upsert=True
        )

db = Database()