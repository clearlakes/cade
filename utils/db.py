import discord

from datetime import datetime
import motor.motor_asyncio
import configparser

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
        # turn entry values into variables
        get = lambda key, default: document.get(key, default)

        self.guild_id: int = get("guild_id", None)
        self.playlists: dict = get("playlists", {})
        self.welcome: list = get("welcome", [])
        self.prefix: str = get("prefix", ".")
        self.tags: dict = get("tags", {})

class GuildDB:
    def __init__(self, guild: discord.Guild):
        self.guild = {"guild_id": guild.id}

    async def _update(self, fields: dict):
        # adds default options to update_one
        return await _db.update_one(self.guild, fields, upsert = True)

    async def cancel_remove(self):
        await self._update({"$unset": {"left": 1}})

    async def remove(self):
        """Removes a guild from the database after 3 days"""
        await self._update({"$set": {"left": datetime.utcnow()}})

    async def get(self):
        """Returns the guild's database entry as a class"""
        _doc = await _db.find_one(self.guild)
        return Document(_doc) if _doc else Document()

    async def set(self, field: str, value):
        """Sets a field's value"""
        await self._update({"$set": {field: value}})

    async def push(self, field: str, value):
        """Adds a value to an array field"""
        await self._update({"$push": {field: value}})

    async def pull(self, field: str, value):
        """Removes a value from an array field"""
        await self._update({"$pull": {field: value}})

    async def add_obj(self, field: str, key: str, value):
        """Adds a value to a dictionary field"""
        await self._update({"$set": {f'{field}.{key}': value}})

    async def del_obj(self, field: str, key: str):
        """Removes a value from a dictionary field"""
        await self._update({"$unset": {f'{field}.{key}': 1}})
        await self._update({"$pull": {f'{field}.{key}': None}})