import discord
import configparser
import motor.motor_asyncio

# load config file
_config = configparser.ConfigParser()
_config.read("config.ini")

_mongo_url = str(_config.get("server", "mongodb"))
_mongo_client = motor.motor_asyncio.AsyncIOMotorClient(_mongo_url)
_db = _mongo_client.cade.main

class Document:
    def __init__(self, document: dict):
        if document:
            # turn entry values into variables
            get = lambda key, default: document.get(key, default)

            self.guild_id: int = get('guild_id', None)
            self.playlists: dict = get('playlists', {})
            self.welcome: list = get('welcome', [])
            self.tags: dict = get('tags', {})

class Guild:
    def __init__(self, guild: discord.Guild):
        self.guild = {'guild_id': guild.id}
        self.id = guild.id

    async def add(self):
        """Adds a guild to the database"""
        await _db.insert_one({
            'guild_id': self.id,
            'tags': {},
            'playlists': {},
            'welcome': [None, None],
        })
    
    async def remove(self):
        """Removes a guild from the database"""
        await _db.delete_one(self.guild)

    async def get(self):
        """Returns the guild's database entry as a class"""
        _doc = await _db.find_one(self.guild)
        return Document(_doc) if _doc else None

    async def set(self, field: str, value):
        """Sets a field's value"""
        await _db.update_one(self.guild, {'$set': {field: value}})

    async def push(self, field: str, value):
        """Adds a value to an array field"""
        await _db.update_one(self.guild, {'$push': {field: value}})
    
    async def pull(self, field: str, value):
        """Removes a value from an array field"""
        await _db.update_one(self.guild, {'$pull': {field: value}})
    
    async def add_obj(self, field: str, key: str, value):
        """Adds a value to a dictionary field"""
        await _db.update_one(self.guild, {'$set': {f'{field}.{key}': value}})
    
    async def del_obj(self, field: str, key: str):
        """Removes a value from a dictionary (or array) field"""
        await _db.update_one(self.guild, {'$unset': {f'{field}.{key}': 1}})
        await _db.update_one(self.guild, {'$pull': {f'{field}.{key}': None}})