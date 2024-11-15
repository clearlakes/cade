import configparser
from datetime import datetime

import discord
import motor.motor_asyncio

# load config file
_config = configparser.ConfigParser()
_config.read("config.ini")

_mongo_uri = str(_config.get("mongo", "uri"))
_mongo_db_name = str(_config.get("mongo", "database"))
_mongo_coll_name = str(_config.get("mongo", "collection"))

_mongo_client = motor.motor_asyncio.AsyncIOMotorClient(_mongo_uri)
_db = _mongo_client[_mongo_db_name][_mongo_coll_name]


class Document:
    def __init__(self, document: dict = {}):
        self._doc = document
        get = lambda key, default: self._doc.get(key, default)

        # turn entry values into variables
        self.guild_id: int = get("guild_id", None)
        self.playlists: dict = get("playlists", {})
        self.welcome: list = get("welcome", [])
        self.prefix: str = get("prefix", ".")
        self.tags: dict[str, str] = get("tags", {})


class GuildDB:
    def __init__(self, guild: discord.Guild):
        self.guild = {"guild_id": guild.id}

    async def _update(self, fields: dict):
        # adds default options to update_one
        return await _db.update_one(self.guild, fields, upsert=True)

    async def cancel_remove(self):
        await self._update({"$unset": {"left": 1}})

    async def remove(self):
        """removes a guild from the database after 3 days"""
        await self._update({"$set": {"left": datetime.utcnow()}})

    async def get(self):
        """returns the guild's database entry as a class"""
        _doc = await _db.find_one(self.guild)
        return Document(_doc) if _doc else Document()

    async def set(self, field: str, value):
        """sets a field's value"""
        await self._update({"$set": {field: value}})

    async def push(self, field: str, value):
        """adds a value to an array field"""
        await self._update({"$push": {field: value}})

    async def pull(self, field: str, value):
        """removes a value from an array field"""
        await self._update({"$pull": {field: value}})

    async def add_obj(self, field: str, key: str, value):
        """adds a value to a dictionary field"""
        await self._update({"$set": {f"{field}.{key}": value}})

    async def del_obj(self, field: str, key: str):
        """removes a value from a dictionary field"""
        await self._update({"$unset": {f"{field}.{key}": 1}})
        await self._update({"$pull": {f"{field}.{key}": None}})


class Internal:
    def __init__(self) -> None:
        self._internal = GuildDB(discord.Object(id=0))

    @property
    async def _db(self) -> dict:
        return (await self._internal.get())._doc

    @property
    async def total_invoke_count(self) -> int:
        return sum((await self._db).get("count", {}).values())

    async def inc_invoke_count(self, cmd: str) -> None:
        return await self._internal._update({"$inc": {f"count.{cmd}": 1}})

    async def get_invoke_count(self, cmd: str) -> int:
        return (await self._db).get("count", {}).get(cmd, 0)
