import discord
import configparser
import pymongo

# load config file
_config = configparser.ConfigParser()
_config.read("config.ini")

_mongo_url = str(_config.get("server", "mongodb"))
_mongo_client = pymongo.MongoClient(_mongo_url)
_db = _mongo_client.cade.main

class Document:
    def __init__(self, document: dict):
        if document:
            # turn entry values into variables
            get = lambda key: document.get(key)

            self.guild_id: int = get('guild_id')
            self.playlists: dict = get('playlists')
            self.welcome: dict = get('welcome')
            self.tags: dict = get('tags')

class Guild:
    def __init__(self, guild: discord.Guild):
        self.guild = {'guild_id': guild.id}
        self.id = guild.id

    def add(self):
        """Adds a guild to the database"""
        _db.insert_one({
            'guild_id': self.id,
            'tags': {},
            'playlists': {},
            'welcome': [None, None],
        })
    
    def remove(self):
        """Removes a guild from the database"""
        _db.delete_one(self.guild)

    def get(self):
        """Returns the guild's database entry as a class"""
        _doc = _db.find_one(self.guild)
        return Document(_doc) if _doc else None

    def set(self, field: str, value):
        """Sets a field's value"""
        _db.update_one(self.guild, {'$set': {field: value}})

    def push(self, field: str, value):
        """Adds a value to an array field"""
        _db.update_one(self.guild, {'$push': {field: value}})
    
    def add_obj(self, field: str, key: str, value):
        """Adds a value to a dictionary field"""
        _db.update_one(self.guild, {'$set': {f'{field}.{key}': value}})
    
    def del_obj(self, field: str, key: str):
        """Removes a value from a dictionary (or array) field"""
        _db.update_one(self.guild, {'$unset': {f'{field}.{key}': 1}})
        _db.update_one(self.guild, {'$pull': {f'{field}.{key}': None}})

    