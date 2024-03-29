import discord

from utils.main import Cade, CadeLavalink

from async_spotify.authentification.authorization_flows import ClientCredentialsFlow
from async_spotify import SpotifyApiClient

from dataclasses import dataclass
import configparser
import asyncio

class BaseKey:
    def __init__(self, section: str):
        # load config file
        self._config = configparser.ConfigParser(interpolation = None)
        self._config.read("config.ini")

        self._section = section

    def get(self, key):
        return self._config.get(self._section, key, fallback = None)

    @property
    def all(self):
        return dict(self._config.items(self._section)) if self else {}

    def __bool__(self):
        return self._config.has_section(self._section)

class LavalinkKeys(BaseKey):
    def __init__(self):
        super().__init__("lavalink")
        self.host = self.get("host")
        self.port = self.get("port")
        self.secret = self.get("secret")
        self.region = self.get("region")

        self.ordered_keys = (
            self.host, self.port, self.secret, self.region
        )

class SpotifyKeys(BaseKey):
    def __init__(self):
        super().__init__("spotify")
        self.key_pair = (self.get("key"), self.get("secret"))

class ImageServerKeys(BaseKey):
    def __init__(self):
        super().__init__("image-server")
        self.domain = self.get("domain")
        self.secret = self.get("secret")

class OtherKeys(BaseKey):
    def __init__(self):
        super().__init__("other")
        self.tenor = self.get("tenor")
        self.gyazo = self.get("gyazo")

@dataclass
class Keys:
    lavalink = LavalinkKeys()
    spotify = SpotifyKeys()
    image = ImageServerKeys()
    tenor = OtherKeys().tenor
    gyazo = OtherKeys().gyazo

def get_spotify_client():
    auth = ClientCredentialsFlow(*Keys.spotify.key_pair)
    api = SpotifyApiClient(auth)

    loop = asyncio.get_running_loop()
    loop.create_task(api.get_auth_token_with_client_credentials())
    loop.create_task(api.create_new_client())

    return api

# class taken from Devoxin's lavalink.py example
# https://github.com/Devoxin/Lavalink.py/blob/master/examples/music.py

class LavalinkVoiceClient(discord.VoiceClient):
    def __init__(self, client: Cade, channel: discord.abc.Connectable):
        self.client = client
        self.channel = channel
        self.log = client.log

        # ensure that a client already exists
        if self.client.lavalink:
            self.lavalink = self.client.lavalink
        else:
            self.client.lavalink = CadeLavalink(client.user.id)
            self.client.lavalink.add_node(*Keys.lavalink.ordered_keys, name = "default-node")
            self.lavalink = self.client.lavalink

    async def on_voice_server_update(self, data):
        # the data needs to be transformed before being handed down to
        # voice_update_handler
        lavalink_data = {
            "t": "VOICE_SERVER_UPDATE",
            "d": data
        }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def on_voice_state_update(self, data):
        # the data needs to be transformed before being handed down to
        # voice_update_handler
        lavalink_data = {
            "t": "VOICE_STATE_UPDATE",
            "d": data
        }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def connect(self, *, timeout: float, reconnect: bool, self_deaf: bool = False, self_mute: bool = False) -> None:
        """Connect the bot to the voice channel and create a player_manager if it doesn't exist yet"""
        # ensure there is a player_manager when creating a new voice_client
        self.lavalink.player_manager.create(guild_id = self.channel.guild.id)
        await self.channel.guild.change_voice_state(channel = self.channel, self_mute = self_mute, self_deaf = self_deaf)

        self.log.info(f"added player in {self.channel.guild.id}")

    async def disconnect(self, *, force: bool) -> None:
        """Handles the disconnect. Cleans up running player and leaves the voice client"""
        player = self.lavalink.player_manager.get(self.channel.guild.id)

        # no need to disconnect if we are not connected
        if not force and not player.is_connected:
            return

        # None means disconnect
        await self.channel.guild.change_voice_state(channel = None)

        # update the channel_id of the player to None
        # this must be done because the on_voice_state_update that
        # would set channel_id to None doesn't get dispatched after the
        # disconnect
        player.channel_id = None
        self.cleanup()

        self.lavalink.player_manager.remove(self.channel.guild.id)
        self.log.info(f"removed player in {self.channel.guild.id}")